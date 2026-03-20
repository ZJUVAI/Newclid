# Rule Validation Issues Analysis

**Date:** 2026-02-01
**Based on:** Discovery Pipeline 端到端测试 (50 条规则)

---

## 1. Overview

| Category | Count | Percentage |
|----------|-------|------------|
| Total Rules Tested | 49 | 100% |
| Valid (Provable) | 13 | 26.5% |
| Invalid (Not Provable) | 25 | 51.0% |
| Conversion Failed | 11 | 22.4% |

This document analyzes the reasons for rule validation failures and proposes solutions.

---

## 2. Conversion Failures (11 rules)

### 2.1 Unsupported Predicates (2 rules)

| Rule ID | Rule | Issue |
|---------|------|-------|
| r101 | `simtri a b c d e f, cong a b d e => contri a b c d e f` | `contri` not supported |
| r102 | `simtrir a b c d e f, cong a b d e => contrir a b c d e f` | `contrir` not supported |

**Root Cause:** The `_translate_premise()` function in `rule_tester.py` does not implement translation for `contri` (congruent triangles) and `contrir` (congruent triangles reflected) predicates.

**Solution:**
- **Option A (Skip):** Add `contri`, `contrir` to the unsupported predicates list in `RuleConverter`
- **Option B (Implement):** Add translation logic for these predicates (requires defining construction commands)

### 2.2 Complex Rules (9 rules)

| Rule ID | Premises | Issue |
|---------|----------|-------|
| r0033 | 8 | Greedy algorithm fails to find valid construction order |
| r0034 | 6 | Greedy algorithm fails to find valid construction order |
| r0035 | 6 | Greedy algorithm fails to find valid construction order |
| r0036 | 6 | Greedy algorithm fails to find valid construction order |
| r0037 | 9 | Greedy algorithm fails to find valid construction order |
| r0038 | 10 | Greedy algorithm fails to find valid construction order |
| r0047 | 12 | Greedy algorithm fails to find valid construction order |
| r0048 | 13 | Greedy algorithm fails to find valid construction order |
| r0049 | 14 | Greedy algorithm fails to find valid construction order |

**Root Cause:** The current greedy algorithm with random shuffling (100 attempts) cannot find a valid construction order for rules with 6+ premises. The search space grows exponentially with the number of premises.

**Solution:**
- **Option A (Filter):** Skip rules with 6+ premises during testing (recommended for short-term)
- **Option B (Improve Algorithm):** Implement backtracking search instead of greedy with random shuffling
- **Option C (Increase Attempts):** Increase `max_attempts` for complex rules (diminishing returns)

---

## 3. CSolver Errors (15 rules)

### 3.1 Empty Error Messages (10 rules)

| Rule ID | Problem Generated | Error |
|---------|-------------------|-------|
| r52 | `f = free f; e = free e; ... ? eqangle b a b c e d e r` | `CSolver error: ` |
| r53 | `f = free f; e = free e; ... ? eqangle b a b c e f e p` | `CSolver error: ` |
| r62 | `f = free f; e = free e; ... ? simtri b a c e d f` | `CSolver error: ` |
| r63 | `e = free e; d = free d; ... ? simtrir b a c e d f` | `CSolver error: ` |
| r34 | `f = free f; e = free e; ... ? simtri b a c e d f` | `CSolver error: ` |
| r35 | `f = free f; e = free e; ... ? simtrir b a c f d e` | `CSolver error: ` |
| r12 | `d = free d; c = free c; ... ? eqratio c b c d a b a d` | `CSolver error: ` |
| r46 | `d = free d; c = free c; ... ? eqangle d b d c d c d a` | `CSolver error: ` |
| r28 | `c = free c; a = free a; ... ? coll a b c` | `CSolver error: ` |
| r0032 | `d = free d; b = free b; ... ? para a f d e` | `CSolver error: ` |

**Root Cause:** C++ exceptions are not properly propagated to Python. The error message is empty because the exception type is caught but the message is lost.

**Analysis of Patterns:**
- Most involve `simtri`/`simtrir` goals (triangle similarity)
- Some involve complex `eqangle` patterns
- r28 (`para a b a c => coll a b c`) is a degenerate case (parallel lines through same point)

**Solution:**
- **Option A (Improve Error Handling):** Modify C++ DDAR bindings to properly propagate exception messages
- **Option B (Debug Logging):** Add verbose logging to identify the actual failure point
- **Option C (Skip Known Patterns):** Skip rules with `simtri`/`simtrir` as goals (temporary workaround)

### 3.2 Point Attribute Errors (2 rules)

