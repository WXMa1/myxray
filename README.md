# Xray weightedRoundRobin patch

This patch adds a new routing balancer strategy named `weightedRoundRobin` to current XTLS/Xray-core.

## Configuration

```json
{
  "routing": {
    "balancers": [
      {
        "tag": "weighted-proxy",
        "selector": ["proxy-"],
        "strategy": {
          "type": "weightedRoundRobin",
          "settings": {
            "weights": [
              {"regexp": false, "match": "proxy-a", "value": 5},
              {"regexp": false, "match": "proxy-b", "value": 3},
              {"regexp": false, "match": "proxy-c", "value": 2}
            ]
          }
        },
        "fallbackTag": "direct"
      }
    ]
  }
}
```

For integer weights `5:3:2`, while the eligible candidate set remains stable, each full 10-selection cycle produces 5, 3, and 2 selections with smooth weighted round-robin ordering. An outbound not matched by any weight rule gets weight `1`. A matched weight of `0` disables that outbound in this balancer. Negative weights are rejected.

When `regexp` is `false`, `match` follows Xray's existing `WeightManager` behavior and is a substring match. When `regexp` is `true`, it is a Go regular expression. First matching rule wins.

If `fallbackTag` is configured, the strategy mirrors Xray's existing `random` and `roundRobin` behavior and uses the observatory feature, when present, to exclude outbounds reported dead. Candidates without observation data are considered alive. If all eligible weights are zero or all candidates are unavailable, the balancer returns empty and Xray falls back to `fallbackTag`.

## Apply locally

Run from an Xray-core checkout:

```bash
python3 /path/to/patch_weighted_balancer.py
go test ./app/router ./infra/conf
CGO_ENABLED=0 go build -o xray -trimpath -buildvcs=false -ldflags="-s -w -buildid=" -v ./main
```

The patcher is idempotent and uses function names, constants, and switch cases as anchors; it does not use source line numbers.

## GitHub Actions

Copy these two paths into your own repository:

- `scripts/patch_weighted_balancer.py`
- `.github/workflows/build-weighted-xray.yml`

Run **Actions -> Build patched Xray weighted balancer -> Run workflow**, and set `xray_ref` to `main`, a release tag, or a commit SHA. The workflow checks out upstream Xray-core, applies the patch, runs focused tests, cross-compiles Linux/Windows/macOS artifacts, and uploads SHA-256 files.

## Why the patch reuses StrategyLeastLoadConfig internally

Xray already has protobuf `StrategyWeight` entries inside `StrategyLeastLoadConfig.Costs`. Reusing that typed-message carrier means the patch does not need to edit `app/router/config.proto` or generated `config.pb.go`. This is deliberate: it makes an out-of-tree CI patch substantially less brittle. It does not change `leastLoad` behavior; only `weightedRoundRobin` interprets the transported `Costs` entries as selection weights.


## Reference source files

The complete newly-added Go strategy and its tests are also included under `reference/app/router/` for direct review. The Python patcher is still the source of truth for applying the change to an upstream checkout because it also edits the three existing integration points.

The patcher deliberately fails if it cannot find its semantic anchors. That is safer than silently applying a possibly-wrong patch after a major upstream refactor.
