#!/bin/bash
export LOGLEVEL=WARNING

# Evaluation V1

# Model directory - modify this as needed
model_dir="sft28"

export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export RAY_memory_usage_threshold=0.95

# Dataset options
datasets=(
    # "imo_102_requires_aux.txt"
    # "imo_2012_p5.txt"
    # "dev_imo.txt"
    # "imo_2000_p6.txt"
    # "imo_2004_p1.txt"
    # "imo_2008_p1.txt"
    # "imo_2008_p6.txt"
    # "imo_2011_p6.txt"
    # "imo_2018_p1.txt"
    # "imo_2019_p2.txt"
    "imo_2020_p1.txt"
    # "imo_102_supple.txt"
    # "imo_102_requires_aux_less.txt"
    # "imo_102_requires_aux_less1.txt" 
    # "imo_102_requires_aux_less2.txt"
    # "imo_102_requires_aux_less3.txt"
    # "dev_jgex.txt" 
    # "hageo_409.txt"
)

# Decoding configurations (decoding_size beam_size)
configs=(
    # "8 64"
    "32 512"
)

# Search depth options
search_depths=(
    "4"
)

timeout=3600

# Checkpoint options - modify this list as needed
checkpoints=(
    # "checkpoint-19622"
    "checkpoint-6288"
    # "checkpoint-699"
    # "checkpoint-610"
    # "checkpoint-730"
    # "checkpoint-763"
    # "checkpoint-175"
    # "checkpoint-566"
    # "checkpoint-609"
    # "checkpoint-977"
    # "checkpoint-7296"	
    # "checkpoint-644"
    # "checkpoint-628"
    # "checkpoint-5911"
    # "checkpoint-5915"
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

echo "Starting evaluation tasks (V1)..."
echo "Will process ${#checkpoints[@]} checkpoints, ${#datasets[@]} datasets, ${#configs[@]} configurations, and ${#search_depths[@]} search depths"
echo "Total commands to execute: $((${#checkpoints[@]} * ${#datasets[@]} * ${#configs[@]} * ${#search_depths[@]}))"
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
            
            # Loop through all search depths
            for search_depth in "${search_depths[@]}"; do
                # Build complete command - use evaluation_v1.py instead of evaluation.py
                cmd="python scripts/evaluation_v1.py --problems_path benchmarks/$dataset --model_path ./models/$model_dir/$checkpoint --max_workers 40 --decoding_size $decoding_size --beam_size $beam_size --search_depth $search_depth --timeout $timeout"
            
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
    
    echo "Completed checkpoint: $checkpoint"
    echo "=================================="
done

echo "All evaluation tasks (V1) completed!"
echo "Processed ${#checkpoints[@]} checkpoints total."
