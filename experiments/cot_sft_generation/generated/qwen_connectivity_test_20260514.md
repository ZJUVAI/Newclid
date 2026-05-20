# Qwen Model Connectivity Test

- Time (UTC): `2026-05-14T07:03:18Z`
- Endpoint: `https://api.zjuqx.cn/v1/chat/completions`
- Prompt: `请只回复字符串 CONNECT_OK，不要添加任何其他内容。`
- Attempts per model: `3`

## Summary

| Model alias | Upstream model returned by gateway | Successes | Avg latency (s) | Min (s) | Max (s) | Avg cost per call |
|---|---|---:|---:|---:|---:|---:|
| `qwen/qwen3.5-flash-02-23` | `qwen/qwen3.5-flash-20260224` | `3/3` | `3.278` | `2.983` | `3.781` | `0.00005733` |
| `qwen/qwen3.5-plus-02-15` | `qwen/qwen3.5-plus-20260216` | `3/3` | `7.728` | `6.822` | `8.873` | `0.00049764` |

## Findings

- Both model aliases were reachable and returned HTTP `200` on all attempts.
- Both models followed the instruction exactly and returned `CONNECT_OK` every time.
- `qwen/qwen3.5-plus-02-15` was slower in this test:
  - Average latency was `7.728s`
  - This was about `2.36x` the average latency of `qwen/qwen3.5-flash-02-23`
- The gateway mapped the requested aliases to different upstream version strings:
  - `qwen/qwen3.5-flash-02-23 -> qwen/qwen3.5-flash-20260224`
  - `qwen/qwen3.5-plus-02-15 -> qwen/qwen3.5-plus-20260216`
- Even for this minimal prompt, both responses reported substantial reasoning token usage:
  - `flash`: `208` reasoning tokens on every run
  - `plus`: `266` to `366` reasoning tokens

## Per-attempt Results

| Model alias | Attempt | HTTP | Latency (s) | Request ID | Response model | Output | Total tokens | Reasoning tokens | Cost |
|---|---:|---:|---:|---|---|---|---:|---:|---:|
| `qwen/qwen3.5-flash-02-23` | `1` | `200` | `3.069` | `202605141501551097450575YyMRj7x` | `qwen/qwen3.5-flash-20260224` | `CONNECT_OK` | `237` | `208` | `0.00005733` |
| `qwen/qwen3.5-flash-02-23` | `2` | `200` | `3.781` | `20260514150158137916885rcb7OfwT` | `qwen/qwen3.5-flash-20260224` | `CONNECT_OK` | `237` | `208` | `0.00005733` |
| `qwen/qwen3.5-flash-02-23` | `3` | `200` | `2.983` | `20260514150201932034226sDIh7qjv` | `qwen/qwen3.5-flash-20260224` | `CONNECT_OK` | `237` | `208` | `0.00005733` |
| `qwen/qwen3.5-plus-02-15` | `1` | `200` | `7.488` | `20260514150204944115891IgEpZaFy` | `qwen/qwen3.5-plus-20260216` | `CONNECT_OK` | `322` | `293` | `0.00047372` |
| `qwen/qwen3.5-plus-02-15` | `2` | `200` | `6.822` | `20260514150212404564354qTL3E55l` | `qwen/qwen3.5-plus-20260216` | `CONNECT_OK` | `295` | `266` | `0.00043160` |
| `qwen/qwen3.5-plus-02-15` | `3` | `200` | `8.873` | `20260514150219244075539KfAc7iRY` | `qwen/qwen3.5-plus-20260216` | `CONNECT_OK` | `395` | `366` | `0.00058760` |

## Notes

- This was a text-only connectivity probe, not a capability benchmark.
- The `usage.cost` field was returned by the gateway itself and is recorded as-is.
- Raw structured results are saved in `qwen_connectivity_test_20260514.json` in the same directory.
