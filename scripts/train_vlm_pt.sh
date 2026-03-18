#!/bin/bash
export LOGLEVEL=WARNING

# Model directory - modify this as needed
model_dir="vlm_pt39"

MASTER_PORT=29700 \
PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
NPROC_PER_NODE=3 \
CUDA_VISIBLE_DEVICES=1,2,3 \
swift pt \
    --model Qwen/Qwen3-VL-2B-Instruct \
    --dataset '/C20545/home/wangzi/GenesisGeo_data_models/datasets/0123/geometry_clauses10_samples1M_aux_updated_img512_inverted_pt_new.jsonl' \
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
    --output_dir models/$model_dir \
    --add_version false \
    --save_only_model true \
    --full_determinism true \
    # --model Qwen/Qwen3-VL-2B-Instruct \
    # --model OpenGVLab/InternVL3_5-2B-Pretrained \
    # --model Qwen/Qwen3-VL-2B-Instruct \
    # --system 'You are a helpful assistant.' \
    # --target_modules all-linear \
    # --resume_from_checkpoint models/$model_dir/checkpoint-20000 \
    # --resume_only_model true \
    # --truncation_strategy left \
    # --lr_scheduler_type cosine_with_min_lr \
    # --lr_scheduler_kwargs '{"min_lr_rate":0.1}' \
    # --use_chat_template false \


# Dataset options
datasets=(
    # "imo_102_requires_aux.txt"
    # "imo_2012_p5.txt"
    # "dev_imo.txt"
    # "imo_2008_p1.txt"
    # "imo_2004_p1.txt"
    # "imo_2018_p1.txt"
    # "imo_102_supple.txt"
    # "imo_102_requires_aux_less.txt"
    # "imo_102_requires_aux_less1.txt" 
    # "imo_102_requires_aux_less2.txt"
    # "imo_102_requires_aux_less3.txt"
    # "dev_jgex.txt" 
)

# Decoding configurations (decoding_size beam_size)
configs=(
    # "8 64"
    "32 512"
)

# Checkpoint options - modify this list as needed
checkpoints=(
    # "checkpoint-2958"
    # "checkpoint-986"
    # "checkpoint-1972"
    # "checkpoint-198"
    # "checkpoint-1299"
    # "checkpoint-241"
    # "checkpoint-5918"
    # "checkpoint-218"
    # "checkpoint-582"
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
            # Split configunration parameters
            read -r decoding_size beam_size <<< "$config"
            
            # Build complete command
            cmd="python scripts/evaluation_vlm.py --problems_path benchmarks/$dataset --model_path ./models/$model_dir/$checkpoint --max_workers 40 --decoding_size $decoding_size --beam_size $beam_size --search_depth 4 --timeout 3600"
            
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

