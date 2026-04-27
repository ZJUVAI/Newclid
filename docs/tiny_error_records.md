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

### [2026-03-13] Rule Reduction — Generality Sorting Bug (Critical)

**Command:**
```bash
bash scripts/run_discovery_pipeline.sh
# Stage 2: Rule Reduction with seed-based group reduction
```

**Expected Output:**
Rules should be sorted by generality with fewer premises first:
- Most general: 8 premises → score=(-8, 1)
- Least general: 34 premises → score=(-34, 1)

**Actual Output:**
```
Step 2: Sorted 294 rules by generality
  Most general: coll a b c, coll a d e, ... (score: (-34, 1))  # 34 premises
  Least general: cong a b b c, cong b d d e, ... (score: (-8, 1))  # 8 premises
```

**Root Cause:**
File: `src/newclid/proof_scout/reduction/rule_reducer.py`, line 185
```python
sorted_rules = sorted(rules, key=lambda r: r.generality_score)  # ✗ Wrong: ascending order
```

The generality score is `(-n_premises, n_conclusions)`. With ascending sort:
- (-34, 1) < (-8, 1), so (-34, 1) comes first ✗
- This puts rules with MORE premises first (opposite of intended)

**Fix:**
```python
sorted_rules = sorted(rules, key=lambda r: r.generality_score, reverse=True)  # ✓ Correct
```

With descending sort:
- (-8, 1) > (-34, 1), so (-8, 1) comes first ✓
- This correctly puts rules with FEWER premises first

**Impact:**
- **Critical Bug**: Greedy elimination algorithm starts from wrong end
- May have kept more specific rules and eliminated more general ones
- All previous rule reduction results are suboptimal
- Need to re-run pipeline after fix

**Status:** ✓ (Fixed on 2026-03-13)

**Notes:**
- Bug discovered by user while monitoring 100k pipeline logs
- Affects all experiments using rule reduction
- Fix is one-line change: add `reverse=True` parameter
- Verification: After fix, log should show fewer premises for "most general"

---

### [2026-04-27] Rule usage evaluation — jgex baseline cache filename mismatch

**Command:**
```bash
python scripts/evaluate_rules_csolver.py evaluate \
  --rules outputs/experiments/20260327_01_weak1m_rule_extraction/extracted_rules_maxprem7.txt \
  --baseline-cache outputs/eval_baselines_csolver/ \
  --output outputs/experiments/20260427_01_rule_usage_analysis/eval_weak1m_jgex231/ \
  --benchmarks jgex_231 --workers 10 --timeout 600
```

**Expected Output:**
Script should locate the cached baseline for `jgex_231` automatically.

**Actual Output:**
The benchmark key is `jgex_231`, but the existing cached baseline file is named `jgex_ag_231_baseline.json`, so the script would not find the cache without a compatibility symlink.

**Status:** ✓

**Notes:**
Resolved locally by creating symlink:
```bash
ln -sf outputs/eval_baselines_csolver/jgex_ag_231_baseline.json outputs/eval_baselines_csolver/jgex_231_baseline.json
```
This is a historical naming mismatch in cached outputs, not a runtime solver bug.


**Date:** 2026-03-15
**Experiment:** 20260315_01_groundtruth_rule_extraction
**Command:**
```bash
python scripts/verify_groundtruth_rules.py \
    --problems .../success_proofs_aux_constructions.jsonl \
    --extracted-rules .../v2/extracted_rules.txt \
    --base-rules src/newclid/default_configs/rules.txt
```

**Expected Output:** 提取的 10 条规则被正确加载，与 62 条基础规则合并为 72 条规则进行验证

**Actual Output:** 提取的规则完全未被加载（0 条），验证结果 0/25 (0%)

**Root Cause:**
- `append_rules_from_txt(rule_txt: str)` 接收的是**规则文本内容**，不是文件路径
- 验证脚本错误地传入了 `str(base_rules_path)` 和 `str(extracted_rules_path)`（文件路径字符串）
- 路径字符串中没有 `=>`，`Rule.parse_text()` 解析出 0 条规则
- 第一次调用时 `self._rules is None`，触发 fallback 加载默认规则（31 条），掩盖了问题
- 第二次调用（提取规则）解析出 0 条，什么都没加

**Fix:**
```python
# Before (BUG):
builder.append_rules_from_txt(str(base_rules_path))
builder.append_rules_from_txt(str(extracted_rules_path))

# After (FIXED):
builder.append_rules_from_txt(base_rules_path.read_text(encoding='utf-8'))
builder.append_rules_from_txt(extracted_rules_path.read_text(encoding='utf-8'))
```

**Impact:**
- **严重**: 之前所有验证结果（v1: 0/25, v2: 0/25）均无效
- 修复后验证结果: **13/25 (52%)**，证明提取的规则确实有效
- 导致之前得出的"规则提取完全无效"结论是错误的

**Status:** ✓ (Fixed on 2026-03-15)

