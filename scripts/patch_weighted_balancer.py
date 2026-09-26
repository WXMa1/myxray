#!/usr/bin/env python3
"""Patch XTLS/Xray-core to add the validated weightedRoundRobin balancer only.

Compatibility goals:
- preserve the original WXMa1/myxray WRR behavior;
- compile against both the known-good d562d89 baseline and newer upstream main;
- no protobuf/API changes;
- idempotent and semantic-anchor based;
- no native selection telemetry in this balancer-only variant.

This is the conservative rollback/reference patcher. The separate
patch_weighted_balancer_with_stats.py layers native selection counters on top.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from textwrap import dedent

ROOT = pathlib.Path.cwd()


def fail(msg: str) -> "None":
    print(f"[patch] ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"required file not found: {rel}; run this script from Xray-core repository root")
    return path.read_text(encoding="utf-8")


def write(rel: str, data: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def sub_once(text: str, pattern: str, repl, description: str, flags: int = 0) -> str:
    new_text, count = re.subn(pattern, repl, text, count=1, flags=flags)
    if count != 1:
        fail(f"could not locate unique anchor for {description}")
    return new_text

STRATEGY_GO = dedent(r"""
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

    type WeightedRoundRobinStrategy struct {
        FallbackTag string
        ctx         context.Context
        observatory extension.Observatory
        mu          sync.Mutex
        current     map[string]float64
        rules       []weightedRoundRobinRule
    }

    type weightedRoundRobinRule struct {
        match  string
        regexp *regexp.Regexp
        weight float64
    }

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
                alive = append(alive, candidate)
            }
        }
        return alive
    }
""")

TEST_GO = dedent(r"""
    package router

    import "testing"

    func TestWeightedRoundRobinStrategyDistribution(t *testing.T) {
        s, err := NewWeightedRoundRobinStrategy(&StrategyLeastLoadConfig{
            Costs: []*StrategyWeight{
                {Match: "node-a", Value: 5},
                {Match: "node-b", Value: 3},
                {Match: "node-c", Value: 2},
            },
        }, "")
        if err != nil {
            t.Fatal(err)
        }
        candidates := []string{"node-a", "node-b", "node-c"}
        counts := map[string]int{}
        for i := 0; i < 100; i++ {
            counts[s.PickOutbound(candidates)]++
        }
        if counts["node-a"] != 50 || counts["node-b"] != 30 || counts["node-c"] != 20 {
            t.Fatalf("unexpected distribution: %#v", counts)
        }
    }

    func TestWeightedRoundRobinStrategyZeroWeightAndDefault(t *testing.T) {
        s, err := NewWeightedRoundRobinStrategy(&StrategyLeastLoadConfig{
            Costs: []*StrategyWeight{
                {Match: "disabled", Value: 0},
                {Regexp: true, Match: `^fast-`, Value: 3},
            },
        }, "")
        if err != nil {
            t.Fatal(err)
        }
        candidates := []string{"disabled-node", "fast-a", "normal"}
        counts := map[string]int{}
        for i := 0; i < 40; i++ {
            counts[s.PickOutbound(candidates)]++
        }
        if counts["disabled-node"] != 0 || counts["fast-a"] != 30 || counts["normal"] != 10 {
            t.Fatalf("unexpected distribution/default weight behavior: %#v", counts)
        }
    }
