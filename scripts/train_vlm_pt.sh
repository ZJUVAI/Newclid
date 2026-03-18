#!/bin/bash
set -e

export LOGLEVEL=WARNING

REPO_ROOT="/C20545/home/wangzi/GenesisGeo"

###############################################
# Configuration
###############################################

DATASET_PATH="${DATASET_PATH:-/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new.jsonl}"
BASE_MODEL="${BASE_MODEL:-Qwen/Qwen3-VL-2B-Instruct}"
MODEL_NAME="${MODEL_NAME:-vlm_pt39}"
MODEL_DIR="${MODEL_DIR:-$REPO_ROOT/models/${MODEL_NAME}}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs/$(date +%m%d_%H%M%S)_${MODEL_NAME}}"

CUDA_DEVICES="${CUDA_DEVICES:-1,2,3}"
NPROC_PER_NODE="${NPROC_PER_NODE:-3}"
MASTER_PORT="${MASTER_PORT:-29700}"

EVAL_DATASETS=(
    "dev_imo.txt"
    "imo_95_reorder.txt"
)

EVAL_CONFIGS=(
    "32 512"
)

EVAL_MAX_WORKERS="${EVAL_MAX_WORKERS:-40}"
EVAL_SEARCH_DEPTH="${EVAL_SEARCH_DEPTH:-4}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-3600}"

mkdir -p "$LOG_DIR"

echo "=========================================="
echo "VLM PT Train + Eval"
echo "=========================================="
echo "Dataset   : $DATASET_PATH"
echo "Base Model: $BASE_MODEL"
echo "Model Dir : $MODEL_DIR"
echo "Log Dir   : $LOG_DIR"
echo "=========================================="

echo ""
echo "--- Step 1: Training ---"
echo "  Model dir : $MODEL_DIR"
echo "  Dataset   : $DATASET_PATH"

MASTER_PORT=$MASTER_PORT \
PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
NPROC_PER_NODE=$NPROC_PER_NODE \
CUDA_VISIBLE_DEVICES=$CUDA_DEVICES \
swift pt \
    --model $BASE_MODEL \
    --dataset "$DATASET_PATH" \
    --columns '{"llm_text_renamed": "text", "image_path": "images"}' \
    --max_length 4096 \
    --packing true \
    --padding_free true \
    --dataset_num_proc 32 \
    --dataloader_num_workers 4 \
    --train_type full \
    --freeze_llm false \
    --freeze_vit false \
    --freeze_aligner false \
    --torch_dtype bfloat16 \
    --deepspeed zero1 \
    --attn_impl flash_attn \
    --use_liger_kernel true \
    --num_train_epochs 1 \
    --warmup_ratio 0.1 \
    --per_device_train_batch_size 4 \
    --gradient_accumulation_steps 5 \
    --per_device_eval_batch_size 1 \
    --learning_rate 1e-4 \
    --adam_beta1 0.9 \
    --adam_beta2 0.999 \
    --save_steps 1000 \
    --logging_steps 500 \
    --output_dir $MODEL_DIR \
    --add_version false \
    --save_only_model true \
    --full_determinism true \
    2>&1 | tee "$LOG_DIR/training.log"

echo "Training completed"

echo ""
echo "--- Step 2: Finding checkpoint ---"

if [ ! -d "$MODEL_DIR" ]; then
    echo "Model directory not found: $MODEL_DIR - skipping evaluation"
    exit 1
fi

LATEST_CHECKPOINT=$(ls -d "$MODEL_DIR"/checkpoint-* 2>/dev/null | sort -V | tail -1)
if [ -z "$LATEST_CHECKPOINT" ]; then
    echo "No checkpoint found, using model root"
    CHECKPOINT_PATH="$MODEL_DIR"
else
    CHECKPOINT_PATH="$LATEST_CHECKPOINT"
    echo "  Checkpoint: $(basename "$LATEST_CHECKPOINT")"
fi

echo ""
echo "--- Step 3: Evaluation ---"
echo "  Datasets: ${EVAL_DATASETS[@]}"
echo "  Configs : ${EVAL_CONFIGS[@]}"

for dataset in "${EVAL_DATASETS[@]}"; do
    for config in "${EVAL_CONFIGS[@]}"; do
        read -r decoding_size beam_size <<< "$config"

        cmd="python $REPO_ROOT/scripts/evaluation_vlm.py \
            --problems_path $REPO_ROOT/benchmarks/$dataset \
            --model_path $CHECKPOINT_PATH \
            --log_dir $LOG_DIR \
            --max_workers $EVAL_MAX_WORKERS \
            --decoding_size $decoding_size \
            --beam_size $beam_size \
            --search_depth $EVAL_SEARCH_DEPTH \
            --timeout $EVAL_TIMEOUT"

        echo ""
        echo "  Evaluating: $dataset (d${decoding_size}_b${beam_size})"
        echo "----------------------------------"

        eval "$cmd"

        if [ $? -eq 0 ]; then
            echo "Evaluation completed: $dataset (d${decoding_size}_b${beam_size})"
        else
            echo "Evaluation failed: $dataset"
        fi
        echo "=========================================="
    done
done

echo ""
echo "=========================================="
echo "Pipeline completed"
echo "  Model: $MODEL_NAME"
echo "  Saved: $MODEL_DIR"
echo "  Logs : $LOG_DIR"
echo "=========================================="
