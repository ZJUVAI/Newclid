#!/bin/bash
###############################################################################
# MAX_NEW_POINTS Ablation Experiment
# 
# 实验目的：探究 max_auxiliary_points 参数对模型性能的影响
# 
# 实验组配置：
#   sft35: max_auxiliary_points=2
#   sft36: max_auxiliary_points=4
#   sft37: max_auxiliary_points=6
#   sft38: max_auxiliary_points=8
#
# 每组流程：数据生成 → 模型训练 → 模型评估
# 
# 异步调度策略：
#   - 数据生成仅使用 CPU，可以与 GPU 训练并行
#   - 训练使用 GPU，同一时刻只有一个训练任务运行
#   - 当实验 i 的训练完成后，立即启动实验 i+1 的训练（若其数据已就绪）
#   - 评估在对应训练完成后立即执行
#
# 时序图示例（4个实验）：
#   时间 →
#   实验1: [数据生成1] [训练1        ] [评估1]
#   实验2:              [数据生成2    ] ----等待训练1和数据2完成---- [训练2        ] [评估2]
#   实验3:                             [数据生成3              ] --------等待---- [训练3        ] [评估3]
#   实验4:                                                      [数据生成4    ] --等待-------- [训练4        ] [评估4]
#
# 用法：
#   bash experiments/max_aux_points_ablation/run_ablation.sh          # 自动跳过已完成阶段
#   bash experiments/max_aux_points_ablation/run_ablation.sh --force  # 清除标记，全部重跑
#
# 注意事项：
#   - 脚本默认支持断点续跑：通过 .data_ready / .train_done / .eval_done 标记文件
#     自动检测已完成的阶段并跳过，中断后重新运行即可自动接续
#   - 使用 --force 可清除所有标记，强制全部重跑
#   - 确保有足够的磁盘空间（每组 200k 数据约占 1-3 GB）
#   - 数据生成使用 32 个 CPU 线程
#   - 训练使用 GPU 0,1,2（3 卡）
#   - 评估使用 CPU（40 workers）
###############################################################################

set -e  # Exit on error

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
            echo ""
            echo "By default, the script automatically detects and skips completed phases."
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            exit 1
            ;;
    esac
done

export LOGLEVEL=WARNING

###############################################
# Global Configuration
###############################################

# Experiment root directory
EXP_ROOT="experiments/max_aux_points_ablation"

# Data generation parameters (shared across experiments)
N_CLAUSES=10
N_SAMPLES=200000
N_THREADS=32
IMG_FLAG=0
AUX_ONLY=1
ADD_AUXILIARY=true
PRUNE=true

# Training parameters (shared)
BASE_MODEL="Qwen/Qwen3-0.6B-Base"
CUDA_DEVICES="0,1,2"
NPROC_PER_NODE=3

# Evaluation parameters (shared)
EVAL_DATASETS=(
    "dev_imo.txt"
    "imo_95_reorder.txt"
)
EVAL_CONFIGS=(
    "32 512"
)
EVAL_MAX_WORKERS=40
EVAL_SEARCH_DEPTH=4

# Experiment groups: (model_name max_auxiliary_points)
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

# Save experiment configuration as JSON
save_experiment_config() {
    local exp_dir="$1"
    local model_name="$2"
    local max_aux_points="$3"
    local data_dir="$4"

    cat > "$exp_dir/experiment_config.json" << EOF
{
    "experiment_name": "$model_name",
    "timestamp": "$(date '+%Y-%m-%d %H:%M:%S')",
    "data_generation": {
        "n_clauses": $N_CLAUSES,
        "n_samples": $N_SAMPLES,
        "n_threads": $N_THREADS,
        "img": $IMG_FLAG,
        "aux_only": $AUX_ONLY,
        "add_auxiliary": $ADD_AUXILIARY,
        "prune": $PRUNE,
        "max_auxiliary_points": $max_aux_points
    },
    "training": {
        "base_model": "$BASE_MODEL",
        "cuda_devices": "$CUDA_DEVICES",
        "nproc_per_node": $NPROC_PER_NODE,
        "per_device_train_batch_size": 7,
        "per_device_eval_batch_size": 3,
        "learning_rate": "1e-4",
        "num_train_epochs": 1
    },
    "evaluation": {
        "datasets": "$(IFS=,; echo "${EVAL_DATASETS[*]}")",
        "configs": "$(IFS=,; echo "${EVAL_CONFIGS[*]}")",
        "max_workers": $EVAL_MAX_WORKERS,
        "search_depth": $EVAL_SEARCH_DEPTH
    },
    "data_directory": "$data_dir",
    "model_directory": "models/$model_name"
}
EOF
}

