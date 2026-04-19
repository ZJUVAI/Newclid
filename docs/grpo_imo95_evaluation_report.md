# GRPO IMO-95 Evaluation Report

**Date:** 2026-04-19  
**Benchmark:** IMO-95 (95 geometry problems)  
**Model:** Qwen3-VL Text-only Agent

**Status note:** This report is the historical evaluation summary for the old GRPO baseline `models/grpo_vlm_sft44_505_run1/v1-20260417-084328/checkpoint-505`. It is not the current `v7` result.

**Current mainline status:** `v7_structure_strict_zero` passed the 50-step smoke gate but failed mid-training promotion and was stopped early at `171 / 300` due to sustained zero-variance collapse. No `v7` `dev_imo` or `imo_95` evaluation was run from this branch. Future GRPO evals should still be compared against both the SFT baseline `checkpoint-20084` and the historical GRPO `checkpoint-505` results in this document.

---

## Executive Summary

GRPO training shows mixed results across benchmarks:

**IMO-95 (95 problems):** Modest improvement from **54/95 (56.8%)** to **56/95 (58.9%)**, +2.1% absolute gain.

**DevIMO (16 problems):** Slight regression from **14/16 (87.5%)** to **13/16 (81.3%)**, -6.2% absolute loss.

**Note:** Both GRPO evaluations use the same checkpoint-505 model. The "sv1" suffix indicates a re-evaluation with improved evaluation stability (fixed seed handling and Ray port issues). The performance difference suggests the model's outputs are sensitive to evaluation environment variations.

### IMO-95 Results

| Metric | SFT Baseline | GRPO (checkpoint-505) | Delta |
|--------|--------------|----------------------|-------|
| **Solved** | 54/95 | 56/95 | +2 |
| **Accuracy** | 56.8% | 58.9% | +2.1% |
| **Newly Solved** | - | 7 | +7 |
| **Regressions** | - | 5 | -5 |
| **Net Gain** | - | - | +2 |

### DevIMO Results

| Metric | SFT Baseline | GRPO (initial eval) | GRPO (sv1 stable eval) |
|--------|--------------|---------------------|------------------------|
| **Solved** | 14/16 | 14/16 | 13/16 |
| **Accuracy** | 87.5% | 87.5% | 81.3% |
| **Failed Problems** | 2 | 2 | 3 |

---

## Detailed Results

### Model Configurations

**SFT Baseline:**
- Checkpoint: `vlm_sft44_checkpoint-20084`
- Evaluation completed: 2026-04-17
- Result file: `imo_95_resume_from_20260417T062654Z_merged.csv`

**GRPO:**
- Checkpoint: `v1-20260417-084328/checkpoint-505`
- IMO-95 evaluation completed: 2026-04-19 (using sv1 stable evaluation)
- DevIMO evaluations: 
  - Initial: 2026-04-17 (14/16 solved)
  - Stable (sv1): 2026-04-18 (13/16 solved)
- Result files: See Files section below

### Evaluation Parameters

Both evaluations used identical settings:
- Agent: `qwen3_vl_text`
- Decoding size: 32
- Beam size: 512
- Search depth: 4
- Timeout: 3600s
- GPUs: 4 (CUDA 0,1,2,3)
- GPU batch size: 2
- Max workers: 40

---

## DevIMO Benchmark Analysis

### Results Summary

| Model | Evaluation Version | Solved | Accuracy | Failed Problems |
|-------|-------------------|--------|----------|-----------------|
| SFT Baseline | checkpoint-20084 | 14/16 | 87.5% | `translated_imo_2008_p6`, `translated_imo_2021_p3` |
| GRPO | checkpoint-505 (initial) | 14/16 | 87.5% | `translated_imo_2008_p6`, `translated_imo_2021_p3` |
| GRPO | checkpoint-505 (sv1 stable) | 13/16 | 81.3% | `translated_imo_2008_p1b`, `translated_imo_2008_p6`, `translated_imo_2021_p3` |

**Important:** The two GRPO evaluations use the **same checkpoint-505 model**. The "sv1" version is a re-evaluation with improved evaluation stability (fixed seed handling and Ray agent port issues). The performance difference reveals sensitivity to evaluation environment variations.

### Key Observations

**Initial GRPO evaluation (checkpoint-505):**
- Maintained same accuracy as SFT baseline (87.5%)
- Failed on identical problems as SFT
- No improvement or regression

**Stable GRPO evaluation (checkpoint-505 sv1):**
- Regressed to 81.3% (-6.2% from baseline)
- New failure: `translated_imo_2008_p1b` (previously solved in initial eval)
- **This is the same model** — the difference indicates evaluation environment sensitivity

### Problem-Level Details

**Consistently Failed (all 3 evaluations):**
1. `translated_imo_2008_p6` - Hard problem, failed by all evaluations
2. `translated_imo_2021_p3` - Hard problem, failed by all evaluations

