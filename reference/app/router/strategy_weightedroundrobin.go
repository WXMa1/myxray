package router

import (
	"context"
	"math"
	"regexp"
	"strings"
	"sync"

	"github.com/xtls/xray-core/app/observatory"
	"github.com/xtls/xray-core/common"
	"github.com/xtls/xray-core/common/errors"
	"github.com/xtls/xray-core/core"
	"github.com/xtls/xray-core/features/extension"
)

// WeightedRoundRobinStrategy implements smooth weighted round-robin (SWRR).
// Unmatched outbounds have weight 1. A matched weight of 0 disables that
// outbound for this balancer. The first matching weight rule wins.
type WeightedRoundRobinStrategy struct {
	FallbackTag string

	ctx         context.Context
	observatory extension.Observatory

	mu      sync.Mutex
	current map[string]float64
	rules   []weightedRoundRobinRule
}

type weightedRoundRobinRule struct {
	match  string
	regexp *regexp.Regexp
	weight float64
}

// NewWeightedRoundRobinStrategy creates a smooth weighted round-robin strategy.
// StrategyLeastLoadConfig is intentionally reused only as a protobuf carrier:
// its Costs field already contains repeated StrategyWeight and avoids adding a
// new protobuf message solely for this strategy.
func NewWeightedRoundRobinStrategy(settings *StrategyLeastLoadConfig, fallbackTag string) (*WeightedRoundRobinStrategy, error) {
	s := &WeightedRoundRobinStrategy{
		FallbackTag: fallbackTag,
		current:     make(map[string]float64),
	}
	if settings == nil {
		return s, nil
	}

	for _, w := range settings.Costs {
		if w == nil {
			continue
		}
		if w.Match == "" {
			return nil, errors.New("weightedRoundRobin: weight match must not be empty")
		}

		weight := float64(w.Value)
		if math.IsNaN(weight) || math.IsInf(weight, 0) || weight < 0 {
			return nil, errors.New("weightedRoundRobin: weight must be a finite number >= 0 for match: ", w.Match)
		}

		rule := weightedRoundRobinRule{match: w.Match, weight: weight}
		if w.Regexp {
			compiled, err := regexp.Compile(w.Match)
			if err != nil {
				return nil, errors.New("weightedRoundRobin: invalid regexp: ", w.Match).Base(err)
			}
			rule.regexp = compiled
		}
		s.rules = append(s.rules, rule)
	}

	return s, nil
}

func (s *WeightedRoundRobinStrategy) InjectContext(ctx context.Context) {
	s.ctx = ctx
	// Keep the same observatory/fallback behavior as Xray's random and
	// roundRobin strategies: health filtering is enabled when fallbackTag
	// is configured.
	if len(s.FallbackTag) > 0 {
		common.Must(core.RequireFeatures(s.ctx, func(observatory extension.Observatory) error {
			s.observatory = observatory
			return nil
		}))
	}
}

func (s *WeightedRoundRobinStrategy) GetPrincipleTarget(candidates []string) []string {
	return candidates
}

func (s *WeightedRoundRobinStrategy) PickOutbound(candidates []string) string {
	candidates = s.aliveCandidates(candidates)
	if len(candidates) == 0 {
		return ""
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	active := make(map[string]struct{}, len(candidates))
	totalWeight := 0.0
	selected := ""
	selectedCurrent := -math.MaxFloat64

	// Smooth weighted round robin:
	// current[i] += weight[i]
	// select max(current)
	// current[selected] -= sum(weight)
	for _, tag := range candidates {
		weight := s.weightFor(tag)
		if weight <= 0 {
			continue
		}

		active[tag] = struct{}{}
		totalWeight += weight
		s.current[tag] += weight

		if selected == "" || s.current[tag] > selectedCurrent {
			selected = tag
			selectedCurrent = s.current[tag]
		}
	}

	// Drop state for outbounds that disappeared, became unhealthy, or were
	// disabled with weight 0. If they return later they restart cleanly.
	for tag := range s.current {
		if _, ok := active[tag]; !ok {
			delete(s.current, tag)
		}
	}

	if selected == "" || totalWeight <= 0 {
		return ""
	}

	s.current[selected] -= totalWeight
	return selected
}

func (s *WeightedRoundRobinStrategy) weightFor(tag string) float64 {
	for _, rule := range s.rules {
		if rule.regexp != nil {
			if rule.regexp.MatchString(tag) {
				return rule.weight
			}
			continue
		}
		// Match semantics intentionally follow Xray's existing WeightManager:
		// non-regexp matches are substring matches.
		if strings.Contains(tag, rule.match) {
			return rule.weight
		}
	}
	return 1
}

func (s *WeightedRoundRobinStrategy) aliveCandidates(candidates []string) []string {
	if s.observatory == nil {
		return candidates
	}

	observeReport, err := s.observatory.GetObservation(s.ctx)
	if err != nil {
		// Match existing random/roundRobin behavior: if observation cannot
		// be read, do not unexpectedly drop all candidates.
		return candidates
	}

	result, ok := observeReport.(*observatory.ObservationResult)
	if !ok {
		return candidates
	}

	statusMap := make(map[string]*observatory.OutboundStatus, len(result.Status))
	for _, outboundStatus := range result.Status {
		statusMap[outboundStatus.OutboundTag] = outboundStatus
	}

	alive := make([]string, 0, len(candidates))
	for _, candidate := range candidates {
		if outboundStatus, found := statusMap[candidate]; found {
			if outboundStatus.Alive {
				alive = append(alive, candidate)
			}
		} else {
			// Preserve Xray's existing behavior: candidates without
			// observation data are considered alive.
			alive = append(alive, candidate)
		}
	}
	return alive
}
