# GRPO Aux Reward

Chinese version: [README_zh.md](/C20545/home/wangzi/GenesisGeo-grpo/scripts/grpo/README_zh.md)

This directory contains the data-selection, reward, and launch helpers for GRPO-based auxiliary-point generation.

## Scripts

- `plugin.py`: registers `aux_reward` for SWIFT.
- `../analyze_dataset.py`: annotates JSONL rows with aux structure, goal predicate, predicate family tags, and lightweight complexity fields.
- `analyze_selected_dataset.py`: analyzes the final selected GRPO training JSONL after `select_debug_set.py`.
- `build_candidate_pool.py`: keeps only rows with real aux targets and emits a candidate pool summary.
- `prefilter_candidate_pool.py`: applies a cheap streaming prefilter to large candidate pools before model-based difficulty labeling.
- `label_difficulty.py`: text-model difficulty labeling with offline generation plus reward evaluation.
- `label_difficulty_vlm.py`: VLM-compatible difficulty labeling with batch inference and multi-GPU support.
- `select_grpo_dataset.sh`: one-click wrapper for the full dataset-selection pipeline.
- `select_debug_set.py`: filters mastered/dead rows and builds the final GRPO subset.
- `prepare_grpo_aux_dataset.py`: converts existing JSONL data into `query/fl_problem/response` rows for aux-only GRPO and drops rows without `<aux>...</aux>`.
- `train_grpo.sh`: GRPO launch template built on top of `swift rlhf`.
- `src/newclid/training/grpo_rewards.py`: composite reward evaluator.

## Required Dataset Fields

The full GRPO pipeline starts from JSONL data with these source fields:

- `llm_input_renamed`: model prompt / query
- `llm_output_renamed`: model response
- `fl_problem`: original buildable geometry problem

The final training dataset used by SWIFT must contain:

- `query`
- `fl_problem`
- `response`

`response` should be an aux-only target such as `<aux> x00 i : ... ; </aux>`.

## End-to-End Data Pipeline

Recommended full pipeline:

```text
raw JSONL
-> analyze_dataset.py
-> build_candidate_pool.py
-> prefilter_candidate_pool.py
-> label_difficulty.py / label_difficulty_vlm.py
-> select_debug_set.py
-> analyze_selected_dataset.py
-> train_grpo.sh
```

### 1. Annotate the raw dataset

This extracts:

- whether a row contains a valid aux block
- aux segment count and aux point count
- goal predicate and predicate family tags
- `n_premises`, `problem_predicate_count`, and `problem_clause_count`

```bash
python scripts/analyze_dataset.py \
  datasets/raw.jsonl \
  --annotations-output datasets/grpo/annotated.jsonl \
  --summary-output datasets/grpo/annotated_summary.json
```

### 2. Build the candidate pool

This keeps only rows with real aux targets and rewrites them into `query / fl_problem / response` format while preserving the balancing metadata.

```bash
python scripts/grpo/build_candidate_pool.py \
  datasets/grpo/annotated.jsonl \
  datasets/grpo/candidate_pool.jsonl \
  --summary-output datasets/grpo/candidate_pool_summary.json
```

### 3. Prefilter large pools

This stage is meant to reduce a large pool before model-based labeling. The goal is not to find the final training set directly, but to cheaply build a smaller, more diverse candidate pool for the expensive difficulty-labeling step.

The current implementation does four things:

1. Exact-query deduplication.
   Only the first occurrence of each `query` is counted when building the pool statistics, so repeated prompts do not dominate the sample budget.

2. Assign each row to a 3D bucket.
   Every sample is bucketed by:
   - aux shape
     `multi_aux` if `aux_segment_count >= 2` or `aux_points_total >= 2`, otherwise `single_aux`
   - premise complexity
     `p8_plus` if `n_premises >= 8`, `p5_7` if `n_premises >= 5`, otherwise `p0_4`
     if `n_premises` is missing, the script falls back to `problem_clause_count`
   - primary family
     inferred from `goal_predicate` first, then from the first `predicate_family_tags` entry, otherwise `other_family`

