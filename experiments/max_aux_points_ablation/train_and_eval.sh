#!/bin/bash
###############################################################################
# MAX_NEW_POINTS Ablation - Training and Evaluation Only
#
# 功能：对已生成的数据进行训练和评估
#
# 并行策略：
#   - 训练使用 GPU，同一时刻只有一个训练任务运行
#   - 评估使用 CPU，同一时刻只有一个评估任务运行
#   - 训练和评估可以并行（不同资源）
#
# 用法：
#   bash experiments/max_aux_points_ablation/train_and_eval.sh          # 自动跳过已完成阶段
#   bash experiments/max_aux_points_ablation/train_and_eval.sh --force  # 强制重新训练和评估
#
# 查看进度：
#   # 查看所有实验的完成状态
#   ls -lh experiments/max_aux_points_ablation/logs/*/.*_done
#
#   # 查看训练日志（实时）
#   tail -f experiments/max_aux_points_ablation/logs/sft35_maxaux2/training.log
#
#   # 查看评估日志（实时）
#   tail -f experiments/max_aux_points_ablation/logs/sft35_maxaux2/evaluation.log
#
#   # 查看训练进度（查找 loss 和 step）
#   grep -E "loss|step" experiments/max_aux_points_ablation/logs/sft35_maxaux2/training.log | tail -20
#
#   # 查看评估结果
#   grep -E "Solved|Score" experiments/max_aux_points_ablation/logs/sft35_maxaux2/evaluation.log
#
#   # 检查哪些实验正在运行
#   ps aux | grep -E "swift sft|evaluation.py" | grep -v grep
#
#   # 查看 GPU 使用情况
#   nvidia-smi
#
###############################################################################

set -e

# Parse command line arguments
FORCE=false
for arg in "$@"; do
    case $arg in
        --force)
            FORCE=true
            echo "[WARN] Force mode: all completed phases will be re-run"
            ;;
        --help|-h)
            echo "Usage: bash $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --force   Force re-run all phases (ignore completed markers)"
            echo "  --help    Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            exit 1
            ;;
    esac
done

export LOGLEVEL=WARNING

# Trap signals for graceful shutdown
trap 'handle_interrupt' SIGINT SIGTERM

# Global variables for cleanup
CURRENT_TRAIN_PID=0
CURRENT_EVAL_PID=0

handle_interrupt() {
    echo ""
    log_info "Received interrupt signal, cleaning up..."

    # Kill background processes if running
    if [ "$CURRENT_TRAIN_PID" -ne 0 ]; then
        log_info "Stopping training process (PID: $CURRENT_TRAIN_PID)..."
        kill -TERM "$CURRENT_TRAIN_PID" 2>/dev/null || true
    fi

    if [ "$CURRENT_EVAL_PID" -ne 0 ]; then
        log_info "Stopping evaluation process (PID: $CURRENT_EVAL_PID)..."
        kill -TERM "$CURRENT_EVAL_PID" 2>/dev/null || true
    fi

    log_info "Cleanup complete. You can resume by running the script again."
    exit 130
}

###############################################
# Global Configuration
###############################################

EXP_ROOT="experiments/max_aux_points_ablation"

# Training parameters
BASE_MODEL="Qwen/Qwen3-0.6B-Base"
CUDA_DEVICES="0,1,2"
NPROC_PER_NODE=3

# Evaluation parameters
EVAL_DATASETS=(
    "dev_imo.txt"
    "imo_95_reorder.txt"
)
EVAL_CONFIGS=(
    "32 512"
)
EVAL_MAX_WORKERS=40
EVAL_SEARCH_DEPTH=4

# Experiment groups
EXPERIMENTS=(
    "sft35 2"
    "sft36 4"
    "sft37 6"
    "sft38 8"
)

###############################################
# Utility Functions
###############################################

log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2
}

log_section() {
    echo ""
    echo "=========================================="
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "=========================================="
}