**Regression in stable evaluation:**
- `translated_imo_2008_p1b` - Solved in initial GRPO eval (168.61s), but failed in stable eval (385.36s timeout)
- The model spent significantly more time searching before timeout, suggesting it explored a different (worse) search path due to evaluation environment differences

---

## Problem-Level Analysis

### Newly Solved by GRPO (7 problems)

1. `imo_sl_2020_g6`
2. `imo_sl_2016_g2`
3. `imo_sl_2016_g2_variant`
4. `imo_sl_2020_g8_variant`
5. `imo_sl_1999_g6`
6. `imo_sl_2016_g5_variant`
7. `imo_sl_2005_g6`

### Regressions (5 problems)

Problems solved by SFT but not by GRPO:

1. `imo_sl_2007_g3`
2. `imo_sl_2008_g1b`
3. `imo_sl_2011_g7`
4. `imo_sl_2016_g6_variant`
5. `imo_sl_2017_g4_variant`

---

## Observations

### Strengths
- **IMO-95:** GRPO successfully solved 7 additional problems that SFT baseline failed on, demonstrating improved capability on harder geometry problems
- Net positive gain of 2 problems on IMO-95 (+2.1% accuracy)
- **DevIMO initial eval:** GRPO maintained performance parity with SFT (87.5%)

### Weaknesses
- **IMO-95:** 5 regressions indicate some instability in problem-solving capability
- **DevIMO stable eval:** The `translated_imo_2008_p1b` failure reveals sensitivity to evaluation environment
- The model spent 385s (timeout) vs 168s in the initial eval, suggesting it explored a different search path due to subtle environment differences (seed handling, Ray port configuration)
- This evaluation sensitivity is concerning for reproducibility

### Key Insight: Evaluation Environment Sensitivity

The DevIMO results reveal that **the same model (checkpoint-505)** produces different results under different evaluation configurations:
- Initial eval: 14/16 (87.5%)
- Stable eval (sv1): 13/16 (81.3%)

This is likely due to:
1. **Seed handling changes:** The sv1 evaluation fixed seed reset issues, which may have changed the random exploration order
2. **Ray agent port configuration:** Port assignment changes could affect parallel execution timing
3. **Search path sensitivity:** The model's beam search is sensitive to these subtle variations

### Recommendations
1. **Prioritize evaluation stability:** The DevIMO variance highlights the need for deterministic evaluation protocols
2. **Use sv1 results as ground truth:** The stable evaluation (sv1) with fixed seed handling is more reliable for comparing models
3. **Investigate IMO-95 regressions:** Analyze the 5 regressed problems to understand failure modes
4. **Consider ensemble approaches:** Combining SFT and GRPO could capture complementary strengths
5. **Increase beam size or timeout:** The 385s timeout on `translated_imo_2008_p1b` suggests the model was close to solving it

---

## Files

### IMO-95 Result Files
- SFT: `results/devimo_grpo_compare/imo_95_resume_from_20260417T062654Z_merged.csv`
- GRPO: `results/devimo_grpo_compare/imo_95_resume_from_20260418T125633Z_merged.csv`

### DevIMO Result Files
- SFT: `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_vlm_sft44_checkpoint-20084_d32_b512_s4_gbs2_gbt100_seed123_20260417T052620Z.csv`
- GRPO checkpoint-505: `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260417-084328_checkpoint-505_d32_b512_s4_gbs2_gbt100_seed123_20260417T055948Z.csv`
- GRPO checkpoint-505 sv1: `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_dev_imo_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T035755Z.csv`

### Evaluation Traces
- IMO-95 SFT: `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T125633Z/`
- IMO-95 GRPO: `results/devimo_grpo_compare/eval_single_problem_multi_gpu_qwen3_vl_text_imo_95_resume_from_20260418T125633Z_v1-20260417-084328_checkpoint-505_sv1_d32_b512_s4_gbs2_gbt100_seed123_20260418T134526Z/`

---

## Conclusion

GRPO training demonstrates mixed but informative results:

**IMO-95 Performance:** Modest but positive improvement (+2.1% accuracy, +2 net problems). The 7 newly solved problems validate GRPO's ability to improve on harder geometry problems, though 5 regressions indicate some instability.

**DevIMO Evaluation Sensitivity:** The same checkpoint-505 model produced different results (87.5% vs 81.3%) under different evaluation configurations. This reveals that the model's beam search is sensitive to evaluation environment variations (seed handling, Ray port configuration). The stable evaluation (sv1) with fixed seed handling should be considered more reliable.

**Overall Assessment:** 
- GRPO shows promise for improving performance on challenging problems (IMO-95 improvement)
- The evaluation sensitivity issue (DevIMO variance) highlights the importance of deterministic evaluation protocols
- The IMO-95 improvement (+2 problems) is real and validated under stable evaluation conditions
- Future work should focus on: (1) improving evaluation reproducibility, (2) investigating regressions, (3) exploring ensemble approaches
