# GRPO Aux Reward

This directory contains the data-selection, reward, and launch helpers for GRPO-based auxiliary-point generation.

## Scripts

- `plugin.py`: registers `aux_reward` for SWIFT.
- `../analyze_dataset.py`: annotates JSONL rows with aux structure, goal predicate, predicate family tags, and lightweight complexity fields.
- `build_candidate_pool.py`: keeps only rows with real aux targets and emits a candidate pool summary.
- `prefilter_candidate_pool.py`: applies a cheap streaming prefilter to large candidate pools before model-based difficulty labeling.
- `label_difficulty.py`: text-model difficulty labeling with offline generation plus reward evaluation.
- `label_difficulty_vlm.py`: VLM-compatible difficulty labeling with batch inference and multi-GPU support.
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

This stage is meant to reduce a large pool before model-based labeling. It removes exact duplicate queries and balances sampling over:

- aux shape: `multi_aux` vs `single_aux`
- premise complexity: `p8_plus`, `p5_7`, `p0_4`
- primary goal/predicate family

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

This removes:

- mastered rows: `greedy_success == true` and very high `pass_at_16`
- dead rows: `all_invalid == true`

It then constructs a balanced "goldilocks" subset for actual GRPO training.

```bash
python scripts/grpo/select_debug_set.py \
  datasets/grpo/difficulty_labels.jsonl \
  datasets/grpo/grpo_train_selected.jsonl \
  --report-output datasets/grpo/grpo_train_report.json \
  --target-size 2000
```

The output rows contain exactly:

- `query`
- `fl_problem`
- `response`

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