3. Allocate per-bucket quotas before sampling.
   The script first splits the global `target_size` by aux shape:
   - `60%` for `multi_aux`
   - `40%` for `single_aux`

   Then, inside each aux bucket, it splits the budget again by premise complexity:
   - `60%` for `p8_plus`
   - `30%` for `p5_7`
   - `10%` for `p0_4`

   For each `(aux_shape, premise_bucket)` slice, the quota is divided as evenly as possible across all available families in that slice.

4. Sample with reservoir selection, then fill shortages.
   For buckets that have enough rows, the script uses reservoir sampling so the result stays deterministic under a fixed `--seed` while remaining stream-friendly for large datasets.
   If some buckets do not have enough rows to meet their quota, the script does a fallback fill from the remaining rows until `target_size` is reached.

During the fallback fill, the script also applies a per-goal cap:

- `goal_cap = 20% * target_size`

This cap is enforced on `goal_predicate` so one goal type does not completely take over the final prefiltered pool.

The output report records:

- distinct-query count before sampling
- exact duplicate count removed
- target quota for each bucket
- actual bucket counts after sampling
- per-bucket shortages
- selected goal-predicate distribution
- how many fallback rows were skipped due to the goal cap

```bash
python scripts/grpo/prefilter_candidate_pool.py \
  datasets/grpo/candidate_pool.jsonl \
  datasets/grpo/candidate_pool_prefiltered.jsonl \
  --report-output datasets/grpo/candidate_pool_prefilter_report.json \
  --target-size 50000
```

### 4. Label difficulty with the current model

This runs offline generation and scores the generated aux completions with the GRPO reward, producing fields such as:

- `greedy_success`
- `pass_at_16`
- `ddar_valid_count`
- `ddar_solved_count`
- `all_invalid`

Text model version:

```bash
python scripts/grpo/label_difficulty.py \
  datasets/grpo/candidate_pool_prefiltered.jsonl \
  datasets/grpo/difficulty_labels.jsonl \
  --model-path /path/to/text-checkpoint
```

VLM version:

```bash
python scripts/grpo/label_difficulty_vlm.py \
  datasets/grpo/candidate_pool_prefiltered.jsonl \
  datasets/grpo/difficulty_labels.jsonl \
  --model-path /path/to/vlm-checkpoint
```

### 5. Select the final GRPO subset

The selector supports three policies.

`v3_tiered` keeps the earlier tiered policy:

- `core`: non-mastered rows with non-trivial but still learnable pass rates
- `near`: rows just outside the core window, either slightly harder or slightly easier
- `hard_valid_high`: `pass_at_* = 0` rows that still look learnable because invalidity is low and aux diversity is acceptable
- `hard_valid_mid`: `pass_at_* = 0` rows that are valid but less diverse
- `mastered`: high-pass rows reserved only as a small fallback when the selector still cannot fill enough examples

`v4_reward_mixed` is stricter about `pass_at_* = 0` rows.
It keeps the same `core` and `near` tiers, but only admits zero-pass rows into
`reward_mixed_zero` when offline labels show genuinely mixed reward outcomes
instead of the degenerate `valid_at_* ~= 1, pass_at_* = 0` pattern that often
produces `reward_std = 0` during training.

`v6_mid_strict_zero` is a selector-only refinement that narrows the learnable
core and separates the easier high-pass tail into two capped tiers:

- `core`: `0.125 <= pass_at_* <= 0.625`
- `near_low`: low-pass rows just below the core window
- `reward_mixed_zero`: stricter zero-pass rows with mixed reward outcomes
- `near_high_mid`: moderate high-pass rows above core and up to a configurable cap
- `near_high_high`: higher-pass but still non-mastered rows, kept under a tighter cap
- `mastered`: only used as fallback if the selector still cannot fill enough rows

`v9_stage_balanced` builds on top of `v6/v7` and explicitly enforces minimum
coverage for low-pass and high-pass boundary tiers so the final training set
does not collapse into almost all `core` rows:

- `core`: `0.125 <= pass_at_* <= 0.625`
- `near_low`: lower-pass boundary rows below core
- `reward_mixed_zero`: zero-pass rows that still satisfy validity, reward-mixing, and diversity constraints
- `near_high_mid`: `0.625 < pass_at_* <= 0.75`
- `near_high_high`: `0.75 < pass_at_* < mastered`
- `mastered`: only used as fallback when the selector still cannot fill enough rows

