#!/bin/bash
export LOGLEVEL=WARNING

# Evaluation

# Model directory - modify this as needed
model_dir="vlm_sft20"

export CUDA_VISIBLE_DEVICES=1,2,3,4,5,6,7
# export CUDA_VISIBLE_DEVICES=7
export RAY_memory_usage_threshold=0.95

# Dataset options
datasets=(
    # "imo_102_requires_aux.txt"
    # "imo_2012_p5.txt"
    # "dev_imo.txt"
    # "imo_2008_p1.txt"
    # "imo_2008_p1b.txt"
    # "imo_2004_p1.txt"
    # "imo_2018_p1.txt"
    # "imo_102_supple.txt"
    # "imo_102_requires_aux_less.txt"
    # "imo_102_requires_aux_less1.txt" 
    # "imo_102_requires_aux_less2.txt"
    # "imo_102_requires_aux_less3.txt"
    # "dev_jgex.txt" 
    "hageo_409.txt"
    # "2007USATSTp5.gex.txt"
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
    # "checkpoint-203"
    # "checkpoint-1294"
    "checkpoint-1972"
    # "checkpoint-198"
    # "checkpoint-1299"
    # "checkpoint-241"
    # "checkpoint-5918"
    # "checkpoint-218"
    # "checkpoint-582"
    # "checkpoint-10000"
    # "checkpoint-20000"
    # "checkpoint-40000"
    # "checkpoint-47751"
    # "checkpoint-57282"
    # "checkpoint-61961"
    # "checkpoint-54667"
    # "checkpoint-50000"
    # "checkpoint-29694"
    # "checkpoint-20000"
    # "checkpoint-18023"
    # "checkpoint-10000"
    # "checkpoint-49437"
    # "checkpoint-40000"
    # "checkpoint-30000"
    # "checkpoint-64209"
    # "checkpoint-54667"
    # "checkpoint-64749"
    # "checkpoint-60000"
    # "checkpoint-50000"
    # "checkpoint-40000"
    # "checkpoint-30000"
    # "checkpoint-20000"
    # "checkpoint-10000"
    # "checkpoint-165355"
    # "checkpoint-160000"
    # "checkpoint-150000"
    # "checkpoint-130000"
    # "checkpoint-110000"
    # "checkpoint-90000"
    # "checkpoint-80000"
    # "checkpoint-70000"
    # "checkpoint-60000"
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
            cmd="python scripts/evaluation.py --problems_path benchmarks/$dataset --model_path ./models/$model_dir/$checkpoint --max_workers 40 --decoding_size $decoding_size --beam_size $beam_size --search_depth 4 --timeout 3600 --agent vlm"
            
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
