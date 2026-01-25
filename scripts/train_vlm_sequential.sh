#!/bin/bash
export LOGLEVEL=WARNING

echo "=========================================="
echo "Starting training vlm_sft41..."
echo "=========================================="

# First model: vlm_sft41
model_dir="vlm_sft41"

PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
NPROC_PER_NODE=8 \
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 \
swift sft \
    --model 'models/vlm_pt39/checkpoint-7337' \
    --model_type qwen3_vl \
    --dataset 'datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_remove_proof_task2.jsonl' \
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

# Check if first training succeeded
if [ $? -ne 0 ]; then
    echo "=========================================="
    echo "WARNING: Training vlm_sft41 failed!"
    echo "Continuing with vlm_sft42 training..."
    echo "=========================================="
else
    echo "=========================================="
    echo "vlm_sft41 training completed successfully!"
    echo "=========================================="
fi

echo "=========================================="
echo "Starting training vlm_sft42..."
echo "=========================================="

# Second model: vlm_sft42
model_dir="vlm_sft42"

PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
NPROC_PER_NODE=8 \
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 \
swift sft \
    --model 'models/vlm_pt39/checkpoint-7337' \
    --model_type qwen3_vl \
    --dataset 'datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_remove_proof_task1.jsonl' \
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

# Check if second training succeeded
if [ $? -ne 0 ]; then
    echo "=========================================="
    echo "WARNING: Training vlm_sft42 failed!"
    echo "=========================================="
else
    echo "=========================================="
    echo "vlm_sft42 training completed successfully!"
    echo "=========================================="
fi

echo "=========================================="
echo "Training process completed!"
echo "vlm_sft41: trained with task2.jsonl"
echo "vlm_sft42: trained with task1.jsonl"
echo "=========================================="

echo ""
echo "=========================================="
echo "Starting evaluation for trained models..."
echo "=========================================="

# Evaluation configuration
export CUDA_VISIBLE_DEVICES=1,2,3,4,5,6,7
export RAY_memory_usage_threshold=0.95

# Evaluation datasets
eval_datasets=(
    "imo_2018_p1.txt"
    # "dev_imo.txt"
    # "imo_102_requires_aux.txt"
)

# Evaluation configurations (decoding_size beam_size)
eval_configs=(
    "32 512"
)

# Search depths
eval_search_depths=(
    "4"
)

# Models to evaluate (with their checkpoints)
eval_models=(
    "vlm_sft41"
    "vlm_sft42"
)

# Loop through each trained model
for eval_model in "${eval_models[@]}"; do
    echo "=========================================="
    echo "Evaluating model: $eval_model"
    echo "=========================================="
    
    # Find the latest checkpoint for this model
    if [ -d "models/$eval_model" ]; then
        # Get all checkpoints sorted by number
        latest_checkpoint=$(ls -d models/$eval_model/checkpoint-* 2>/dev/null | sort -t'-' -k2 -n | tail -1 | xargs basename 2>/dev/null)
        
        if [ -z "$latest_checkpoint" ]; then
            echo "No checkpoint found for $eval_model, skipping evaluation..."
            continue
        fi
        
        echo "Using checkpoint: $latest_checkpoint"
        
        # Loop through all evaluation datasets
        for eval_dataset in "${eval_datasets[@]}"; do
            # Loop through all evaluation configurations
            for eval_config in "${eval_configs[@]}"; do
                # Split configuration parameters
                read -r decoding_size beam_size <<< "$eval_config"
                
                # Loop through all search depths
                for search_depth in "${eval_search_depths[@]}"; do
                    # Build complete evaluation command
                    eval_cmd="python scripts/evaluation_vlm.py --problems_path benchmarks/$eval_dataset --model_path ./models/$eval_model/$latest_checkpoint --max_workers 40 --decoding_size $decoding_size --beam_size $beam_size --search_depth $search_depth --timeout 3600 --agent vlm"
                    
                    # Print current command to execute
                    echo "Executing evaluation:"
                    echo "$eval_cmd"
                    echo "----------------------------------"
                    
                    # Execute command
                    eval "$eval_cmd"
                    
                    # Check command execution status
                    if [ $? -eq 0 ]; then
                        echo "✓ Evaluation completed successfully"
                    else
                        echo "✗ Evaluation failed"
                    fi
                    
                    echo "=================================="
                done
            done
        done
        
        echo "Completed evaluation for: $eval_model"
        echo "=================================="
    else
        echo "Model directory models/$eval_model not found, skipping..."
    fi
done

echo ""
echo "=========================================="
echo "All training and evaluation tasks completed!"
echo "Models trained: ${eval_models[@]}"
echo "=========================================="