The `v3_tiered` policy first groups rows into:

- `core`
- `near`
- `hard_valid_high`
- `hard_valid_mid`
- `mastered`

It always removes:

- mastered rows: `greedy_success == true` and very high `pass_at_16`
- dead rows: `all_invalid == true`

It then constructs a balanced subset for actual GRPO training while enforcing:

- minimum multi-segment and multi-point coverage
- minimum predicate-family coverage
- a per-goal cap so one goal type cannot dominate
- explicit caps on `hard_valid_high`, `hard_valid_mid`, and mastered fallback rows

The JSON report records tier availability, tier-selected counts, selected pass histogram,
pass-zero vs nonzero share, mastered share, and diversity statistics such as
`unique_aux_count` and `duplicate_aux_ratio`.

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo/difficulty_labels.jsonl \
  datasets/grpo/grpo_train_selected.jsonl \
  --report-output datasets/grpo/grpo_train_report.json \
  --target-size 2000
```

For the stricter zero-pass filter:

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo/difficulty_labels.jsonl \
  datasets/grpo/grpo_train_selected.jsonl \
  --report-output datasets/grpo/grpo_train_report.json \
  --selection-policy v4_reward_mixed \
  --target-size 800 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.875 \
  --zero-pass-reward-std-min 0.15 \
  --reward-mixed-zero-max-fraction 0.25
```

For the mid-band focused selector:

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo/difficulty_labels.jsonl \
  datasets/grpo/grpo_train_selected.jsonl \
  --report-output datasets/grpo/grpo_train_report.json \
  --selection-policy v6_mid_strict_zero \
  --target-size 2000 \
  --core-pass-min 0.125 \
  --core-pass-max 0.625 \
  --near-high-mid-max-pass 0.75 \
  --zero-valid-min 0.25 \
  --zero-valid-max 0.75 \
  --zero-pass-reward-std-min 0.20 \
  --reward-mixed-zero-max-fraction 0.10 \
  --near-high-mid-max-fraction 0.15 \
  --near-high-high-max-fraction 0.14
```

The output rows contain exactly:

- `query`
- `fl_problem`
- `response`

You can analyze the selected dataset without reintroducing selection metadata:

```bash
python scripts/grpo/analyze_selected_dataset.py \
  datasets/grpo/grpo_train_selected.jsonl \
  --annotations-output datasets/grpo/grpo_train_selected_annotated.jsonl \
  --summary-output datasets/grpo/grpo_train_selected_summary.json
```

This script recomputes the same derived geometry statistics directly from `query`, `fl_problem`, and `response`, including:

- goal predicate distribution
- predicate family distribution
- aux segment / aux point distributions
- problem predicate count distribution
- problem clause count distribution

### One-Click Dataset Selection

If you want to run the whole selection chain in one command, use:

```bash
INPUT_PATH=datasets/raw.jsonl \
MODEL_PATH=/path/to/checkpoint \
OUTPUT_DIR=datasets/grpo_pipeline \
LABELER=text \
bash scripts/grpo/select_grpo_dataset.sh
```

The wrapper runs:

```text
analyze_dataset.py
-> build_candidate_pool.py
-> prefilter_candidate_pool.py
-> label_difficulty.py / label_difficulty_vlm.py
-> select_debug_set.py
-> analyze_selected_dataset.py
```

Useful environment variables:

- `INPUT_PATH`: source JSONL with `llm_input_renamed`, `llm_output_renamed`, and `fl_problem`
- `MODEL_PATH`: checkpoint used for offline difficulty labeling
- `OUTPUT_DIR`: directory for all intermediate and final artifacts
- `LABELER`: `text` or `vlm`
- `PREFILTER_TARGET_SIZE`: defaults to `50000`
- `FINAL_TARGET_SIZE`: defaults to `2000`
- `SEED`: defaults to `998244353`
- `LABEL_NUM_SAMPLES`: defaults to `16`
- `LABEL_TEMPERATURE`: defaults to `0.8`
- `LABEL_TOP_P`: defaults to `0.95`

Main outputs:

- `grpo_train_selected.jsonl`: final training dataset
- `grpo_train_report.json`: selection report from `select_debug_set.py`
- `grpo_train_selected_summary.json`: recomputed stats for the final dataset

### Current `vlm_sft44` Provenance

For the current `vlm_sft44` GRPO experiments in this repo:

- raw source JSONL:
  `/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new_remove_proof.jsonl`
- VLM difficulty-label checkpoint:
  `/C20545/home/wangzi/GenesisGeo_data_models/models/vlm_sft44/checkpoint-20084`

The existing `grpo_pipeline_vlm_sft44_1m_textonly_20k*` artifacts were produced from that
raw source through `build_candidate_pool.py -> prefilter_candidate_pool.py -> label_difficulty_vlm.py`.

## Fast Path From Existing SFT Data

If you already have a cleaned SFT-style dataset and only need an aux-only GRPO dataset, skip the full selection pipeline and extract the first valid aux block directly:

```bash
python scripts/grpo/prepare_grpo_aux_dataset.py \
  datasets/sft_data.jsonl \
  datasets/grpo_aux.jsonl