###############################################
# Phase Functions
###############################################

# Wait for data to be ready
wait_for_data() {
    local model_name="$1"
    local log_dir="$2"
    local data_ready_file="$log_dir/.data_ready"

    while [ ! -f "$data_ready_file" ]; do
        log_info "[$model_name] Waiting for data generation to complete..." >&2
        sleep 30
    done

    local dataset_path
    dataset_path=$(cat "$data_ready_file")

    if [ ! -f "$dataset_path" ]; then
        log_error "[$model_name] Data file not found: $dataset_path" >&2
        return 1
    fi

    log_info "[$model_name] Data ready: $dataset_path" >&2
    echo "$dataset_path"
}

# Phase 1: Training (GPU)
run_training() {
    local model_name="$1"
    local dataset_path="$2"
    local log_dir="$3"

    log_section "[$model_name] Training"
    log_info "Dataset: $dataset_path"
    log_info "Model dir: models/$model_name"

    PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True' \
    NPROC_PER_NODE=$NPROC_PER_NODE \
    CUDA_VISIBLE_DEVICES=$CUDA_DEVICES \
    swift sft \
        --model $BASE_MODEL \
        --dataset "$dataset_path" \
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
        --per_device_train_batch_size 7 \
        --per_device_eval_batch_size 3 \
        --gradient_accumulation_steps 1 \
        --learning_rate 1e-4 \
        --adam_beta1 0.9 \
        --adam_beta2 0.999 \
        --save_steps 10000 \
        --logging_steps 500 \
        --output_dir models/$model_name \
        --add_version false \
        --save_only_model true \
        2>&1 | tee "$log_dir/training.log"

    touch "$log_dir/.train_done"
    log_info "[$model_name] Training completed"
}

# Phase 2: Evaluation (CPU)
run_evaluation() {
    local model_name="$1"
    local log_dir="$2"

    log_section "[$model_name] Evaluation"

    local checkpoint_dir="models/$model_name"
    if [ ! -d "$checkpoint_dir" ]; then
        log_error "[$model_name] Model directory not found: $checkpoint_dir"
        return 1
    fi

    local latest_checkpoint
    latest_checkpoint=$(ls -d "$checkpoint_dir"/checkpoint-* 2>/dev/null | sort -V | tail -1)
    if [ -z "$latest_checkpoint" ]; then
        log_info "[$model_name] No checkpoint found, using model root"
        latest_checkpoint="$checkpoint_dir"
    else
        latest_checkpoint=$(basename "$latest_checkpoint")
        latest_checkpoint="$checkpoint_dir/$latest_checkpoint"
    fi

    log_info "[$model_name] Using checkpoint: $latest_checkpoint"

    for dataset in "${EVAL_DATASETS[@]}"; do
        for config in "${EVAL_CONFIGS[@]}"; do
            read -r decoding_size beam_size <<< "$config"

            log_info "[$model_name] Evaluating: $dataset (d${decoding_size}_b${beam_size})"

            script -q -c "python scripts/evaluation.py \
                --problems_path benchmarks/$dataset \
                --model_path \"$latest_checkpoint\" \
                --log_dir \"$log_dir\" \
                --max_workers $EVAL_MAX_WORKERS \
                --decoding_size $decoding_size \
                --beam_size $beam_size \
                --search_depth $EVAL_SEARCH_DEPTH" /dev/null | tee -a "$log_dir/evaluation.log"

            if [ $? -eq 0 ]; then
                log_info "✓ [$model_name] Evaluation completed: $dataset"
            else
                log_error "✗ [$model_name] Evaluation failed: $dataset"
            fi
        done
    done

    touch "$log_dir/.eval_done"
}

###############################################
# Parallel Pipeline Orchestrator
###############################################

