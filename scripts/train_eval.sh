#!/bin/bash
export LOGLEVEL=WARNING

###############################################
# Training

# Model directory - modify this as needed
model_dir="sfttest"

# Create log directory with timestamp
LOG_DIR="logs/$(date +%m%d_%H%M%S)_${model_dir}"
mkdir -p "$LOG_DIR"
echo "Log directory: $LOG_DIR"
echo ""

PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
NPROC_PER_NODE=4 \
CUDA_VISIBLE_DEVICES=0,1,2,3 \
swift sft \
    --model Qwen/Qwen3-0.6B-Base \
    --dataset '/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples100K_aux_updated_img512_inverted_remove_proof_task12_pathfixed.jsonl' \
    --columns '{"llm_input_renamed": "query", "llm_output_renamed": "response"}' \
    --system 'You are a helpful assistant.' \
    --max_length 2048 \
    --packing true \
    --padding_free true \
    --dataset_num_proc 32 \
    --dataloader_num_workers 4 \
    --train_type full \
    --torch_dtype bfloat16 \
    --deepspeed zero1 \
    --attn_impl flash_attn \
    --use_liger_kernel true \
    --num_train_epochs 1 \
    --warmup_ratio 0.1 \
    --per_device_train_batch_size 8 \
    --per_device_eval_batch_size 2 \
    --gradient_accumulation_steps 1 \
    --learning_rate 1e-4 \
    --adam_beta1 0.9 \
    --adam_beta2 0.999 \
    --save_steps 10000 \
    --logging_steps 500 \
    --output_dir models/$model_dir \
    --add_version false \
    --save_only_model true \
    2>&1 | tee "$LOG_DIR/training.log"
    # --truncation_strategy left \
    # --full_determinism true \
    # --lr_scheduler_type cosine_with_min_lr \
    # --lr_scheduler_kwargs '{"min_lr_rate":0.1}' \
    # --use_chat_template false \


###############################################
# Evaluation

# Dataset options
datasets=(
    # "dev_jgex.txt"
    # "dev_imo.txt"
    # "imo_102_requires_aux.txt"
)

# Decoding configurations (decoding_size beam_size)
configs=(
    # "8 64"
    "32 512"
)

# Checkpoint options - modify this list as needed
checkpoints=(
    # "checkpoint-10000"
    # "checkpoint-20000"
)

echo "Starting evaluation tasks..."
echo "Will process ${#checkpoints[@]} checkpoints, ${#datasets[@]} datasets, and ${#configs[@]} configurations"
echo "Total commands to execute: $((${#checkpoints[@]} * ${#datasets[@]} * ${#configs[@]}))"
echo "=================================="

# Loop through all checkpoints
for checkpoint in "${checkpoints[@]}"; do
    echo "Processing checkpoint: $checkpoint"
    echo "=================================="

    # Loop through all datasets
    for dataset in "${datasets[@]}"; do
        # Loop through all configurations
        for config in "${configs[@]}"; do
            # Split configuration parameters
            read -r decoding_size beam_size <<< "$config"

            # Build complete command
            cmd="python scripts/evaluation.py --problems_path benchmarks/$dataset --model_path ./models/$model_dir/$checkpoint --log_dir $LOG_DIR --max_workers 40 --decoding_size $decoding_size --beam_size $beam_size --search_depth 4 --agent lm"

            # Print current command to execute
            echo "Executing command:"
            echo "$cmd"
            echo "----------------------------------"

            # Execute command
            eval "$cmd"

            # Check command execution status
            if [ $? -eq 0 ]; then
                echo "✓ Command executed successfully"
            else
                echo "✗ Command execution failed"
            fi

            echo "=================================="
        done
    done

    echo "Completed checkpoint: $checkpoint"
    echo "=================================="
done

echo "All evaluation tasks completed!"
echo "Processed ${#checkpoints[@]} checkpoints total."