###############################################
# Phase Functions
###############################################

# Phase 1: Data Generation (CPU only)
run_data_generation() {
    local model_name="$1"
    local max_aux_points="$2"
    local data_dir="$3"
    local log_dir="$4"

    log_section "[$model_name] Data Generation (max_auxiliary_points=$max_aux_points)"

    mkdir -p "$data_dir"

    python src/newclid/generation_new/pipeline.py \
        --n_clauses $N_CLAUSES \
        --n_samples $N_SAMPLES \
        --n_threads $N_THREADS \
        --dir "$data_dir/" \
        --img $IMG_FLAG \
        --aux_only $AUX_ONLY \
        --add_auxiliary $ADD_AUXILIARY \
        --prune $PRUNE \
        --max_auxiliary_points $max_aux_points \
        2>&1 | tee "$log_dir/data_generation.log"

    # Find generated dataset file
    local dataset_path
    dataset_path=$(find "$data_dir" -name "*.jsonl" -type f | head -1)

    if [ -z "$dataset_path" ]; then
        log_error "[$model_name] No dataset file found in $data_dir"
        return 1
    fi

    log_info "[$model_name] Dataset generated: $dataset_path"

    # Run dataset analysis
    if [ -f "scripts/analyze_dataset.py" ]; then
        python scripts/analyze_dataset.py "$dataset_path" > "$log_dir/dataset_analysis.txt" 2>&1 || true
        log_info "[$model_name] Dataset analysis saved"
    fi

    # Write dataset path to a flag file for the training phase to pick up
    echo "$dataset_path" > "$log_dir/.data_ready"
}

# Phase 2: Training (GPU)
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

    # Mark training as complete
    touch "$log_dir/.train_done"
    log_info "[$model_name] Training completed"
}

# Phase 3: Evaluation (CPU)
run_evaluation() {
    local model_name="$1"
    local log_dir="$2"

    log_section "[$model_name] Evaluation"

    # Find latest checkpoint
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

            python scripts/evaluation.py \
                --problems_path benchmarks/$dataset \
                --model_path "$latest_checkpoint" \
                --log_dir "$log_dir" \
                --max_workers $EVAL_MAX_WORKERS \
                --decoding_size $decoding_size \
                --beam_size $beam_size \
                --search_depth $EVAL_SEARCH_DEPTH \
                2>&1 | tee -a "$log_dir/evaluation.log"

            if [ $? -eq 0 ]; then
                log_info "✓ [$model_name] Evaluation completed: $dataset"
            else
                log_error "✗ [$model_name] Evaluation failed: $dataset"
            fi
        done
    done

    # Mark evaluation as complete
    touch "$log_dir/.eval_done"
}

###############################################
# Async Pipeline Orchestrator
###############################################