""")

def patch_router_strategy() -> None:
    rel = "infra/conf/router_strategy.go"
    text = read(rel)
    if not re.search(r'(?m)^\s*strategyWeightedRoundRobin\s+(?:string\s*)?=\s*"weightedroundrobin"\s*$', text):
        text = sub_once(
            text,
            r'(?m)^(\s*strategyLeastLoad\s+(?:string\s*)?=\s*"leastload"\s*)$',
            lambda m: m.group(1) + '\n\tstrategyWeightedRoundRobin string = "weightedroundrobin"',
            "weightedRoundRobin strategy constant",
        )
    if not re.search(r'(?m)^\s*strategyWeightedRoundRobin\s*:\s*func\(\)', text):
        text = sub_once(
            text,
            r'(?m)^(\s*strategyLeastLoad\s*:\s*func\(\)\s*(?:interface\{\}|any)\s*\{\s*return\s+new\(strategyLeastLoadConfig\)\s*\},\s*)$',
            lambda m: m.group(1) + '\n\tstrategyWeightedRoundRobin: func() interface{} { return new(strategyWeightedRoundRobinConfig) },',
            "weightedRoundRobin config loader",
        )
    if "type strategyWeightedRoundRobinConfig struct" not in text:
        block = dedent('''
            type strategyWeightedRoundRobinConfig struct {
                // Reuse router.StrategyWeight. Unmatched outbounds default to weight 1.
                Weights []*router.StrategyWeight `json:"weights,omitempty"`
            }
            // Build uses StrategyLeastLoadConfig only as an existing typed-message
            // carrier for repeated StrategyWeight. WeightedRoundRobin interprets
            // Costs as routing weights; leastLoad behavior is unchanged.
            func (v *strategyWeightedRoundRobinConfig) Build() (proto.Message, error) {
                return &router.StrategyLeastLoadConfig{Costs: v.Weights}, nil
            }
        ''')
        health_anchor = re.search(r'(?m)^//\s*HealthCheckSettings\b[^\n]*$', text)
        if health_anchor:
            pos = health_anchor.start()
            text = text[:pos] + block + text[pos:]
        else:
            build_anchor = re.search(r'(?m)^func\s+\(v\s+\*strategyLeastLoadConfig\)\s+Build\s*\(', text)
            if not build_anchor:
                fail("could not locate semantic anchor for weightedRoundRobin settings type")
            pos = build_anchor.start()
            text = text[:pos] + block + text[pos:]
    write(rel, text)


def patch_router_conf() -> None:
    rel = "infra/conf/router.go"
    text = read(rel)
    if "strategyWeightedRoundRobin" in text:
        return
    pattern = (
        r'(?m)^(?P<prefix>\s*case\s+)'
        r'(?=[^:\n]*strategyRandom)'
        r'(?=[^:\n]*strategyLeastLoad)'
        r'(?=[^:\n]*strategyLeastPing)'
        r'(?=[^:\n]*strategyRoundRobin)'
        r'(?P<items>[^:\n]+)(?P<suffix>:\s*)$'
    )

    def repl(m: re.Match[str]) -> str:
        items = m.group("items").rstrip()
        return f'{m.group("prefix")}{items}, strategyWeightedRoundRobin{m.group("suffix")}'

    text = sub_once(text, pattern, repl, "router accepted strategy switch")
    write(rel, text)


def patch_runtime_builder() -> None:
    rel = "app/router/config.go"
    text = read(rel)
    if 'case "weightedroundrobin":' in text.lower():
        return
    block = dedent('''
        case "weightedroundrobin":
            i, err := br.StrategySettings.GetInstance()
            if err != nil {
                return nil, err
            }
            s, ok := i.(*StrategyLeastLoadConfig)
            if !ok {
                return nil, errors.New("not a StrategyLeastLoadConfig for weightedRoundRobin")
            }
            weightedRoundRobinStrategy, err := NewWeightedRoundRobinStrategy(s, br.FallbackTag)
            if err != nil {
                return nil, err
            }
            return &Balancer{
                selectors:   br.OutboundSelector,
                ohm:         ohm,
                fallbackTag: br.FallbackTag,
                strategy:    weightedRoundRobinStrategy,
            }, nil
    ''')
    func_match = re.search(
        r'func\s+\(br\s+\*BalancingRule\)\s+Build\([^)]*\)\s*\(\*Balancer,\s*error\)\s*\{',
        text,
    )
    if not func_match:
        fail("BalancingRule.Build function not found in app/router/config.go")
    random_match = re.search(r'(?m)^\s*case\s+"random"\s*:', text[func_match.end():])
    if not random_match:
        fail('random strategy case not found inside BalancingRule.Build')

    pos = func_match.end() + random_match.start()
    text = text[:pos] + block + text[pos:]
    write(rel, text)


def write_new_files() -> None:
    # These files are deliberately rewritten to the canonical balancer-only
    # version on every run. The integration points remain unchanged when already
    # present, preserving idempotency and the validated WRR behavior.
    write("app/router/strategy_weightedroundrobin.go", STRATEGY_GO)
    write("app/router/strategy_weightedroundrobin_test.go", TEST_GO)


def gofmt() -> None:
    files = [
        "app/router/strategy_weightedroundrobin.go",
        "app/router/strategy_weightedroundrobin_test.go",
        "app/router/config.go",
        "infra/conf/router.go",
        "infra/conf/router_strategy.go",
    ]
    try:
        subprocess.run(["gofmt", "-w", *files], cwd=ROOT, check=True)
    except FileNotFoundError:
        fail("gofmt not found; install Go before applying this patch")
    except subprocess.CalledProcessError as exc:
        fail(f"gofmt failed with exit code {exc.returncode}")


def main() -> None:
    go_mod = read("go.mod")
    if "module github.com/xtls/xray-core" not in go_mod:
        fail("this does not look like the XTLS/Xray-core repository")

    patch_router_strategy()
    patch_router_conf()
    patch_runtime_builder()
    write_new_files()
    gofmt()

    print("[patch] weightedRoundRobin balancer applied")
    print("[patch] native selection counters are intentionally NOT included in this variant")
    print("[patch] run: go test ./app/router ./infra/conf")
    print("[patch] then build: CGO_ENABLED=0 go build -o xray -trimpath -buildvcs=false -ldflags='-s -w -buildid=' -v ./main")


if __name__ == "__main__":
    main()
