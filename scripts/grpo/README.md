# GRPO Aux Reward

- `plugin.py`: registers `aux_reward` for SWIFT.
- `../analyze_dataset.py`: annotates JSONL rows with aux structure, goal predicate, and predicate family tags.
- `build_candidate_pool.py`: keeps only rows with real aux targets and emits a candidate pool summary.
- `label_difficulty.py`: runs `greedy@1 + sample@16` with a checkpoint and scores completions through DDAR.
- `select_debug_set.py`: filters mastered/dead rows and builds the GRPO debug subset.
- `prepare_grpo_aux_dataset.py`: converts existing JSONL data into `query/fl_problem/response` rows for aux-only GRPO and drops rows without `<aux>...</aux>`.
- `train_grpo.sh`: text-only GRPO launch template.
- `src/newclid/training/grpo_rewards.py`: composite reward evaluator.

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
3. `python scripts/grpo/label_difficulty.py candidate_pool.jsonl difficulty_labels.jsonl --model-path models/auxsweep02/checkpoint-39184`
4. `python scripts/grpo/select_debug_set.py difficulty_labels.jsonl grpo_debug_selected.jsonl --report-output grpo_debug_report.json --target-size 2000`