run_async_pipeline() {
    log_section "Starting Async Ablation Pipeline"
    log_info "Experiments: ${#EXPERIMENTS[@]}"
    log_info "Parameters under test: max_auxiliary_points = 2, 4, 6, 8"
    log_info "Data samples per experiment: $N_SAMPLES"
    echo ""

    local num_exps=${#EXPERIMENTS[@]}
    
    # Arrays to track state for each experiment
    declare -a EXP_NAMES
    declare -a EXP_MAX_AUX
    declare -a EXP_DATA_DIRS
    declare -a EXP_LOG_DIRS
    declare -a DATA_GEN_PIDS      # PID of background data generation
    declare -a DATA_READY          # 1 if data generation is complete
    declare -a TRAIN_DONE          # 1 if training is complete
    declare -a EVAL_DONE           # 1 if evaluation is complete

    # Initialize experiment metadata
    for i in $(seq 0 $((num_exps - 1))); do
        read -r name max_aux <<< "${EXPERIMENTS[$i]}"
        EXP_NAMES[$i]="$name"
        EXP_MAX_AUX[$i]="$max_aux"
        EXP_DATA_DIRS[$i]="$EXP_ROOT/data/${name}_maxaux${max_aux}"
        EXP_LOG_DIRS[$i]="$EXP_ROOT/logs/${name}_maxaux${max_aux}"
        DATA_GEN_PIDS[$i]=0
        DATA_READY[$i]=0
        TRAIN_DONE[$i]=0
        EVAL_DONE[$i]=0

        mkdir -p "${EXP_LOG_DIRS[$i]}"
        mkdir -p "${EXP_DATA_DIRS[$i]}"

        # Detect completed phases from previous runs (skip if --force)
        if [ "$FORCE" = false ]; then
            if [ -f "${EXP_LOG_DIRS[$i]}/.eval_done" ]; then
                DATA_READY[$i]=1
                TRAIN_DONE[$i]=1
                EVAL_DONE[$i]=1
                log_info "[SKIP] ${name}: all phases already completed"
            elif [ -f "${EXP_LOG_DIRS[$i]}/.train_done" ]; then
                DATA_READY[$i]=1
                TRAIN_DONE[$i]=1
                log_info "[SKIP] ${name}: data+training already completed, will resume at evaluation"
            elif [ -f "${EXP_LOG_DIRS[$i]}/.data_ready" ]; then
                DATA_READY[$i]=1
                log_info "[SKIP] ${name}: data generation already completed, will resume at training"
            fi
        else
            # Force mode: remove old markers
            rm -f "${EXP_LOG_DIRS[$i]}/.data_ready"
            rm -f "${EXP_LOG_DIRS[$i]}/.train_done"
            rm -f "${EXP_LOG_DIRS[$i]}/.eval_done"
        fi

        # Save config
        save_experiment_config \
            "${EXP_LOG_DIRS[$i]}" \
            "$name" \
            "$max_aux" \
            "${EXP_DATA_DIRS[$i]}"
    done

    # =========================================
    # Phase 1: Start first data generation (skip if already done)
    # =========================================
    if [ "${DATA_READY[0]}" -eq 0 ]; then
        log_info "Starting data generation for experiment 0: ${EXP_NAMES[0]} (max_aux=${EXP_MAX_AUX[0]})"
        run_data_generation "${EXP_NAMES[0]}" "${EXP_MAX_AUX[0]}" "${EXP_DATA_DIRS[0]}" "${EXP_LOG_DIRS[0]}" &
        DATA_GEN_PIDS[0]=$!
    fi

    # =========================================
    # Determine resume points:
    #   next_data_gen  = first experiment whose data is not ready and not in progress
    #   next_train     = first experiment whose training is not done
    # =========================================
    local next_data_gen=1
    local next_train=0
    local next_eval=0
    local prev_train_done=1

    # Fast-forward next_data_gen past already-completed or already-started experiments
    # Experiment 0 is handled above; scan from 1
    for i in $(seq 1 $((num_exps - 1))); do
        if [ "${DATA_READY[$i]}" -eq 1 ]; then
            next_data_gen=$((i + 1))
        else
            break
        fi
    done

    # Fast-forward next_train past already-trained experiments
    for i in $(seq 0 $((num_exps - 1))); do
        if [ "${EVAL_DONE[$i]}" -eq 1 ]; then
            next_train=$((i + 1))
        elif [ "${TRAIN_DONE[$i]}" -eq 1 ]; then
            # Training done but eval not — need to run eval for this one first
            next_train=$i
            break
        else
            next_train=$i
            break
        fi
    done

    while true; do
        # Check if all experiments are complete
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

        # --- Check data generation completion ---
        for i in $(seq 0 $((num_exps - 1))); do
            if [ "${DATA_GEN_PIDS[$i]}" -ne 0 ] && [ "${DATA_READY[$i]}" -eq 0 ]; then
                if ! kill -0 "${DATA_GEN_PIDS[$i]}" 2>/dev/null; then
                    # Process has finished, check if it succeeded
                    wait "${DATA_GEN_PIDS[$i]}" 2>/dev/null
                    local exit_code=$?
                    if [ $exit_code -eq 0 ] && [ -f "${EXP_LOG_DIRS[$i]}/.data_ready" ]; then
                        DATA_READY[$i]=1
                        log_info "✓ Data generation complete for ${EXP_NAMES[$i]}"
                    else
                        log_error "✗ Data generation failed for ${EXP_NAMES[$i]} (exit code: $exit_code)"
                        # Mark as done to skip this experiment
                        DATA_READY[$i]=1
                        TRAIN_DONE[$i]=1
                        EVAL_DONE[$i]=1
                    fi
                fi
            fi
        done

        # --- Try to start training for next_train ---
        if [ "$next_train" -lt "$num_exps" ] && \
           [ "${DATA_READY[$next_train]}" -eq 1 ] && \
           [ "${EVAL_DONE[$next_train]}" -eq 0 ] && \
           [ "$prev_train_done" -eq 1 ]; then

            # Check if this experiment was marked as failed (data gen failed)
            if [ "${DATA_READY[$next_train]}" -eq 1 ] && \
               [ "${EVAL_DONE[$next_train]}" -eq 1 ]; then
                prev_train_done=1
                next_train=$((next_train + 1))
                continue
            fi

            local dataset_path
            dataset_path=$(cat "${EXP_LOG_DIRS[$next_train]}/.data_ready")

            # Start next data generation in background (if any remain)
            if [ "$next_data_gen" -lt "$num_exps" ] && [ "${DATA_READY[$next_data_gen]}" -eq 0 ]; then
                log_info "Starting data generation for experiment $next_data_gen: ${EXP_NAMES[$next_data_gen]} (max_aux=${EXP_MAX_AUX[$next_data_gen]})"
                run_data_generation \
                    "${EXP_NAMES[$next_data_gen]}" \
                    "${EXP_MAX_AUX[$next_data_gen]}" \
                    "${EXP_DATA_DIRS[$next_data_gen]}" \
                    "${EXP_LOG_DIRS[$next_data_gen]}" &
                DATA_GEN_PIDS[$next_data_gen]=$!
                next_data_gen=$((next_data_gen + 1))
            fi

            # Run training if not already done (blocking - GPU exclusive)
            if [ "${TRAIN_DONE[$next_train]}" -eq 0 ]; then
                prev_train_done=0
                run_training "${EXP_NAMES[$next_train]}" "$dataset_path" "${EXP_LOG_DIRS[$next_train]}"
                TRAIN_DONE[$next_train]=1
                prev_train_done=1
            fi

            # Run evaluation if not already done
            if [ "${EVAL_DONE[$next_train]}" -eq 0 ]; then
                run_evaluation "${EXP_NAMES[$next_train]}" "${EXP_LOG_DIRS[$next_train]}"
                EVAL_DONE[$next_train]=1
            fi

            next_train=$((next_train + 1))
        else
            # Nothing to do right now, wait a bit
            sleep 10
        fi
    done

    log_section "All Experiments Completed!"
    
    # Print summary
    echo ""
    echo "┌──────────┬─────────────────────┬──────────────────────────────┬──────────────────────────────┐"
    echo "│ Model    │ max_auxiliary_points │ Data Directory               │ Model Directory              │"
    echo "├──────────┼─────────────────────┼──────────────────────────────┼──────────────────────────────┤"
    for i in $(seq 0 $((num_exps - 1))); do
        printf "│ %-8s │ %-19s │ %-28s │ %-28s │\n" \
            "${EXP_NAMES[$i]}" "${EXP_MAX_AUX[$i]}" "${EXP_DATA_DIRS[$i]}" "models/${EXP_NAMES[$i]}"
    done
    echo "└──────────┴─────────────────────┴──────────────────────────────┴──────────────────────────────┘"
    echo ""
    echo "Logs: $EXP_ROOT/logs/"
    echo ""
}

###############################################
# Main Entry Point
###############################################

# Print experiment overview
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       MAX_AUXILIARY_POINTS Ablation Experiment              ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  sft35: max_auxiliary_points=2                             ║"
echo "║  sft36: max_auxiliary_points=4                             ║"
echo "║  sft37: max_auxiliary_points=6                             ║"
echo "║  sft38: max_auxiliary_points=8                             ║"
echo "║                                                            ║"
echo "║  Data: 200k samples per experiment                         ║"
echo "║  Model: Qwen/Qwen3-0.6B-Base (full fine-tuning)           ║"
echo "║  GPU: 0,1,2 (3 cards)                                     ║"
echo "║  Eval: dev_imo.txt, imo_95_reorder.txt                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

run_async_pipeline
