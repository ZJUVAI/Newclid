#!/bin/bash
set -euo pipefail

# Prepare a dataset first, for example:
#   python scripts/grpo/prepare_grpo_aux_dataset.py INPUT.jsonl OUTPUT.jsonl

MODEL_PATH="${MODEL_PATH:-Qwen/Qwen3-0.6B-Base}"
MODEL_TYPE="${MODEL_TYPE:-}"
DATASET_PATH="${DATASET_PATH:-datasets/grpo_aux.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-models/grpo_aux}"
NUM_GENERATIONS="${NUM_GENERATIONS:-}"
TEMPERATURE="${TEMPERATURE:-}"
TOP_K="${TOP_K:-}"
TOP_P="${TOP_P:-}"
MAX_COMPLETION_LENGTH="${MAX_COMPLETION_LENGTH:-}"
BETA="${BETA:-}"
REWARD_LOG_INTERVAL="${REWARD_LOG_INTERVAL:-50}"

# Get the directory of this script and use venv swift
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"

mkdir -p "$OUTPUT_DIR"

export NEWCLID_GRPO_REWARD_LOG_INTERVAL="$REWARD_LOG_INTERVAL"

METADATA_PATH="$OUTPUT_DIR/run_metadata.json"
"$PYTHON_BIN" - <<'PY' "$DATASET_PATH" "$OUTPUT_DIR" "$METADATA_PATH"
import json
import os
import sys
from pathlib import Path

dataset_path = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
metadata_path = Path(sys.argv[3])
dataset_rows = 0
if dataset_path.exists():
    with dataset_path.open("r", encoding="utf-8") as handle:
        dataset_rows = sum(1 for line in handle if line.strip())

report_path = dataset_path.with_name("grpo_train_report.json")
report = None
if report_path.exists():
    with report_path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)

metadata = {
    "dataset_path": str(dataset_path),
    "dataset_rows": dataset_rows,
    "output_dir": str(output_dir),
    "model_type": os.getenv("MODEL_TYPE") or None,
    "num_generations": os.getenv("NUM_GENERATIONS") or None,
    "temperature": os.getenv("TEMPERATURE") or None,
    "top_k": os.getenv("TOP_K") or None,
    "top_p": os.getenv("TOP_P") or None,
    "max_completion_length": os.getenv("MAX_COMPLETION_LENGTH") or None,
    "beta": os.getenv("BETA") or None,
    "reward_log_interval": os.getenv("NEWCLID_GRPO_REWARD_LOG_INTERVAL"),
    "reward_config": {
        "solved_reward": os.getenv("NEWCLID_GRPO_SOLVED_REWARD"),
        "valid_reward": os.getenv("NEWCLID_GRPO_VALID_REWARD"),
        "invalid_build_reward": os.getenv("NEWCLID_GRPO_INVALID_BUILD_REWARD"),
        "invalid_format_reward": os.getenv("NEWCLID_GRPO_INVALID_FORMAT_REWARD"),
        "engine_error_reward": os.getenv("NEWCLID_GRPO_ENGINE_ERROR_REWARD"),
    },
    "selection_report_path": str(report_path) if report_path.exists() else None,
    "selection_report": report,
}
metadata_path.write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(f"wrote training metadata to {metadata_path}")
PY

SWIFT_ARGS=()
if [[ -n "$MODEL_TYPE" ]]; then
    SWIFT_ARGS+=(--model_type "$MODEL_TYPE")
fi
if [[ -n "$NUM_GENERATIONS" ]]; then
    SWIFT_ARGS+=(--num_generations "$NUM_GENERATIONS")
fi
if [[ -n "$TEMPERATURE" ]]; then
    SWIFT_ARGS+=(--temperature "$TEMPERATURE")
fi
if [[ -n "$TOP_K" ]]; then
    SWIFT_ARGS+=(--top_k "$TOP_K")
fi
if [[ -n "$TOP_P" ]]; then
    SWIFT_ARGS+=(--top_p "$TOP_P")
fi
if [[ -n "$MAX_COMPLETION_LENGTH" ]]; then
    SWIFT_ARGS+=(--max_completion_length "$MAX_COMPLETION_LENGTH")
fi
if [[ -n "$BETA" ]]; then
    SWIFT_ARGS+=(--beta "$BETA")
fi

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
    "${SWIFT_ARGS[@]}" \
    "$@"
