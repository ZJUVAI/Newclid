# GRPO Iteration Status and Next Plan

Last updated: 2026-04-19

## Background

- Base model: `vlm_sft44` at `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- Raw source data: `/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
- Current training entrypoint: `scripts/grpo/train_grpo.sh`
- Current selector entrypoint: `scripts/grpo/select_debug_set.py`
- Current diagnosis: the main blocker is still data distribution, not GRPO training hyperparameters

## Current Gate

All new GRPO dataset iterations use the same smoke gate on the first 50 metric steps:

- `first50_avg_frac_reward_zero_std <= 0.40`
- `first50_median_reward_std >= 0.20`
- `max_consecutive_full_zero_std_steps <= 3`

Only datasets that pass all three gates are allowed to continue to `300-step` training and evaluation.

## Version Review

### `v3_tiered`

- Dataset: `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v3`
- Selector policy: `v3_tiered`
- Static result:
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.6785`
  - `selected_nonzero_pass_ratio = 0.3215`
  - `selected_avg_unique_aux_count = 1.873`
- Main issue:
  - the selected pool was dominated by `pass@16 = 0` rows (`1357 / 2000`)
  - this made the dataset structurally large enough but reward-diversity-poor
- Smoke result:
  - run: `models/grpo_vlm_sft44_v3_smoke_s1_single/v1-20260419-112703`
  - `first50_avg_frac_reward_zero_std = 0.6136`
  - `first50_median_reward_std = 0.0`
  - `max_consecutive_full_zero_std_steps = 7`
- Conclusion:
  - `v3` fails clearly
  - the old hard-valid fallback admitted too many pass-zero rows and collapsed GRPO reward variance

### `v4_reward_mixed`

- Dataset: `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v4_rewardmix_800`
- Selector policy: `v4_reward_mixed`
- Static result:
  - `selected_rows = 800`
  - `selected_zero_pass_ratio = 0.20375`
  - `selected_reward_mixed_zero_ratio = 0.20375`
  - `selected_avg_proxy_reward_std = 0.3512`
  - `selected_median_proxy_reward_std = 0.3248`
- Main improvement:
  - replacing generic pass-zero fallback with `reward_mixed_zero` was the right direction
  - zero-pass share dropped from `67.85%` to `20.38%`
- Main limitation:
  - the dataset stayed too small at `800` rows
  - this version was useful as a selector proof-of-concept, not as the final 2k training set
- Conclusion:
  - reward-mixed filtering is necessary
  - but `v4` does not answer whether a 2k-scale dataset can still maintain good reward variance

### `v5_rewardmix_2k`

- Dataset: `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v5_rewardmix_2k`
- Label source:
  - reused overlapping labels from `v2_relaxed`
  - relabeled the delta and merged to `100k` rows
- Selector policy: `v4_reward_mixed`
- Static result:
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.1685`
  - `selected_reward_mixed_zero_ratio = 0.1685`
  - `selected_nonzero_pass_ratio = 0.8315`
  - `selected_avg_proxy_reward_std = 0.3595`
  - `selected_median_proxy_reward_std = 0.3476`
  - no structural shortages remained in the selector report
- Smoke result:
  - main run: `models/grpo_vlm_sft44_v5_rewardmix_s1_4gpu_256/v1-20260419-195804`
  - `first50_avg_frac_reward_zero_std = 0.4375`
  - `first50_median_reward_std = 0.1833`
  - `max_consecutive_full_zero_std_steps = 1`
- Fallback checks:
  - `ng4` run was worse than main smoke
  - `max_len=192` run also failed to recover the gate
- Conclusion:
  - moving from `v4` to `v5` proved that larger scale alone is not enough
  - the failure pattern suggests the bottleneck is not mainly `num_generations` or `max_completion_length`
  - data composition is still the first-order problem

### `v6_mid_strict_zero`

- Dataset: `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v6_midpass_2k`
- Selector policy: `v6_mid_strict_zero`
- Design goal:
  - keep the stricter `reward_mixed_zero` filter
  - narrow the core window to the mid pass band
  - split higher-pass non-mastered rows into separate capped tiers
- Static result:
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.10`
  - `selected_reward_mixed_zero_ratio = 0.10`
  - `selected_nonzero_pass_ratio = 0.90`
  - `selected_avg_proxy_reward_std = 0.3663`
  - `selected_median_proxy_reward_std = 0.3476`
  - `selected_avg_valid_ratio = 0.8333`
  - `multi_point_shortage = 137`
  - high-pass tail stayed heavy:
    - `0.8125 = 153`
    - `0.8750 = 118`
    - combined `0.8125 + 0.8750 = 271`
- Smoke result:
  - run: `models/grpo_vlm_sft44_v6_midpass_s1_4gpu_256/v0-20260419-210740`
  - smoke gate file: `models/grpo_vlm_sft44_v6_midpass_s1_4gpu_256/v0-20260419-210740/smoke_gate_first50.json`
  - `first50_avg_frac_reward_zero_std = 0.4125`
  - `first50_median_reward_std = 0.2054`
  - `max_consecutive_full_zero_std_steps = 0`
- Comparison against `v5` main smoke:
  - `avg_frac_reward_zero_std`: `0.4375 -> 0.4125`
  - `median_reward_std`: `0.1833 -> 0.2054`
  - `avg_reward`: `0.6164 -> 0.6626`
  - `mean_length`: `50.88 -> 48.44`
- Conclusion:
  - `v6` is better than `v5`
  - but it still fails the smoke gate because `0.4125 > 0.40`
  - selector-only changes help, but they are not sufficient

### `v7_structure_strict_zero`

- Dataset: `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v7_structure_2k`
- Prefilter changes:
  - expanded candidate pool target to `150k`
  - switched the top-level structure budget from `multi_aux/single_aux` to `multi_point/single_point`
  - targeted `multi_point = 70%`, but the realized prefilter ratio was supply-limited at `44.35%`
- Label source:
  - fast-path union of prior labels:
    - `v5_merged_100k = 100000`
    - `v2_relaxed_extra = 13350`
  - merged label pool size: `113350`
  - label model remains `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