| Rule ID | Problem Generated | Error |
|---------|-------------------|-------|
| r0031 | `d = free d; c = free c; ... ? para a e b d` | `'Point' object has no attribute 'num'` |
| r0044 | `d = free d; c = free c; ... ? eqratio d a e a f a f a` | `'Point' object has no attribute 'num'` |

**Root Cause:** In `_test_rule_csolver()`, the code assumes all points have a `num` attribute with coordinates. Some points may have `num = None` if numerical construction failed.

**Location:** `rule_tester.py:602`
```python
for name, point in solver.proof.symbols_graph.name2node.items():
    if isinstance(point.num, PointNum) and name in useful_points:
        points.append((name, point.num.x, point.num.y))
```

**Solution:** Add a check for `point.num is not None` before accessing coordinates:
```python
if point.num is not None and isinstance(point.num, PointNum) and name in useful_points:
```

### 3.3 Unsupported Predicate in Goal (1 rule)

| Rule ID | Rule | Error |
|---------|------|-------|
| r07 | `para a b c d, coll e a c, ncoll e a b, coll e b d => eqratio3 a b c d e e` | `eqratio3 is not supported yet` |

**Root Cause:** CSolver does not implement the `eqratio3` predicate.

**Solution:**
- **Option A (Skip):** Add `eqratio3` to unsupported predicates in `RuleConverter`
- **Option B (Implement):** Implement `eqratio3` in CSolver (requires C++ changes)

### 3.4 Fraction Argument Parsing Error (1 rule)

| Rule ID | Rule | Error |
|---------|------|-------|
| r51 | `midp a b c => rconst a b b c 1/2` | `too many values to unpack (expected 5)` |

**Root Cause:** The `rconst` predicate has a fraction argument (`1/2`) that is parsed as two separate tokens (`1` and `2`) instead of a single fraction.

**Location:** The problem is generated as `? rconst a b b c 1 2` instead of `? rconst a b b c 1/2`.

**Solution:**
- **Option A (Skip):** Add `rconst` to unsupported predicates in `RuleConverter`
- **Option B (Fix Parsing):** Modify goal parsing to handle fraction arguments

### 3.5 Geometry Construction Error (1 rule)

| Rule ID | Rule | Error |
|---------|------|-------|
| r50 | `cong a b a c, cong a d a e, cyclic b c d e, npara b c d e => cong a b a d` | `Build failed too many times, last error: PointTooFarError()` |

**Root Cause:** The numerical geometry construction fails because the constraints produce points that are too far apart or the construction is numerically unstable.

**Solution:**
- **Option A (Skip):** Skip rules that fail geometry construction
- **Option B (Retry):** Increase `max_attempts` in `GeometricSolverBuilder.build()`

---

## 4. CSolver Cannot Prove (10 rules)

These rules were successfully converted to problems and CSolver ran without errors, but failed to prove the conclusion.

### 4.1 Pappus Theorem (1 rule)

| Rule ID | Rule |
|---------|------|
| r44 | `coll a b c, coll d e b, coll d a f, coll e f g, coll h a g, coll h e c, coll i b g, coll i c f => coll d h i` |

**Analysis:** This is Pappus's theorem, a highly non-trivial projective geometry theorem. CSolver's DDAR rules may not include the necessary inference steps.

### 4.2 Parallelogram Rules (2 rules)

| Rule ID | Rule |
|---------|------|
| r0039 | `cong a b c d, para a c d b => eqangle a d a b c d c b` |
| r0040 | `cong a b c d, para a c d b => cong a d c b` |

**Analysis:** These rules describe properties of parallelograms. CSolver may lack specific parallelogram inference rules.

### 4.3 Midpoint + Perpendicular + Parallel Combinations (5 rules)

| Rule ID | Rule |
|---------|------|
| r0041 | `cong a b c b, midp d e f, para a e f c, perp a e a c => eqangle a b a d c d c b` |
| r0042 | `cong a b c b, midp d e f, para a e f c, perp a e a c => para a e b d` |
| r0043 | `cong a b c b, midp d e f, para a e f c, perp a e a c => perp a c b d` |
| r0045 | `midp a b c, para d b c e, perp d b d e => cong d a e a` |
| r0046 | `coll a b c, cong d e b e, midp f g a, para d g a b, perp d g d b => para a c e f` |

**Analysis:** These rules involve complex combinations of midpoint, perpendicular, and parallel constraints. The inference chains may be too long for CSolver's default depth limit.

### 4.4 Cyclic + Direction Constraints (2 rules)