run_parallel_pipeline() {
    log_section "Starting Training and Evaluation Pipeline"
    log_info "Experiments: ${#EXPERIMENTS[@]}"
    echo ""

    local num_exps=${#EXPERIMENTS[@]}

    declare -a EXP_NAMES
    declare -a EXP_MAX_AUX
    declare -a EXP_LOG_DIRS
    declare -a TRAIN_DONE
    declare -a EVAL_DONE

    # Initialize
    for i in $(seq 0 $((num_exps - 1))); do
        read -r name max_aux <<< "${EXPERIMENTS[$i]}"
        EXP_NAMES[$i]="$name"
        EXP_MAX_AUX[$i]="$max_aux"
        EXP_LOG_DIRS[$i]="$EXP_ROOT/logs/${name}_maxaux${max_aux}"
        TRAIN_DONE[$i]=0
        EVAL_DONE[$i]=0

        mkdir -p "${EXP_LOG_DIRS[$i]}"

        if [ "$FORCE" = false ]; then
            if [ -f "${EXP_LOG_DIRS[$i]}/.eval_done" ]; then
                TRAIN_DONE[$i]=1
                EVAL_DONE[$i]=1
                log_info "[SKIP] ${name}: all phases already completed"
            elif [ -f "${EXP_LOG_DIRS[$i]}/.train_done" ]; then
                TRAIN_DONE[$i]=1
                log_info "[SKIP] ${name}: training already completed, will resume at evaluation"
            fi
        else
            rm -f "${EXP_LOG_DIRS[$i]}/.train_done"
            rm -f "${EXP_LOG_DIRS[$i]}/.eval_done"
        fi
    done

    local train_pid=0
    local eval_pid=0
    local next_train=0
    local next_eval=0

    # Fast-forward to first incomplete experiment
    for i in $(seq 0 $((num_exps - 1))); do
        if [ "${TRAIN_DONE[$i]}" -eq 0 ]; then
            next_train=$i
            break
        fi
        next_train=$((i + 1))
    done

    # Fast-forward evaluation to first incomplete
    for i in $(seq 0 $((num_exps - 1))); do
        if [ "${EVAL_DONE[$i]}" -eq 1 ]; then
            next_eval=$((i + 1))
        elif [ "${TRAIN_DONE[$i]}" -eq 1 ] && [ "${EVAL_DONE[$i]}" -eq 0 ]; then
            # Training done but eval not — start here
            next_eval=$i
            break
        else
            # Training not done yet — will wait
            next_eval=$i
            break
        fi
    done

    # Main loop
    while true; do
        local all_done=1
        for i in $(seq 0 $((num_exps - 1))); do
            if [ "${EVAL_DONE[$i]}" -ne 1 ]; then
                all_done=0
                break
            fi
        done
        if [ "$all_done" -eq 1 ]; then
            break
        fi

        # Check if training process finished
        if [ "$train_pid" -ne 0 ]; then
            if ! kill -0 "$train_pid" 2>/dev/null; then
                wait "$train_pid" 2>/dev/null
                local train_idx=$((next_train - 1))
                local exit_code=$?
                if [ $exit_code -eq 0 ]; then
                    TRAIN_DONE[$train_idx]=1
                    log_info "✓ Training complete for ${EXP_NAMES[$train_idx]}"
                else
                    log_error "✗ Training failed for ${EXP_NAMES[$train_idx]} (exit code: $exit_code)"
                    TRAIN_DONE[$train_idx]=1
                    EVAL_DONE[$train_idx]=1
                fi
                train_pid=0
                CURRENT_TRAIN_PID=0
            fi
        fi

        # Check if evaluation process finished
        if [ "$eval_pid" -ne 0 ]; then
            if ! kill -0 "$eval_pid" 2>/dev/null; then
                wait "$eval_pid" 2>/dev/null
                local eval_idx=$((next_eval - 1))
                local exit_code=$?
                if [ $exit_code -eq 0 ]; then
                    EVAL_DONE[$eval_idx]=1
                    log_info "✓ Evaluation complete for ${EXP_NAMES[$eval_idx]}"
                else
                    log_error "✗ Evaluation failed for ${EXP_NAMES[$eval_idx]} (exit code: $exit_code)"
                    EVAL_DONE[$eval_idx]=1
                fi
                eval_pid=0
                CURRENT_EVAL_PID=0
            fi
        fi

        # Start next training if no training is running
        if [ "$train_pid" -eq 0 ] && [ "$next_train" -lt "$num_exps" ]; then
            if [ "${TRAIN_DONE[$next_train]}" -eq 0 ]; then
                local dataset_path
                dataset_path=$(wait_for_data "${EXP_NAMES[$next_train]}" "${EXP_LOG_DIRS[$next_train]}")

                if [ -n "$dataset_path" ]; then
                    log_info "Starting training for ${EXP_NAMES[$next_train]}"
                    (run_training "${EXP_NAMES[$next_train]}" "$dataset_path" "${EXP_LOG_DIRS[$next_train]}") &
                    train_pid=$!
                    CURRENT_TRAIN_PID=$train_pid
                    next_train=$((next_train + 1))
                else
                    log_error "Failed to get dataset for ${EXP_NAMES[$next_train]}"
                    TRAIN_DONE[$next_train]=1
                    EVAL_DONE[$next_train]=1
                    next_train=$((next_train + 1))
                fi
            else
                next_train=$((next_train + 1))
            fi
        fi

        # Start next evaluation if no evaluation is running
        if [ "$eval_pid" -eq 0 ] && [ "$next_eval" -lt "$num_exps" ]; then
            # Find next experiment ready for evaluation (training done but eval not done)
            local found_eval=0
            for i in $(seq $next_eval $((num_exps - 1))); do
                if [ "${EVAL_DONE[$i]}" -eq 0 ] && [ "${TRAIN_DONE[$i]}" -eq 1 ]; then
                    log_info "Starting evaluation for ${EXP_NAMES[$i]}"
                    (run_evaluation "${EXP_NAMES[$i]}" "${EXP_LOG_DIRS[$i]}") &
                    eval_pid=$!
                    CURRENT_EVAL_PID=$eval_pid
                    next_eval=$((i + 1))
                    found_eval=1
                    break
                fi
            done
            # If no ready evaluation found, advance next_eval to skip completed ones
            if [ "$found_eval" -eq 0 ]; then
                while [ "$next_eval" -lt "$num_exps" ] && [ "${EVAL_DONE[$next_eval]}" -eq 1 ]; do
                    next_eval=$((next_eval + 1))
                done
            fi
        fi

        sleep 10
    done

    log_section "All Experiments Completed!"

    echo ""
    echo "┌──────────┬─────────────────────┬──────────────────────────────┐"
    echo "│ Model    │ max_auxiliary_points │ Status                       │"
    echo "├──────────┼─────────────────────┼──────────────────────────────┤"
    for i in $(seq 0 $((num_exps - 1))); do
        local status="✓ Done"
        if [ "${EVAL_DONE[$i]}" -ne 1 ]; then
            status="✗ Failed"
        fi
        printf "│ %-8s │ %-19s │ %-28s │\n" \
            "${EXP_NAMES[$i]}" "${EXP_MAX_AUX[$i]}" "$status"
    done
    echo "└──────────┴─────────────────────┴──────────────────────────────┘"
    echo ""
}

###############################################
# Main Entry Point
###############################################

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║    MAX_AUXILIARY_POINTS Ablation - Train & Eval            ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  sft35: max_auxiliary_points=2                             ║"
echo "║  sft36: max_auxiliary_points=4                             ║"
echo "║  sft37: max_auxiliary_points=6                             ║"
echo "║  sft38: max_auxiliary_points=8                             ║"
echo "║                                                            ║"
echo "║  Training: GPU 0,1,2 (sequential)                         ║"
echo "║  Evaluation: CPU (sequential)                             ║"
echo "║  Training and Evaluation can run in parallel              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

run_parallel_pipeline

