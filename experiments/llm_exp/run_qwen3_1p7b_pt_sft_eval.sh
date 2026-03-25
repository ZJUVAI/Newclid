#!/bin/bash
set -euo pipefail

export LOGLEVEL="${LOGLEVEL:-WARNING}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# Expected pure-text JSONL formats:
# 1. PT dataset:  one text field, default key `llm_text_renamed`
# 2. SFT dataset: one prompt field + one answer field, default keys
#    `llm_input_renamed` and `llm_output_renamed`

BASE_MODEL="${BASE_MODEL:-Qwen/Qwen3-1.7B-Base}"

PT_DATASET="${PT_DATASET:-/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new.jsonl}"
SFT_DATASET="${SFT_DATASET:-/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_remove_proof_task1_pathfixed.jsonl}"

PT_COLUMNS="${PT_COLUMNS:-{\"llm_text_renamed\":\"text\"}}"
SFT_COLUMNS="${SFT_COLUMNS:-{\"llm_input_renamed\":\"query\",\"llm_output_renamed\":\"response\"}}"
SFT_SYSTEM_PROMPT="${SFT_SYSTEM_PROMPT:-You are a helpful assistant.}"

PT_MODEL_DIR="${PT_MODEL_DIR:-qwen3_1p7b_pt_text}"
SFT_MODEL_DIR="${SFT_MODEL_DIR:-qwen3_1p7b_sft_text}"

CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3}"
MASTER_PORT="${MASTER_PORT:-29600}"
NPROC_PER_NODE="${NPROC_PER_NODE:-4}"

DATASET_NUM_PROC="${DATASET_NUM_PROC:-16}"
DATALOADER_NUM_WORKERS="${DATALOADER_NUM_WORKERS:-4}"
WARMUP_RATIO="${WARMUP_RATIO:-0.1}"
SAVE_STEPS="${SAVE_STEPS:-10000}"
LOGGING_STEPS="${LOGGING_STEPS:-500}"
TORCH_DTYPE="${TORCH_DTYPE:-bfloat16}"
DEEPSPEED_STAGE="${DEEPSPEED_STAGE:-zero1}"
ATTN_IMPL="${ATTN_IMPL:-flash_attn}"
USE_LIGER_KERNEL="${USE_LIGER_KERNEL:-true}"

PT_MAX_LENGTH="${PT_MAX_LENGTH:-4096}"
PT_PACKING="${PT_PACKING:-true}"
PT_PADDING_FREE="${PT_PADDING_FREE:-true}"
PT_EPOCHS="${PT_EPOCHS:-1}"
PT_BATCH_SIZE="${PT_BATCH_SIZE:-8}"
PT_GRAD_ACC="${PT_GRAD_ACC:-2}"
PT_LR="${PT_LR:-1e-4}"

SFT_MAX_LENGTH="${SFT_MAX_LENGTH:-2048}"
SFT_PACKING="${SFT_PACKING:-true}"
SFT_PADDING_FREE="${SFT_PADDING_FREE:-true}"
SFT_EPOCHS="${SFT_EPOCHS:-1}"
SFT_BATCH_SIZE="${SFT_BATCH_SIZE:-8}"
SFT_GRAD_ACC="${SFT_GRAD_ACC:-2}"
SFT_LR="${SFT_LR:-1e-5}"

BENCHMARK_DIR="${BENCHMARK_DIR:-$REPO_ROOT/benchmarks}"
EVAL_DATASETS="${EVAL_DATASETS:-dev_imo.txt imo_95_reorder.txt}"
EVAL_CONFIGS="${EVAL_CONFIGS:-32:512:4}"
EVAL_MAX_WORKERS="${EVAL_MAX_WORKERS:-40}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-3600}"
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

require_command swift
require_command python
require_path "$PT_DATASET" "PT dataset"
require_path "$SFT_DATASET" "SFT dataset"
require_path "$BENCHMARK_DIR" "benchmark directory"

PT_OUTPUT_DIR="$REPO_ROOT/models/$PT_MODEL_DIR"
SFT_OUTPUT_DIR="$REPO_ROOT/models/$SFT_MODEL_DIR"

print_section "Stage 1/3: Pretrain"
echo "Base model: $BASE_MODEL"
echo "PT dataset: $PT_DATASET"
echo "PT output : $PT_OUTPUT_DIR"

PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
MASTER_PORT="$MASTER_PORT" \
NPROC_PER_NODE="$NPROC_PER_NODE" \
CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES" \
swift pt \
    --model "$BASE_MODEL" \
    --dataset "$PT_DATASET" \
    --columns "$PT_COLUMNS" \
    --max_length "$PT_MAX_LENGTH" \
    --packing "$PT_PACKING" \
    --padding_free "$PT_PADDING_FREE" \
    --dataset_num_proc "$DATASET_NUM_PROC" \
    --dataloader_num_workers "$DATALOADER_NUM_WORKERS" \
    --train_type full \
    --torch_dtype "$TORCH_DTYPE" \
    --deepspeed "$DEEPSPEED_STAGE" \
    --attn_impl "$ATTN_IMPL" \
    --use_liger_kernel "$USE_LIGER_KERNEL" \
    --num_train_epochs "$PT_EPOCHS" \
    --warmup_ratio "$WARMUP_RATIO" \
    --per_device_train_batch_size "$PT_BATCH_SIZE" \
    --per_device_eval_batch_size 1 \
    --gradient_accumulation_steps "$PT_GRAD_ACC" \
    --learning_rate "$PT_LR" \
    --adam_beta1 0.9 \
    --adam_beta2 0.999 \
    --save_steps "$SAVE_STEPS" \
    --logging_steps "$LOGGING_STEPS" \
    --output_dir "$PT_OUTPUT_DIR" \
    --add_version false \
    --save_only_model true \
    --full_determinism true

PT_MODEL_PATH="$(resolve_model_artifact "$PT_OUTPUT_DIR")"

print_section "Stage 2/3: SFT"
echo "SFT init model: $PT_MODEL_PATH"
echo "SFT dataset   : $SFT_DATASET"
echo "SFT output    : $SFT_OUTPUT_DIR"

PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
MASTER_PORT="$((MASTER_PORT + 1))" \
NPROC_PER_NODE="$NPROC_PER_NODE" \
CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES" \
swift sft \
    --model "$PT_MODEL_PATH" \
    --dataset "$SFT_DATASET" \
    --columns "$SFT_COLUMNS" \
    --system "$SFT_SYSTEM_PROMPT" \
    --max_length "$SFT_MAX_LENGTH" \
    --packing "$SFT_PACKING" \
    --padding_free "$SFT_PADDING_FREE" \
    --dataset_num_proc "$DATASET_NUM_PROC" \
    --dataloader_num_workers "$DATALOADER_NUM_WORKERS" \
    --train_type full \
    --torch_dtype "$TORCH_DTYPE" \
    --deepspeed "$DEEPSPEED_STAGE" \
    --attn_impl "$ATTN_IMPL" \
    --use_liger_kernel "$USE_LIGER_KERNEL" \
    --num_train_epochs "$SFT_EPOCHS" \
    --warmup_ratio "$WARMUP_RATIO" \
    --per_device_train_batch_size "$SFT_BATCH_SIZE" \
    --per_device_eval_batch_size 1 \
    --gradient_accumulation_steps "$SFT_GRAD_ACC" \
    --learning_rate "$SFT_LR" \
    --adam_beta1 0.9 \
    --adam_beta2 0.999 \
    --save_steps "$SAVE_STEPS" \
    --logging_steps "$LOGGING_STEPS" \
    --output_dir "$SFT_OUTPUT_DIR" \
    --add_version false \
    --save_only_model true \
    --full_determinism true

SFT_MODEL_PATH="$(resolve_model_artifact "$SFT_OUTPUT_DIR")"

print_section "Stage 3/3: Evaluation"
echo "Eval model: $SFT_MODEL_PATH"
echo "Datasets  : $EVAL_DATASETS"
echo "Configs   : $EVAL_CONFIGS"

export CUDA_VISIBLE_DEVICES
export RAY_memory_usage_threshold

for dataset in $EVAL_DATASETS; do
    require_path "$BENCHMARK_DIR/$dataset" "benchmark file"
    for config in $EVAL_CONFIGS; do
        decoding_size="$(printf '%s' "$config" | cut -d: -f1)"
        beam_size="$(printf '%s' "$config" | cut -d: -f2)"
        search_depth="$(printf '%s' "$config" | cut -d: -f3)"

        echo "Running eval on $dataset with d=$decoding_size b=$beam_size s=$search_depth"
        python scripts/evaluation.py \
            --problems_path "$BENCHMARK_DIR/$dataset" \
            --model_path "$SFT_MODEL_PATH" \
            --max_workers "$EVAL_MAX_WORKERS" \
            --decoding_size "$decoding_size" \
            --beam_size "$beam_size" \
            --search_depth "$search_depth" \
            --timeout "$EVAL_TIMEOUT"
    done
done

print_section "All stages completed"
echo "PT artifact : $PT_MODEL_PATH"
echo "SFT artifact: $SFT_MODEL_PATH"
