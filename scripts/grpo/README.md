# GRPO Aux Reward

## Scripts

- `plugin.py`: registers `aux_reward` for SWIFT.
- `../analyze_dataset.py`: annotates JSONL rows with aux structure, goal predicate, and predicate family tags.
- `build_candidate_pool.py`: keeps only rows with real aux targets and emits a candidate pool summary.
- `prefilter_candidate_pool.py`: applies a cheap streaming prefilter to large candidate pools before model-based difficulty labeling.
- `label_difficulty_vlm.py`: VLM-compatible difficulty labeling with batch inference and multi-GPU support.
- `select_debug_set.py`: filters mastered/dead rows and builds the GRPO debug subset.
- `prepare_grpo_aux_dataset.py`: converts existing JSONL data into `query/fl_problem/response` rows for aux-only GRPO and drops rows without `<aux>...</aux>`.
- `train_grpo.sh`: text-only GRPO launch template.
- `src/newclid/training/grpo_rewards.py`: composite reward evaluator.

## Performance Benchmarks (label_difficulty_vlm.py)

Tested on Qwen3-VL checkpoint with 5 sample rows:

| Configuration | Time per row | Speedup |
|---------------|--------------|---------|
| Baseline (num_samples=16, serial) | 3.32s | 1.0x |
| Optimized (num_samples=8, batch_size=8, 1 GPU) | 1.70s | 1.95x |
| Optimized (num_samples=8, batch_size=8, 2 GPUs) | 0.85s | 3.9x |
| Optimized (num_samples=8, batch_size=8, 4 GPUs) | 0.43s | 7.7x |

**Time estimates for generating 3k goldilocks samples from 1M dataset:**

| Configuration | Conservative (10% goldilocks) | Optimistic (20% goldilocks) |
|---------------|-------------------------------|------------------------------|
| Baseline (1 GPU, n=16) | 27.8h | 14.0h |
| Optimized (1 GPU, n=8, batch) | 14.3h | 7.2h |
| Optimized (2 GPUs, n=8, batch) | 7.2h | 3.7h |
| Optimized (4 GPUs, n=8, batch) | 3.7h | 1.9h |

**Key optimization:** Set `max_batch_size` in TransformersEngine to enable true batch inference (default is 1).

Expected dataset columns:

- `query`: prompt given to the model.
- `fl_problem`: original buildable problem text used by the reward.
- `response`: aux-only target such as `<aux> x00 i : ... ; </aux>`.

Reward interface:

- `completions`
- `fl_problem`

`fl_problem` is required; the reward no longer falls back to `query` or any other field.

Recommended debug pipeline:

1. `python scripts/analyze_dataset.py DATA.jsonl --annotations-output annotated.jsonl --summary-output annotated_summary.json`
2. `python scripts/grpo/build_candidate_pool.py annotated.jsonl candidate_pool.jsonl --summary-output candidate_pool_summary.json`
3. `python scripts/grpo/prefilter_candidate_pool.py candidate_pool.jsonl candidate_pool_prefiltered.jsonl --report-output candidate_pool_prefilter_report.json --target-size 50000`
4. `python scripts/grpo/label_difficulty.py candidate_pool_prefiltered.jsonl difficulty_labels.jsonl --model-path models/auxsweep02/checkpoint-39184`
5. `python scripts/grpo/select_debug_set.py difficulty_labels.jsonl grpo_debug_selected.jsonl --report-output grpo_debug_report.json --target-size 2000`
