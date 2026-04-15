#!/bin/bash
set -euo pipefail

# Prepare a dataset first, for example:
#   python scripts/grpo/prepare_grpo_aux_dataset.py INPUT.jsonl OUTPUT.jsonl

MODEL_PATH="${MODEL_PATH:-Qwen/Qwen3-0.6B-Base}"
DATASET_PATH="${DATASET_PATH:-datasets/grpo_aux.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-models/grpo_aux}"

# Get the directory of this script and use venv swift
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Use the swift executable from venv
"$REPO_ROOT/.venv/bin/swift" rlhf \
    --rlhf_type grpo \
    --model "$MODEL_PATH" \
    --dataset "$DATASET_PATH" \
    --external_plugins scripts/grpo/plugin.py \
    --reward_funcs aux_reward \
    --split_dataset_ratio 0 \
    --system 'You are a helpful assistant.' \
    --max_length 2048 \
    --torch_dtype bfloat16 \
    --output_dir "$OUTPUT_DIR" \
    "$@"
