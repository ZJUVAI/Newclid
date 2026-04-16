#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$REPO_ROOT/.venv/bin/python}"

INPUT_PATH="${INPUT_PATH:-}"
OUTPUT_DIR="${OUTPUT_DIR:-datasets/grpo_pipeline}"
MODEL_PATH="${MODEL_PATH:-}"
LABELER="${LABELER:-text}"
PREFILTER_TARGET_SIZE="${PREFILTER_TARGET_SIZE:-50000}"
FINAL_TARGET_SIZE="${FINAL_TARGET_SIZE:-2000}"
SEED="${SEED:-998244353}"
LABEL_NUM_SAMPLES="${LABEL_NUM_SAMPLES:-16}"
LABEL_TEMPERATURE="${LABEL_TEMPERATURE:-0.8}"
LABEL_TOP_P="${LABEL_TOP_P:-0.95}"

if [[ -z "$INPUT_PATH" ]]; then
    echo "INPUT_PATH is required" >&2
    exit 1
fi

if [[ -z "$MODEL_PATH" ]]; then
    echo "MODEL_PATH is required" >&2
    exit 1
fi

case "$LABELER" in
    text)
        LABEL_SCRIPT="scripts/grpo/label_difficulty.py"
        ;;
    vlm)
        LABEL_SCRIPT="scripts/grpo/label_difficulty_vlm.py"
        ;;
    *)
        echo "LABELER must be either 'text' or 'vlm'" >&2
        exit 1
        ;;
esac

mkdir -p "$OUTPUT_DIR"

ANNOTATED_JSONL="$OUTPUT_DIR/annotated.jsonl"
ANNOTATED_SUMMARY_JSON="$OUTPUT_DIR/annotated_summary.json"
CANDIDATE_POOL_JSONL="$OUTPUT_DIR/candidate_pool.jsonl"
CANDIDATE_POOL_SUMMARY_JSON="$OUTPUT_DIR/candidate_pool_summary.json"
PREFILTERED_JSONL="$OUTPUT_DIR/candidate_pool_prefiltered.jsonl"
PREFILTER_REPORT_JSON="$OUTPUT_DIR/candidate_pool_prefilter_report.json"
DIFFICULTY_JSONL="$OUTPUT_DIR/difficulty_labels.jsonl"
SELECTED_JSONL="$OUTPUT_DIR/grpo_train_selected.jsonl"
SELECTED_REPORT_JSON="$OUTPUT_DIR/grpo_train_report.json"
SELECTED_ANNOTATED_JSONL="$OUTPUT_DIR/grpo_train_selected_annotated.jsonl"
SELECTED_SUMMARY_JSON="$OUTPUT_DIR/grpo_train_selected_summary.json"

"$PYTHON_BIN" scripts/analyze_dataset.py \
    "$INPUT_PATH" \
    --annotations-output "$ANNOTATED_JSONL" \
    --summary-output "$ANNOTATED_SUMMARY_JSON"

"$PYTHON_BIN" scripts/grpo/build_candidate_pool.py \
    "$ANNOTATED_JSONL" \
    "$CANDIDATE_POOL_JSONL" \
    --summary-output "$CANDIDATE_POOL_SUMMARY_JSON"

"$PYTHON_BIN" scripts/grpo/prefilter_candidate_pool.py \
    "$CANDIDATE_POOL_JSONL" \
    "$PREFILTERED_JSONL" \
    --report-output "$PREFILTER_REPORT_JSON" \
    --target-size "$PREFILTER_TARGET_SIZE" \
    --seed "$SEED"

"$PYTHON_BIN" "$LABEL_SCRIPT" \
    "$PREFILTERED_JSONL" \
    "$DIFFICULTY_JSONL" \
    --model-path "$MODEL_PATH" \
    --num-samples "$LABEL_NUM_SAMPLES" \
    --temperature "$LABEL_TEMPERATURE" \
    --top-p "$LABEL_TOP_P"

"$PYTHON_BIN" scripts/grpo/select_debug_set.py \
    "$DIFFICULTY_JSONL" \
    "$SELECTED_JSONL" \
    --report-output "$SELECTED_REPORT_JSON" \
    --target-size "$FINAL_TARGET_SIZE"

"$PYTHON_BIN" scripts/grpo/analyze_selected_dataset.py \
    "$SELECTED_JSONL" \
    --annotations-output "$SELECTED_ANNOTATED_JSONL" \
    --summary-output "$SELECTED_SUMMARY_JSON"

echo "GRPO dataset selection pipeline completed."
echo "Selected dataset: $SELECTED_JSONL"
echo "Selected dataset summary: $SELECTED_SUMMARY_JSON"
