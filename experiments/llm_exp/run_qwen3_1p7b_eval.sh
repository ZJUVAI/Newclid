#!/bin/bash
set -euo pipefail

export LOGLEVEL="${LOGLEVEL:-WARNING}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

SFT_MODEL_DIR="${SFT_MODEL_DIR:-qwen3_1p7b_sft_text}"
MODEL_PATH="${MODEL_PATH:-}"

BENCHMARK_DIR="${BENCHMARK_DIR:-$REPO_ROOT/benchmarks}"
EVAL_DATASETS="${EVAL_DATASETS:-dev_imo.txt imo_95_reorder.txt}"
EVAL_CONFIGS="${EVAL_CONFIGS:-32:512:4}"
EVAL_MAX_WORKERS="${EVAL_MAX_WORKERS:-40}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-3600}"
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3}"
RAY_memory_usage_threshold="${RAY_memory_usage_threshold:-0.95}"

require_command() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Missing command: $cmd"
        exit 1
    fi
}

require_path() {
    local path="$1"
    local label="$2"
    if [ ! -e "$path" ]; then
        echo "Missing ${label}: $path"
        exit 1
    fi
}

find_latest_checkpoint() {
    local model_dir="$1"
    if [ ! -d "$model_dir" ]; then
        return 0
    fi
    find "$model_dir" -maxdepth 1 -mindepth 1 -type d -name 'checkpoint-*' 2>/dev/null | sort -t'-' -k2,2n | tail -1
}

resolve_model_artifact() {
    local model_dir="$1"
    local latest_checkpoint
    latest_checkpoint="$(find_latest_checkpoint "$model_dir")"
    if [ -n "$latest_checkpoint" ]; then
        printf '%s\n' "$latest_checkpoint"
        return 0
    fi
    if [ -d "$model_dir" ]; then
        printf '%s\n' "$model_dir"
        return 0
    fi
    return 1
}

print_section() {
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

require_command python
require_path "$BENCHMARK_DIR" "benchmark directory"

if [ -n "$MODEL_PATH" ]; then
    require_path "$MODEL_PATH" "model path"
    EVAL_MODEL_PATH="$MODEL_PATH"
else
    SFT_OUTPUT_DIR="$REPO_ROOT/models/$SFT_MODEL_DIR"
    require_path "$SFT_OUTPUT_DIR" "SFT output directory"
    EVAL_MODEL_PATH="$(resolve_model_artifact "$SFT_OUTPUT_DIR")"
fi

print_section "Qwen3 1.7B Evaluation"
echo "Eval model: $EVAL_MODEL_PATH"
echo "Datasets  : $EVAL_DATASETS"
echo "Configs   : $EVAL_CONFIGS"
echo "Workers   : $EVAL_MAX_WORKERS"
echo "Timeout   : $EVAL_TIMEOUT"

export CUDA_VISIBLE_DEVICES
export RAY_memory_usage_threshold

for dataset in $EVAL_DATASETS; do
    require_path "$BENCHMARK_DIR/$dataset" "benchmark file"
    for config in $EVAL_CONFIGS; do
        decoding_size="$(printf '%s' "$config" | cut -d: -f1)"
        beam_size="$(printf '%s' "$config" | cut -d: -f2)"
        search_depth="$(printf '%s' "$config" | cut -d: -f3)"

        if [ -z "$decoding_size" ] || [ -z "$beam_size" ] || [ -z "$search_depth" ]; then
            echo "Invalid eval config: $config"
            exit 1
        fi

        echo "Running eval on $dataset with d=$decoding_size b=$beam_size s=$search_depth"
        python scripts/evaluation.py \
            --problems_path "$BENCHMARK_DIR/$dataset" \
            --model_path "$EVAL_MODEL_PATH" \
            --max_workers "$EVAL_MAX_WORKERS" \
            --decoding_size "$decoding_size" \
            --beam_size "$beam_size" \
            --search_depth "$search_depth" \
            --timeout "$EVAL_TIMEOUT"
    done
done

print_section "Evaluation completed"
echo "Eval model: $EVAL_MODEL_PATH"
