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

## Current Diagnosis

The evidence from `v3 -> v6` supports three conclusions:

1. Reducing pass-zero contamination is necessary.
   `v3` failed because it admitted too many `pass@16 = 0` samples.

2. Reducing pass-zero contamination alone is not sufficient.
   `v6` cut zero-pass share to `10%`, but still failed the smoke gate.

3. The remaining failure now comes from the candidate-pool ceiling and structure mix.
   In `v6`, the high-pass tail is too heavy and `multi_point` coverage is too weak, so the selected 2k rows are cleaner but still not the right training signal.

Current working hypothesis:

- The candidate pool before difficulty labeling is too narrow for the selector to form a truly balanced 2k set.
- `v6` exhausted the useful selector-only edits.
- The next iteration must change prefilter, label reuse / relabel scope, and selector together.

## Next Iteration: `v7`

### Goal

Build a new 2k training set that:

- keeps `reward_mixed_zero <= 10%`
- keeps the high-pass tail (`0.8125 + 0.8750`) under tighter control
- repairs the `multi_point` shortage
- passes the unified 50-step smoke gate before any longer training

### `v7` Data Flow

1. Rebuild the prefiltered pool from the original 1M raw source.
2. Increase prefilter target size from `100k` to `150k-200k`.
3. Reuse any overlapping difficulty labels from prior versions where safe.
4. Relabel the new delta with the same label model:
   `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`
5. Keep difficulty resolution at `pass@16`.
6. Run a new selector over the enlarged merged label pool to produce a `v7` 2k set.

### `v7` Prefilter Changes

Modify `scripts/grpo/prefilter_candidate_pool.py` so that the structural budget is no longer controlled only by `multi_aux` vs `single_aux`.

Required changes:

- Add an explicit `multi_point` distinction based on `aux_points_total >= 2`
- Allocate the top-level prefilter budget with a stronger bias toward `multi_point`
- Keep complexity and family balancing, but do not allow `single_point` rows to dominate through abundance

Default target distribution for `v7` prefilter:

- `multi_point = 70%`
- `single_point = 30%`

### `v7` Selector Changes

Modify `scripts/grpo/select_debug_set.py` with a new selector iteration that keeps the `v6` zero-pass strictness but adds harder control over the high-pass tail and structural ranking.

Required changes:

- keep `reward_mixed_zero <= 10%`
- keep `core` centered on `0.125 - 0.625`
- allow `near_low` for `0.0625`
- retain capped `near_high_mid` and `near_high_high`
- explicitly rank structural strength ahead of pass-distance preference:
  - `aux_points_total >= 2`
  - `aux_segment_count >= 2`
  - `unique_aux_count`
  - then proxy reward variance and pass distance

Required high-pass constraint:

- selected `0.8125 + 0.8750 <= 200` rows

### `v7` Static Acceptance Criteria

The `v7` selected dataset must satisfy all of the following before training:

- `selected_rows = 2000`
- `selected_zero_pass_ratio <= 0.10`
- `selected_nonzero_pass_ratio >= 0.88`
- `selected_reward_mixed_zero_ratio <= 0.10`
- `selected_avg_unique_aux_count >= 2.0`
- `selected_median_proxy_reward_std >= 0.3476`
- `multi_point_shortage <= 20`
- `0.8125 + 0.8750 <= 200`

### `v7` Training Plan

Do not sweep training hyperparameters at the same time as the `v7` data change.

The first `v7` smoke run must keep the same training setup as `v6` main smoke:

- `CUDA_VISIBLE_DEVICES=0,1,2,3`
- `num_generations = 8`
- `temperature = 0.9`
- `top_k = 50`
- `beta = 0.04`
- `max_completion_length = 256`
- `reward_log_interval = 20`
- `max_steps = 50`

Decision rule:

- pass the unified smoke gate: continue to `300-step`
- fail the unified smoke gate: stop and return to data iteration

Only if the `300-step` run also looks stable should `v7` continue to:

1. `dev_imo`
2. `imo_95`

## Active Artifacts

- Main evaluation report:
  - `docs/grpo_imo95_evaluation_report.md`
- `v5` dataset report:
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v5_rewardmix_2k/grpo_train_report_2000.json`
- `v6` dataset report:
  - `datasets/grpo_pipeline_vlm_sft44_1m_textonly_20k_v6_midpass_2k/grpo_train_report_2000.json`
- `v6` smoke gate:
  - `models/grpo_vlm_sft44_v6_midpass_s1_4gpu_256/v0-20260419-210740/smoke_gate_first50.json`
- `v6` vs `v5` smoke comparison:
  - `models/grpo_vlm_sft44_v6_midpass_s1_4gpu_256/v0-20260419-210740/compare_vs_v5_main_first50.json`

## Recent Conclusion

- `v6` is the best selector-only iteration so far.
- `v6` still does not pass the unified smoke gate.
- The project should not spend more time on `v6` fallback sweeps.
- The active mainline is now `v7`: wider prefilter, merged relabeling, and a structure-aware selector.
