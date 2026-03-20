# Tiny Error Records

This document tracks all errors, data inconsistencies, and unexpected behaviors encountered during experiments. Even minor issues should be recorded here to help identify systematic problems.

## Purpose

- Track all experimental errors and data anomalies
- Provide a historical record for debugging
- Identify patterns in recurring issues
- Ensure no detail is overlooked

## Record Format

Each entry should include:
- **Date**: YYYY-MM-DD
- **Experiment Name**: Name or ID of the experiment
- **Command**: Exact command that was executed
- **Expected Output**: (Optional) What was expected to happen
- **Actual Output**: What actually happened
- **Status**: ✓ (Resolved) or ✗ (Unresolved)
- **Notes**: Additional context, root cause, or solution

---

## Error Records

### Template

```
### [YYYY-MM-DD] Experiment Name

**Command:**
```bash
command here
```

**Expected Output:** (Optional)
Description of expected behavior

**Actual Output:**
Description of actual behavior or error message

**Status:** ✗ / ✓

**Notes:**
Additional context, investigation findings, or solution
```

---

## Example Entry

### [2026-03-10] Example Experiment

**Command:**
```bash
python scripts/discovery_pipeline.py --input data.jsonl --output results/
```

**Expected Output:**
Pipeline should complete all stages and output basis rules

**Actual Output:**
```
Error: KeyError: 'premises' at line 142
```

**Status:** ✓

**Notes:**
Root cause: Input JSONL file had inconsistent schema. Some entries missing 'premises' field.
Solution: Added validation step in Stage 1a to check required fields before processing.

---

## Records

<!-- Add new records below this line -->

### [2026-03-12] evaluate_rules.py — rules_to_text 序列化格式错误导致 augmented 全面 regression

**Command:**
```bash
python scripts/evaluate_rules.py evaluate --rules .../basis_rules.txt --baseline-cache outputs/eval_baselines/ --output ... --benchmarks jgex_ag_231,hageo_409
```

**Expected Output:**
Augmented solve rate >= baseline (规则应该帮助求解更多题目)

**Actual Output:**
jgex_ag_231: 202→2, hageo_409: 100→0 (catastrophic regression)

**Root Cause:**
`rules_to_text()` 使用 `str(rule)` 序列化 Rule 对象，输出 Python tuple repr 格式：
```
('coll', 'a', 'b', 'c'), ('cong', 'a', 'c', 'b', 'c') => ('coll', 'd', 'e', 'c')
```
但 `Rule.parse_text()` / `append_rules_from_txt()` 期望 JGEX DSL 格式：
```
coll a b c, cong a c b c => coll d e c
```
导致解析出的 "规则" 全是垃圾数据（每个 premise 变成单字符串 tuple），破坏了推理引擎。

**Fix:**
新增 `rule_to_dsl()` 函数，正确序列化为 DSL 格式。已验证 16 条规则全部 round-trip 正确。

**Status:** ✓ (已修复)

### [2026-03-11] HAGeo 409 Baseline — 4 Problems Fail to Build

**Command:**
```bash
python scripts/evaluate_rules.py baseline --output outputs/eval_baselines/ --benchmarks hageo_409 --workers 30
```

**Expected Output:**
All 409 problems should be attempted; failures should be caught gracefully.

**Actual Output:**
4 problems crash with `returncode=1` during `ProofState.build_problemJGEX`:

| Problem ID | Error |
|------------|-------|
| `2011CTSTp10` | `PointTooCloseError()` |
| `2019KoMaLA736` | `AttributeError: 'Point' has no attribute 'num'` (ncoll check on un-initialized point) |
| `ShuZhiMiGeo209` | `PointTooCloseError()` |
| `XinXingV35p1` | `PointTooCloseError()` |

Note: These are caught by Ray's exception handling and reported as `solved: false, error: "worker crashed"`. The benchmark run completes for the other problems.

**Status:** ✗ (Problems skipped for now; engine incompatibility to be investigated later)

**Notes:**
- 3 of 4 failures are `PointTooCloseError` — the geometric construction produces numerically degenerate configurations that fail even after max retries.
- 1 failure (`2019KoMaLA736`) is a different bug: `Point.num` is `None` when `Coll.check_numerical` is called, suggesting the point was never successfully placed.
- Skip list saved at: `outputs/experiments/20260311_01_hageo409_oom_diagnosis/failed_problems.txt`
- These are NOT OOM issues — they are fast failures (`rc=1` within seconds).

### [2026-03-12] evaluate_rules.py — Augmented solver worker stuck past timeout (214GB RSS)

**Command:**
```bash
python scripts/evaluate_rules.py evaluate --rules .../basis_rules.txt --baseline-cache outputs/eval_baselines/ --output ... --benchmarks jgex_ag_231,hageo_409 --workers 30 --timeout 3600
```

**Expected Output:**
All workers should respect the 3600s timeout and return results.

**Actual Output:**
One Ray worker (PID 93068) ran for >65 minutes (past 3600s timeout), consuming 214GB RSS memory. The `solver.run(timeout=3600)` internal timeout was not enforced. The worker was solving problem `2017CTSTp9` with augmented rules. Had to be manually killed (`kill 93068`) to unblock the evaluation.

**Status:** ✗ (Workaround: manual kill; root cause in solver timeout enforcement not investigated)

**Notes:**
- The solver's internal timeout mechanism does not reliably enforce time limits for all problems, especially when augmented rules cause exponential state expansion.
- This only occurred with augmented rules (baseline completed normally for this problem).
- Consider adding a hard process-level timeout wrapper in `solve_single_problem` as a safety net.