```

This keeps only rows whose `llm_output_renamed` contains a valid first `<aux> ... </aux>` block.

## Reward Semantics

`src/newclid/training/grpo_rewards.py` evaluates only the generated aux block against `fl_problem`, not the full solver trajectory.

Reward values:

- `1.0`: aux is valid and DDAR solves the problem
- `0.25`: aux is geometrically valid but DDAR does not solve the problem
- `-0.25`: aux parses but cannot be built into the problem
- `-1.0`: invalid aux format
- `0.0`: DDAR engine error

Reward interface:

- `completions`
- `fl_problem`

`fl_problem` is required.

## Actual GRPO Run

The training entrypoint is `train_grpo.sh`, which wraps:

```bash
swift rlhf \
  --rlhf_type grpo \
  --dataset "$DATASET_PATH" \
  --external_plugins scripts/grpo/plugin.py \
  --reward_funcs aux_reward
```

Minimal run:

```bash
MODEL_PATH=/path/to/base-or-sft-checkpoint \
DATASET_PATH=datasets/grpo/grpo_train_selected.jsonl \
OUTPUT_DIR=models/grpo_aux \
bash scripts/grpo/train_grpo.sh
```

You can pass extra SWIFT arguments through the script. Example:

```bash
MODEL_PATH=/path/to/checkpoint \
DATASET_PATH=datasets/grpo/grpo_train_selected.jsonl \
OUTPUT_DIR=models/grpo_aux_run1 \
bash scripts/grpo/train_grpo.sh \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 16 \
  --num_generations 8 \
  --num_train_epochs 3 \
  --learning_rate 1e-6
```

## Performance Benchmarks (`label_difficulty_vlm.py`)

Tested on a Qwen3-VL checkpoint with 5 sample rows:

| Configuration | Time per row | Speedup |
|---------------|--------------|---------|
| Baseline (num_samples=16, serial) | 3.32s | 1.0x |
| Optimized (num_samples=8, batch_size=8, 1 GPU) | 1.70s | 1.95x |
| Optimized (num_samples=8, batch_size=8, 2 GPUs) | 0.85s | 3.9x |
| Optimized (num_samples=8, batch_size=8, 4 GPUs) | 0.43s | 7.7x |

Time estimates for generating 3k goldilocks samples from a 1M-row dataset:

| Configuration | Conservative (10% goldilocks) | Optimistic (20% goldilocks) |
|---------------|-------------------------------|------------------------------|
| Baseline (1 GPU, n=16) | 27.8h | 14.0h |
| Optimized (1 GPU, n=8, batch) | 14.3h | 7.2h |
| Optimized (2 GPUs, n=8, batch) | 7.2h | 3.7h |
| Optimized (4 GPUs, n=8, batch) | 3.7h | 1.9h |

Key optimization: explicitly set `max_batch_size` in `TransformersEngine` so batch inference does not silently fall back to serial generation.