- Selector policy: `v7_structure_strict_zero`
- Static result:
  - `selected_rows = 2000`
  - `selected_zero_pass_ratio = 0.10`
  - `selected_reward_mixed_zero_ratio = 0.10`
  - `selected_nonzero_pass_ratio = 0.90`
  - `selected_avg_proxy_reward_std = 0.3711`
  - `selected_median_proxy_reward_std = 0.3476`
  - `selected_avg_valid_ratio = 0.8267`
  - `selected_avg_unique_aux_count = 2.1115`
  - `multi_point_shortage = 61`
  - high-pass tail improved:
    - `0.8125 + 0.8750 = 200`
- Smoke result:
  - run: `models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401`
  - smoke gate file: `models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401/smoke_gate_first50.json`
  - comparison file: `models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401/compare_vs_v6_v5_first50.json`
  - `first50_avg_frac_reward_zero_std = 0.2900`
  - `first50_median_reward_std = 0.2562`
  - `max_consecutive_full_zero_std_steps = 0`
- Comparison against `v6` smoke:
  - `avg_frac_reward_zero_std`: `0.4125 -> 0.2900`
  - `median_reward_std`: `0.2054 -> 0.2562`
  - `avg_reward`: `0.6626 -> 0.6162`
  - `mean_length`: `48.44 -> 46.46`
- Conclusion:
  - `v7` is the first dataset iteration that passes the unified 50-step smoke gate
  - the main win comes from reward-variance stability, not higher mean reward
  - the next stage is `300-step` training on the same dataset and hyperparameters

## Current Diagnosis

The evidence from `v3 -> v7` now supports four conclusions:

1. Reducing pass-zero contamination is necessary.
   `v3` failed because it admitted too many `pass@16 = 0` samples.

2. Reducing pass-zero contamination alone is not sufficient.
   `v6` cut zero-pass share to `10%`, but still failed the smoke gate.

3. Candidate-pool structure matters as much as selector policy.
   `v7` only passed after widening the prefilter pool and explicitly biasing toward `multi_point` structure.

4. The current blocker has shifted from dataset construction to training stability validation.
   `v7` has already cleared the 50-step gate, so the next question is whether that signal survives mid-training.

## Current Mainline: `v7` Promotion

### Why `300-step` Is The Next Gate

The historical `v1` GRPO run shows why `50-step` is not enough:

- `first50_avg_frac_reward_zero_std = 0.29`
- `first50_median_reward_std = 0.3677`
- but by `300-step`, the same run had already collapsed into persistent zero-variance behavior

So the current promotion path is:

1. `v7` smoke pass at `checkpoint-50`
2. true resume to `checkpoint-300`
3. evaluate `checkpoint-300` on `dev_imo`
4. only if the mid-training trace stays healthy, true resume to `checkpoint-500`
5. evaluate `checkpoint-500` on `dev_imo`, then `imo_95`

### `v7` Promotion Rules

Keep the successful smoke settings fixed during promotion:

- `CUDA_VISIBLE_DEVICES=0,1,2,3`
- `num_generations = 8`
- `temperature = 0.9`
- `top_k = 50`
- `beta = 0.04`
- `max_completion_length = 256`
- `reward_log_interval = 20`

Use true checkpoint resume rather than model-only restart:

- `checkpoint-50 -> checkpoint-300`
- `checkpoint-300 -> checkpoint-500`

Decision rule:

- if the `300-step` trace stays stable and `dev_imo` remains acceptable, continue to `500-step`
- if the `300-step` trace regresses toward the historical `v1` failure pattern, stop promotion and return to data iteration

## Active Artifacts

- Main evaluation report:
  - `docs/grpo_imo95_evaluation_report.md`
- `v5` dataset report:
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v5_rewardmix_2k/grpo_train_report_2000.json`
- `v6` dataset report:
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v6_midpass_2k/grpo_train_report_2000.json`
- `v7` prefilter report:
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v7_structure_2k/candidate_pool_prefilter_report_150k.json`
- `v7` merged-label report:
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v7_structure_2k/difficulty_labels_union_v2_v5_113k_report.json`
- `v7` dataset report:
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v7_structure_2k/grpo_train_report_2000.json`
- `v6` smoke gate:
  - `models/grpo_vlm_sft44_v6_midpass_s1_4gpu_256/v0-20260419-210740/smoke_gate_first50.json`
- `v7` smoke gate:
  - `models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401/smoke_gate_first50.json`
- `v7` vs `v6/v5` smoke comparison:
  - `models/grpo_vlm_sft44_v7_structure_s1_4gpu_256/v0-20260419-213401/compare_vs_v6_v5_first50.json`
- historical long-run GRPO baseline:
  - `models/grpo_vlm_sft44_505_run1/v1-20260417-084328`

## Recent Conclusion

- `v7` is now the best GRPO data iteration so far.
- `v7` is the first dataset that passes the unified 50-step smoke gate.
- The project should stop selector-only fallback work on `v5/v6`.
- The active mainline is now `v7` promotion:
  - run `300-step`
  - if stable, continue to `dev_imo`
  - then continue to `imo_95`
- Git hygiene for this phase:
  - track the two docs under `docs/`
  - do not stage temporary benchmark resume files, monitor logs, or one-off recovery helpers
