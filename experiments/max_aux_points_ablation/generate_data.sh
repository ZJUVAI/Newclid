#!/bin/bash
###############################################################################
# MAX_AUXILIARY_POINTS Ablation - Data Generation Only
#
# 专门用于生成实验数据的脚本，不包含训练和评估
#
# 实验组配置：
#   sft35: max_auxiliary_points=2
#   sft36: max_auxiliary_points=4
#   sft37: max_auxiliary_points=6
#   sft38: max_auxiliary_points=8
#
# 用法：
#   bash experiments/max_aux_points_ablation/generate_data.sh          # 自动跳过已完成的数据生成
#   bash experiments/max_aux_points_ablation/generate_data.sh --force  # 强制重新生成所有数据
#
# 查看进度：
#   # 查看所有实验的数据生成状态
#   ls -lh experiments/max_aux_points_ablation/logs/*/.data_ready
#
#   # 查看数据生成日志（实时）
#   tail -f experiments/max_aux_points_ablation/logs/sft35_maxaux2/data_generation.log
#
#   # 查看生成进度（查找 Generated 关键字）
#   grep -E "Generated|Progress|samples" experiments/max_aux_points_ablation/logs/sft35_maxaux2/data_generation.log | tail -20
#
#   # 查看已生成的数据文件大小
#   ls -lh experiments/max_aux_points_ablation/data/*/geometry_*.jsonl
#
#   # 检查数据生成进程是否在运行
#   ps aux | grep "pipeline.py" | grep -v grep
#
#   # 查看 CPU 使用情况
#   top -bn1 | grep "Cpu(s)"
#
# 注意事项：
#   - 脚本支持断点续跑：通过 .data_ready 标记文件自动检测已完成的数据生成
#   - 使用 --force 可清除所有标记，强制全部重新生成
#   - 确保有足够的磁盘空间（每组 200k 数据约占 1-3 GB）
#   - 数据生成使用 32 个 CPU 线程
#   - 所有数据生成任务串行执行（避免 CPU 资源竞争）
###############################################################################

set -e  # Exit on error

# Parse command line arguments
FORCE=false
for arg in "$@"; do
    case $arg in
        --force)
            FORCE=true
            echo "[WARN] Force mode: all data will be regenerated"
            ;;
        --help|-h)
            echo "Usage: bash $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --force   Force regenerate all data (ignore completed markers)"
            echo "  --help    Show this help message"
            echo ""
            echo "By default, the script automatically detects and skips completed data generation."
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
save_data_config() {
    local exp_dir="$1"
    local model_name="$2"
    local max_aux_points="$3"
    local data_dir="$4"

    cat > "$exp_dir/data_generation_config.json" << EOF
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
    "data_directory": "$data_dir"
}
EOF
}

###############################################
# Data Generation Function
###############################################

# Data Generation (CPU only)
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

    # Write dataset path to a flag file
    echo "$dataset_path" > "$log_dir/.data_ready"
}

###############################################
# Main Pipeline
###############################################

run_sequential_data_generation() {
    log_section "Starting Sequential Data Generation"
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
    declare -a DATA_READY          # 1 if data generation is complete

    # Initialize experiment metadata
    for i in $(seq 0 $((num_exps - 1))); do
        read -r name max_aux <<< "${EXPERIMENTS[$i]}"
        EXP_NAMES[$i]="$name"
        EXP_MAX_AUX[$i]="$max_aux"
        EXP_DATA_DIRS[$i]="$EXP_ROOT/data/${name}_maxaux${max_aux}"
        EXP_LOG_DIRS[$i]="$EXP_ROOT/logs/${name}_maxaux${max_aux}"
        DATA_GEN_PIDS[$i]=0
        DATA_READY[$i]=0

        mkdir -p "${EXP_LOG_DIRS[$i]}"
        mkdir -p "${EXP_DATA_DIRS[$i]}"

        # Detect completed data generation from previous runs (skip if --force)
        if [ "$FORCE" = false ]; then
            if [ -f "${EXP_LOG_DIRS[$i]}/.data_ready" ]; then
                DATA_READY[$i]=1
                log_info "[SKIP] ${name}: data generation already completed"
            fi
        else
            # Force mode: remove old markers
            rm -f "${EXP_LOG_DIRS[$i]}/.data_ready"
        fi

        # Save config
        save_data_config \
            "${EXP_LOG_DIRS[$i]}" \
            "$name" \
            "$max_aux" \
            "${EXP_DATA_DIRS[$i]}"
    done

    # Run data generation tasks sequentially (串行执行)
    for i in $(seq 0 $((num_exps - 1))); do
        if [ "${DATA_READY[$i]}" -eq 0 ]; then
            log_info "Starting data generation for ${EXP_NAMES[$i]} (max_aux=${EXP_MAX_AUX[$i]})"

            if run_data_generation \
                "${EXP_NAMES[$i]}" \
                "${EXP_MAX_AUX[$i]}" \
                "${EXP_DATA_DIRS[$i]}" \
                "${EXP_LOG_DIRS[$i]}"; then
                DATA_READY[$i]=1
                log_info "✓ Data generation complete for ${EXP_NAMES[$i]}"
            else
                log_error "✗ Data generation failed for ${EXP_NAMES[$i]}"
                DATA_READY[$i]=-1  # Mark as failed
            fi
        fi
    done

    log_section "All Data Generation Completed!"

    # Print summary
    echo ""
    echo "┌──────────┬─────────────────────┬──────────────────────────────┬──────────┐"
    echo "│ Model    │ max_auxiliary_points │ Data Directory               │ Status   │"
    echo "├──────────┼─────────────────────┼──────────────────────────────┼──────────┤"
    for i in $(seq 0 $((num_exps - 1))); do
        local status="✓ Done"
        if [ "${DATA_READY[$i]}" -eq -1 ]; then
            status="✗ Failed"
        elif [ "${DATA_READY[$i]}" -eq 1 ]; then
            status="✓ Done"
        fi
        printf "│ %-8s │ %-19s │ %-28s │ %-8s │\n" \
            "${EXP_NAMES[$i]}" "${EXP_MAX_AUX[$i]}" "${EXP_DATA_DIRS[$i]}" "$status"
    done
    echo "└──────────┴─────────────────────┴──────────────────────────────┴──────────┘"
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
echo "║       MAX_AUXILIARY_POINTS Ablation - Data Generation      ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  sft35: max_auxiliary_points=2                             ║"
echo "║  sft36: max_auxiliary_points=4                             ║"
echo "║  sft37: max_auxiliary_points=6                             ║"
echo "║  sft38: max_auxiliary_points=8                             ║"
echo "║                                                            ║"
echo "║  Data: 200k samples per experiment                         ║"
echo "║  Threads: 32 CPU threads per task                          ║"
echo "║  Mode: Sequential execution (one task at a time)          ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

run_sequential_data_generation
