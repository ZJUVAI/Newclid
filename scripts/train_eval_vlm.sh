#!/bin/bash
export LOGLEVEL=WARNING

# Model directory - modify this as needed
model_dir="vlm_sft40"

echo "=================================="
echo "Starting training process..."
echo "Model directory: $model_dir"
echo "=================================="

# Training phase
PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
NPROC_PER_NODE=8 \
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 \
swift sft \
    --model 'models/vlm_pt39/checkpoint-7337' \
    --model_type qwen3_vl \
    --dataset 'datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_remove_proof_task12.jsonl' \
    --split_dataset_ratio 0.005 \
    --columns '{"llm_input_renamed": "query", "llm_output_renamed": "response", "image_path": "images"}' \
    --system 'You are a helpful assistant.' \
    --max_length 2048 \
    --packing true \
    --padding_free true \
    --dataset_num_proc 16 \
    --dataloader_num_workers 4 \
    --train_type full \
    --freeze_llm false \
    --freeze_vit true \
    --freeze_aligner false \
    --torch_dtype bfloat16 \
    --deepspeed zero1 \
    --attn_impl flash_attn \
    --use_liger_kernel true \
    --num_train_epochs 1 \
    --warmup_ratio 0.1 \
    --per_device_train_batch_size 1 \
    --gradient_accumulation_steps 8 \
    --per_device_eval_batch_size 1 \
    --learning_rate 1e-5 \
    --adam_beta1 0.9 \
    --adam_beta2 0.999 \
    --save_steps 10000 \
    --logging_steps 500 \
    --output_dir models/$model_dir \
    --add_version false \
    --save_only_model true \
    --full_determinism true

# Check if training was successful
if [ $? -ne 0 ]; then
    echo "=================================="
    echo "✗ Training failed! Exiting..."
    echo "=================================="
    exit 1
fi

echo "=================================="
echo "✓ Training completed successfully!"
echo "=================================="

# Find the latest checkpoint
latest_checkpoint=$(ls -td models/$model_dir/checkpoint-* 2>/dev/null | head -1 | xargs basename)

if [ -z "$latest_checkpoint" ]; then
    echo "✗ No checkpoint found in models/$model_dir/"
    exit 1
fi

echo "=================================="
echo "Starting evaluation process..."
echo "Latest checkpoint: $latest_checkpoint"
echo "=================================="

# Evaluation phase
export CUDA_VISIBLE_DEVICES=1,2,3,4,5,6,7
export RAY_memory_usage_threshold=0.95

# Dataset options for evaluation
datasets=(
    "imo_2018_p1.txt"
    # "imo_102_requires_aux.txt"
    # "imo_2012_p5.txt"
    # "dev_imo.txt"
)

# Decoding configurations (decoding_size beam_size)
configs=(
    "32 512"
)

# Search depth options
search_depths=(
    "4"
)

echo "Evaluation configuration:"
echo "  Datasets: ${datasets[@]}"
echo "  Checkpoint: $latest_checkpoint"
echo "  Total commands to execute: $((${#datasets[@]} * ${#configs[@]} * ${#search_depths[@]}))"
echo "=================================="

# Loop through all datasets
for dataset in "${datasets[@]}"; do
    # Loop through all configurations
    for config in "${configs[@]}"; do
        # Split configuration parameters
        read -r decoding_size beam_size <<< "$config"
        
        # Loop through all search depths
        for search_depth in "${search_depths[@]}"; do
            # Build complete command
            cmd="python scripts/evaluation_vlm.py --problems_path benchmarks/$dataset --model_path ./models/$model_dir/$latest_checkpoint --max_workers 40 --decoding_size $decoding_size --beam_size $beam_size --search_depth $search_depth --timeout 3600 --agent vlm"
        
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
done

echo "=================================="
echo "All tasks completed!"
echo "Training and evaluation finished for model: $model_dir"
echo "Checkpoint used for evaluation: $latest_checkpoint"
echo "=================================="