| Rule ID | Rule |
|---------|------|
| r58 | `cong a b c d, cyclic a b e c d f, sameclock e a b f c d, sameside e a b f c d => eqangle e a e b f c f d` |
| r59 | `cong a b c d, cyclic a b e c d f, sameclock e b a f c d, nsameside e a b f c d => eqangle e a e b f c f d` |

**Analysis:** These rules involve cyclic points with direction constraints (`sameclock`, `sameside`). CSolver may not handle direction constraints properly in all cases.

---

## 5. Valid Rules Characteristics

The 13 valid rules share these characteristics:

| Characteristic | Count | Percentage |
|----------------|-------|------------|
| 1-2 premises | 7 | 53.8% |
| 3-4 premises | 3 | 23.1% |
| 5+ premises | 3 | 23.1% |

**Common patterns in valid rules:**
1. Simple predicate transformations (e.g., `cyclic => eqangle`)
2. Well-known geometric theorems (e.g., inscribed angle theorem)
3. Direct consequences of definitions (e.g., `midp => coll`)

---

## 6. Recommendations

### 6.1 Short-term Fixes (Immediate)

| Priority | Fix | Impact |
|----------|-----|--------|
| P0 | Fix Point attribute error in `rule_tester.py` | +2 rules testable |
| P1 | Add complexity filter (skip 6+ premises) | Reduce noise, faster testing |
| P2 | Add `contri`, `contrir`, `eqratio3`, `rconst` to unsupported predicates | Cleaner error reporting |

### 6.2 Medium-term Improvements

| Priority | Improvement | Impact |
|----------|-------------|--------|
| P1 | Improve C++ exception propagation | Better error diagnosis |
| P2 | Implement backtracking search for rule-to-problem conversion | +5-10% conversion success |
| P3 | Add `simtri`/`simtrir` goal support in CSolver | +6 rules potentially provable |

### 6.3 Long-term Enhancements

| Priority | Enhancement | Impact |
|----------|-------------|--------|
| P1 | Implement missing predicates (`eqratio3`, `contri`, `contrir`) | Full predicate coverage |
| P2 | Add parallelogram inference rules to CSolver | Better theorem coverage |
| P3 | Increase DDAR depth limit for complex rules | More complex theorems provable |

---

## 7. Implementation Checklist

### Immediate Actions

- [ ] Fix Point attribute error in `rule_tester.py:602`
- [ ] Add complexity filter (skip rules with 6+ premises)
- [ ] Update `RuleConverter` to skip unsupported predicates: `contri`, `contrir`, `eqratio3`, `rconst`

### Validation

After implementing fixes:
1. Re-run the 50-rule test set
2. Verify Point attribute errors are resolved
3. Verify complex rules are properly skipped
4. Document new success rate

---

## Appendix A: Full Error Classification

| Error Type | Count | Rule IDs |
|------------|-------|----------|
| Conversion failed (unsupported predicate) | 2 | r101, r102 |
| Conversion failed (complex rule) | 9 | r0033-r0049 |
| CSolver empty error | 10 | r52, r53, r62, r63, r34, r35, r12, r46, r28, r0032 |
| CSolver Point attribute error | 2 | r0031, r0044 |
| CSolver unsupported predicate | 1 | r07 |
| CSolver fraction parsing error | 1 | r51 |
| CSolver geometry construction error | 1 | r50 |
| CSolver cannot prove | 10 | r44, r0039-r0046, r58, r59 |
| **Valid** | **13** | r03, r04, r11, r19, r27, r41, r42, r43, r49, r54, r56, r60, r61 |

## Appendix B: Predicate Support Matrix

| Predicate | As Premise | As Goal | Notes |
|-----------|------------|---------|-------|
| cong | Yes | Yes | |
| para | Yes | Yes | |
| perp | Yes | Yes | |
| coll | Yes | Yes | |
| cyclic | Yes | Yes | |
| eqangle | Yes | Yes | |
| eqratio | Yes | Yes | |
| midp | Yes | Yes | |
| circle | Yes | Yes | |
| simtri | Expanded | Partial | Goals may fail |
| simtrir | Expanded | Partial | Goals may fail |
| contri | No | No | Not implemented |
| contrir | No | No | Not implemented |
| eqratio3 | No | No | Not implemented |
| rconst | No | No | Fraction parsing issue |
| sameclock | Yes (skip) | N/A | No construction needed |
| ncoll | Yes (skip) | N/A | No construction needed |
| npara | Yes (skip) | N/A | No construction needed |
| sameside | Yes (skip) | N/A | No construction needed |
| nsameside | Yes (skip) | N/A | No construction needed |
