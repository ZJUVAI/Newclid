#!/bin/bash
set -e  # Exit on error

export LOGLEVEL=WARNING

###############################################
# Configuration
###############################################

# Dataset and model configuration
# 完整数据集（使用 autodl-tmp 快速存储）
DATASET_PATH="/root/autodl-tmp/datasets/0210/geometry_clauses10_samples2M_inverted_tmp.jsonl"
BASE_MODEL="Qwen/Qwen3.5-2B"
MODEL_NAME="vlm_sft54"
MODEL_DIR="/root/autodl-pub/math/wangzi/models/${MODEL_NAME}"
LOG_DIR="/root/autodl-pub/math/wangzi/logs/$(date +%m%d_%H%M%S)_${MODEL_NAME}"

# Training parameters
CUDA_DEVICES="0,1,2,3"
NPROC_PER_NODE=4

# Evaluation parameters
EVAL_DATASETS=(
    "dev_imo.txt"
    "imo_95_reorder.txt"
    "jgex_ag_231.txt"
)

EVAL_CONFIGS=(
    "32 512"
)

EVAL_MAX_WORKERS=40
EVAL_SEARCH_DEPTH=4
EVAL_TIMEOUT=7200
EVAL_AGENT="qwen35"

###############################################
# Step 1: Create log directory
###############################################

mkdir -p "$LOG_DIR"
echo "=========================================="
echo "Training and Evaluation Pipeline"
echo "=========================================="
echo "Dataset   : $DATASET_PATH"
echo "Base Model: $BASE_MODEL"
echo "Model Dir : $MODEL_DIR"
echo "Log Dir   : $LOG_DIR"
echo "=========================================="

###############################################
# Step 2: Dataset analysis (optional)
###############################################

echo ""
echo "--- Step 1: Dataset analysis ---"
ANALYSIS_OUTPUT="$LOG_DIR/dataset_analysis.txt"
if [ -f "scripts/analyze_dataset.py" ]; then
    python scripts/analyze_dataset.py "$DATASET_PATH" > "$ANALYSIS_OUTPUT" 2>&1
    if [ $? -eq 0 ]; then
        echo "✓ Dataset analysis completed. Results: $ANALYSIS_OUTPUT"
    else
        echo "⚠ Dataset analysis failed (continuing anyway)"
    fi
else
    echo "⚠ analyze_dataset.py not found, skipping analysis"
fi

###############################################
# Step 3: Training
###############################################

echo ""
echo "--- Step 2: Training ---"
echo "  Model dir : $MODEL_DIR"
echo "  Dataset   : $DATASET_PATH"

PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
IMAGE_MAX_TOKEN_NUM='1024' \
NPROC_PER_NODE=$NPROC_PER_NODE \
CUDA_VISIBLE_DEVICES=$CUDA_DEVICES \
swift sft \
    --model $BASE_MODEL \
    --dataset "$DATASET_PATH" \
    --columns '{"llm_input_renamed": "query", "llm_output_renamed": "response", "image_path": "images"}' \
    --system 'You are a helpful assistant.' \
    --max_length 4096 \
    --packing false \
    --padding_free false \
    --group_by_length true \
    --dataset_num_proc 32 \
    --dataloader_num_workers 4 \
    --train_type full \
    --freeze_llm false \
    --freeze_vit true \
    --freeze_aligner false \
    --torch_dtype bfloat16 \
    --deepspeed zero2 \
    --attn_impl flash_attn \
    --use_liger_kernel true \
    --add_non_thinking_prefix true \
    --loss_scale ignore_empty_think \
    --num_train_epochs 1 \
    --warmup_ratio 0.1 \
    --per_device_train_batch_size 4 \
    --per_device_eval_batch_size 1 \
    --gradient_accumulation_steps 4 \
    --learning_rate 1e-5 \
    --adam_beta1 0.9 \
    --adam_beta2 0.999 \
    --save_steps 10000 \
    --logging_steps 1 \
    --output_dir $MODEL_DIR \
    --add_version false \
    --save_only_model true \
    --full_determinism true \
    2>&1 | tee "$LOG_DIR/training.log"

echo "✓ Training completed"

###############################################
# Step 4: Find latest checkpoint
###############################################

echo ""
echo "--- Step 3: Finding checkpoint ---"

if [ ! -d "$MODEL_DIR" ]; then
    echo "✗ Model directory not found: $MODEL_DIR — skipping evaluation"
    exit 1
fi

LATEST_CHECKPOINT=$(ls -d "$MODEL_DIR"/checkpoint-* 2>/dev/null | sort -V | tail -1)
if [ -z "$LATEST_CHECKPOINT" ]; then
    echo "⚠ No checkpoint found, using model root"
    CHECKPOINT_PATH="$MODEL_DIR"
else
    CHECKPOINT_PATH="$LATEST_CHECKPOINT"
    echo "  Checkpoint: $(basename $LATEST_CHECKPOINT)"
fi

###############################################
# Step 5: Evaluation
###############################################

echo ""
echo "--- Step 4: Evaluation ---"
echo "  Datasets: ${EVAL_DATASETS[@]}"
echo "  Configs : ${EVAL_CONFIGS[@]}"

for dataset in "${EVAL_DATASETS[@]}"; do
    for config in "${EVAL_CONFIGS[@]}"; do
        read -r decoding_size beam_size <<< "$config"

        cmd="python scripts/evaluation_vlm.py \
            --problems_path benchmarks/$dataset \
            --model_path $CHECKPOINT_PATH \
            --max_workers $EVAL_MAX_WORKERS \
            --decoding_size $decoding_size \
            --beam_size $beam_size \
            --search_depth $EVAL_SEARCH_DEPTH \
            --timeout $EVAL_TIMEOUT \
            --agent $EVAL_AGENT"

        echo ""
        echo "  Evaluating: $dataset (d${decoding_size}_b${beam_size})"
        echo "----------------------------------"

        eval "$cmd"

        if [ $? -eq 0 ]; then
            echo "✓ Evaluation completed: $dataset (d${decoding_size}_b${beam_size})"
        else
            echo "✗ Evaluation failed: $dataset"
        fi
        echo "=========================================="
    done
done

echo ""
echo "=========================================="
echo "Pipeline completed!"
echo "  Model: $MODEL_NAME"
echo "  Saved: $MODEL_DIR"
echo "  Logs : $LOG_DIR"
echo "=========================================="
