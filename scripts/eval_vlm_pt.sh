#!/bin/bash
set -e

export LOGLEVEL="${LOGLEVEL:-WARNING}"

REPO_ROOT="${REPO_ROOT:-/C20545/home/wangzi/GenesisGeo}"
MODEL_DIR="${MODEL_DIR:-$REPO_ROOT/models/vlm_pt39_new}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs/$(date +%m%d_%H%M%S)_$(basename "$MODEL_DIR")}"

EVAL_DATASETS_STR="${EVAL_DATASETS_STR:-dev_imo.txt imo_95_reorder.txt}"
EVAL_CONFIGS_STR="${EVAL_CONFIGS_STR:-32 512}"

read -r -a EVAL_DATASETS <<< "$EVAL_DATASETS_STR"
IFS=';' read -r -a EVAL_CONFIGS <<< "$EVAL_CONFIGS_STR"

EVAL_MAX_WORKERS="${EVAL_MAX_WORKERS:-40}"
EVAL_SEARCH_DEPTH="${EVAL_SEARCH_DEPTH:-4}"
EVAL_TIMEOUT="${EVAL_TIMEOUT:-3600}"
EVAL_AGENT="${EVAL_AGENT:-vlm}"

mkdir -p "$LOG_DIR"

echo "=========================================="
echo "VLM PT Evaluation"
echo "=========================================="
echo "Model Dir : $MODEL_DIR"
echo "Log Dir   : $LOG_DIR"
echo "Agent     : $EVAL_AGENT"
echo "=========================================="

echo ""
echo "--- Step 1: Finding checkpoint ---"

if [ ! -d "$MODEL_DIR" ]; then
    echo "Model directory not found: $MODEL_DIR"
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
echo "--- Step 2: Evaluation ---"
echo "  Datasets: ${EVAL_DATASETS[@]}"
echo "  Configs : ${EVAL_CONFIGS[@]}"

for dataset in "${EVAL_DATASETS[@]}"; do
    for config in "${EVAL_CONFIGS[@]}"; do
        read -r decoding_size beam_size <<< "$config"

        cmd="python $REPO_ROOT/scripts/evaluation.py \
            --problems_path $REPO_ROOT/benchmarks/$dataset \
            --model_path $CHECKPOINT_PATH \
            --log_dir $LOG_DIR \
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
            echo "Evaluation completed: $dataset (d${decoding_size}_b${beam_size})"
        else
            echo "Evaluation failed: $dataset"
        fi
        echo "=========================================="
    done
done

echo ""
echo "=========================================="
echo "Evaluation completed"
echo "  Model: $(basename "$MODEL_DIR")"
echo "  Path : $CHECKPOINT_PATH"
echo "  Logs : $LOG_DIR"
echo "=========================================="
