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
