#!/bin/bash
# Discovery Pipeline 一键运行脚本
# 支持完整pipeline或分阶段运行，可配置所有超参数

set -e  # 遇到错误立即退出

# ============================================================================
# 默认配置（100k数据标准参数）
# ============================================================================

# 环境配置
CONDA_ENV="Discovery"
CONDA_PATH="/C20545/home/duzhengtong/miniconda3"
PROJECT_ROOT="/C20545/home/duzhengtong/GeoDiscovery"

# Stage 0: 数据生成（默认跳过，使用现有数据）
GENERATE_DATA=false
N_CLAUSES=10
N_SAMPLES=100000
N_THREADS=30
AUX_ONLY=1
TIMEOUT_GENERATE=3600
DATA_DIR="${PROJECT_ROOT}/datasets"

# Stage 1: 规则提取
RUN_EXTRACTION=true
SKIP_PREDICATES="eqpoint,constline"
RULE_SKIP_PREDICATES="aconst,rconst"
MAX_WORKERS=30
SAVE_INTERMEDIATES=true
RENDER_IMAGES=false

# Stage 2: 规则规约
RUN_REDUCTION=true
TIMEOUT_REDUCTION=60
SEED=42
MAX_PREMISES=7
BATCH_SIZE=10
DEBUG=false
NO_GROUP_REDUCTION=false

# Stage 3: 规则评估
RUN_EVALUATION=true
BENCHMARKS="jgex_ag_231,hageo_409,imo_95"
TIMEOUT_EVAL=600
EVAL_WORKERS=30
SKIP_BASELINE_SOLVED=true

# Stage 4: 可视化
RUN_VISUALIZATION=false

# 输出目录
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="${PROJECT_ROOT}/outputs/experiments/${TIMESTAMP}_full_pipeline"

# ============================================================================
# 帮助信息
# ============================================================================

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Discovery Pipeline 一键运行脚本

OPTIONS:
    -h, --help              显示帮助信息

    # 阶段控制
    --generate-data         启用数据生成（默认跳过，使用现有数据）
    --skip-extraction       跳过规则提取
    --skip-reduction        跳过规则规约
    --skip-evaluation       跳过规则评估
    --skip-visualization    跳过可视化

    # Stage 0: 数据生成
    --n-clauses N           构造子句数 (默认: 10)
    --n-samples N           样本数量 (默认: 100000)
    --n-threads N           并行线程数 (默认: 30)
    --aux-only {0|1}        是否只保留含辅助点的题目 (默认: 1)
    --data-dir PATH         数据目录（指定后自动跳过数据生成）

    # Stage 1: 规则提取
    --skip-predicates LIST  输入过滤谓词 (默认: eqpoint,constline)
    --rule-skip-predicates LIST  规则过滤谓词 (默认: aconst,rconst)
    --max-workers N         并行worker数 (默认: 30)
    --no-save-intermediates 不保存中间结果
    --render-images         渲染对比图

    # Stage 2: 规则规约
    --timeout-reduction N   Subsumption测试超时 (默认: 60)
    --seed N                随机种子 (默认: 42)
    --max-premises N        最大前提数过滤 (默认: 7)
    --batch-size N          批处理大小 (默认: 10)
    --debug                 启用调试输出
    --no-group-reduction    禁用小组规约

    # Stage 3: 规则评估
    --benchmarks LIST       Benchmark列表 (默认: jgex_ag_231,hageo_409,imo_95)
    --timeout-eval N        评估超时 (默认: 600)
    --eval-workers N        评估并行数 (默认: 30)
    --no-skip-baseline-solved  不跳过baseline已解决的题目

    # 输出控制
    --output-dir PATH       输出目录 (默认: outputs/experiments/TIMESTAMP_full_pipeline)

EXAMPLES:
    # 默认运行（使用现有100k数据，Stage 1-3）
    $0

    # 完整pipeline（包含数据生成）
    $0 --generate-data

    # 仅提取+规约（跳过评估）
    $0 --skip-evaluation

    # 仅评估（使用已有规则）
    $0 --skip-extraction --skip-reduction --rules <path/to/extracted_rules.txt>

    # 快速测试（1k数据）
    $0 --generate-data --n-samples 1000 --n-threads 10 --max-workers 10
EOF
}

# ============================================================================
# 参数解析
# ============================================================================

RULES_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --generate-data)
            GENERATE_DATA=true
            shift
            ;;
        --skip-extraction)
            RUN_EXTRACTION=false
            shift
            ;;
        --skip-reduction)
            RUN_REDUCTION=false
            shift
            ;;
        --skip-evaluation)
            RUN_EVALUATION=false
            shift
            ;;
        --skip-visualization)
            RUN_VISUALIZATION=false
            shift
            ;;
        --n-clauses)
            N_CLAUSES="$2"
            shift 2
            ;;
        --n-samples)
            N_SAMPLES="$2"
            shift 2
            ;;
        --n-threads)
            N_THREADS="$2"
            shift 2
            ;;
        --aux-only)
            AUX_ONLY="$2"
            shift 2
            ;;
        --data-dir)
            DATA_DIR="$2"
            GENERATE_DATA=false
            shift 2
            ;;
        --skip-predicates)
            SKIP_PREDICATES="$2"
            shift 2
            ;;
        --rule-skip-predicates)
            RULE_SKIP_PREDICATES="$2"
            shift 2
            ;;
        --max-workers)
            MAX_WORKERS="$2"
            shift 2
            ;;
        --no-save-intermediates)
            SAVE_INTERMEDIATES=false
            shift
            ;;
        --render-images)
            RENDER_IMAGES=true
            shift
            ;;
        --timeout-reduction)
            TIMEOUT_REDUCTION="$2"
            shift 2
            ;;
        --seed)
            SEED="$2"
            shift 2
            ;;
        --max-premises)
            MAX_PREMISES="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --debug)
            DEBUG=true
            shift
            ;;
        --no-group-reduction)
            NO_GROUP_REDUCTION=true
            shift
            ;;
        --benchmarks)
            BENCHMARKS="$2"
            shift 2
            ;;
        --timeout-eval)
            TIMEOUT_EVAL="$2"
            shift 2
            ;;
        --eval-workers)
            EVAL_WORKERS="$2"
            shift 2
            ;;
        --no-skip-baseline-solved)
            SKIP_BASELINE_SOLVED=false
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --rules)
            RULES_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# ============================================================================
# 环境检查
# ============================================================================

echo "=========================================="
echo "Discovery Pipeline 一键运行脚本"
echo "=========================================="
echo ""

# 激活conda环境
echo "[环境] 激活 conda 环境: $CONDA_ENV"
source "${CONDA_PATH}/bin/activate" "$CONDA_ENV"

# 验证Python环境
PYTHON_VERSION=$(python --version 2>&1)
echo "[环境] Python 版本: $PYTHON_VERSION"

# 验证项目根目录
if [ ! -d "$PROJECT_ROOT" ]; then
    echo "[错误] 项目根目录不存在: $PROJECT_ROOT"
    exit 1
fi
cd "$PROJECT_ROOT"

# 创建输出目录
mkdir -p "$OUTPUT_DIR"
echo "[输出] 输出目录: $OUTPUT_DIR"

# 保存配置
CONFIG_FILE="${OUTPUT_DIR}/pipeline_config.json"
cat > "$CONFIG_FILE" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "stages": {
    "generation": $GENERATE_DATA,
    "extraction": $RUN_EXTRACTION,
    "reduction": $RUN_REDUCTION,
    "evaluation": $RUN_EVALUATION,
    "visualization": $RUN_VISUALIZATION
  },
  "parameters": {
    "n_clauses": $N_CLAUSES,
    "n_samples": $N_SAMPLES,
    "n_threads": $N_THREADS,
    "aux_only": $AUX_ONLY,
    "max_workers": $MAX_WORKERS,
    "timeout_reduction": $TIMEOUT_REDUCTION,
    "timeout_eval": $TIMEOUT_EVAL,
    "max_premises": $MAX_PREMISES
  },
  "paths": {
    "data_dir": "$DATA_DIR",
    "output_dir": "$OUTPUT_DIR"
  }
}
EOF
echo "[配置] 配置已保存: $CONFIG_FILE"
echo ""
# ============================================================================
# Stage 0: 数据生成
# ============================================================================

if [ "$GENERATE_DATA" = true ]; then
    echo "=========================================="
    echo "Stage 0: 数据生成"
    echo "=========================================="
    echo "[参数] n_clauses=$N_CLAUSES, n_samples=$N_SAMPLES, n_threads=$N_THREADS"

    python src/newclid/generation/generate.py \
        --n_clauses="$N_CLAUSES" \
        --n_threads="$N_THREADS" \
        --n_samples="$N_SAMPLES" \
        --aux_only="$AUX_ONLY" \
        --log_level=info \
        --timeout="$TIMEOUT_GENERATE" \
        --dir="$DATA_DIR"

    echo "[完成] 数据生成完成: $DATA_DIR"
    echo ""
fi

# 验证数据文件
# 支持两种路径格式：
# 1. datasets/geometry_clauses10_samples100k.jsonl (100k缩写)
# 2. datasets/geometry_clauses10_samples100000/geometry_clauses10_samples100000.jsonl (完整数字+子目录)
if [ "$N_SAMPLES" -ge 1000 ]; then
    # 尝试使用k缩写格式
    N_SAMPLES_K=$((N_SAMPLES / 1000))
    DATA_FILE="${DATA_DIR}/geometry_clauses${N_CLAUSES}_samples${N_SAMPLES_K}k.jsonl"
    if [ ! -f "$DATA_FILE" ]; then
        # 回退到完整数字格式（带子目录）
        DATA_FILE="${DATA_DIR}/geometry_clauses${N_CLAUSES}_samples${N_SAMPLES}/geometry_clauses${N_CLAUSES}_samples${N_SAMPLES}.jsonl"
    fi
else
    # 小于1000的样本数，使用完整数字
    DATA_FILE="${DATA_DIR}/geometry_clauses${N_CLAUSES}_samples${N_SAMPLES}.jsonl"
fi

if [ ! -f "$DATA_FILE" ]; then
    echo "[错误] 数据文件不存在: $DATA_FILE"
    echo "[提示] 请检查数据文件路径，或使用 --generate-data 生成新数据"
    exit 1
fi

# ============================================================================
# Stage 1: 规则提取
# ============================================================================

EXTRACTED_RULES_FILE=""
SOURCE_DATA_FILE=""

if [ "$RUN_EXTRACTION" = true ]; then
    echo "=========================================="
    echo "Stage 1: 规则提取"
    echo "=========================================="

    EXTRACTION_ARGS=(
        --input "$DATA_FILE"
        --output "$OUTPUT_DIR"
        --max-workers "$MAX_WORKERS"
        --skip-predicates "$SKIP_PREDICATES"
        --rule-skip-predicates "$RULE_SKIP_PREDICATES"
    )

    if [ "$SAVE_INTERMEDIATES" = true ]; then
        EXTRACTION_ARGS+=(--save-intermediates)
    fi

    if [ "$RENDER_IMAGES" = true ]; then
        EXTRACTION_ARGS+=(--render-images)
    fi

    if [ "$RUN_REDUCTION" = false ]; then
        EXTRACTION_ARGS+=(--skip-reduction)
    fi

    python scripts/discovery_pipeline.py "${EXTRACTION_ARGS[@]}"

    # 自动检测输出文件
    EXTRACTED_RULES_FILE=$(find "$OUTPUT_DIR" -name "*_pruned_rules.txt" | head -1)
    SOURCE_DATA_FILE="${OUTPUT_DIR}/intermediates/step6_rules_stats.json"

    echo "[完成] 规则提取完成"
    echo "[输出] 规则文件: $EXTRACTED_RULES_FILE"
    echo ""
fi

# ============================================================================
# Stage 2: 规则规约
# ============================================================================

FINAL_RULES_FILE=""

if [ "$RUN_REDUCTION" = true ]; then
    echo "=========================================="
    echo "Stage 2: 规则规约"
    echo "=========================================="

    # 如果用户提供了规则文件，使用用户提供的
    if [ -n "$RULES_FILE" ]; then
        EXTRACTED_RULES_FILE="$RULES_FILE"
    fi

    if [ -z "$EXTRACTED_RULES_FILE" ] || [ ! -f "$EXTRACTED_RULES_FILE" ]; then
        echo "[错误] 缺少规则文件: $EXTRACTED_RULES_FILE"
        exit 1
    fi

    if [ -z "$SOURCE_DATA_FILE" ] || [ ! -f "$SOURCE_DATA_FILE" ]; then
        echo "[错误] 缺少源数据文件: $SOURCE_DATA_FILE"
        exit 1
    fi

    REDUCTION_ARGS=(
        --output "$OUTPUT_DIR"
        --skip-extraction
        --rules "$EXTRACTED_RULES_FILE"
        --source-data "$SOURCE_DATA_FILE"
        --timeout "$TIMEOUT_REDUCTION"
        --seed "$SEED"
        --max-premises "$MAX_PREMISES"
        --max-workers "$MAX_WORKERS"
        --batch-size "$BATCH_SIZE"
    )

    if [ "$DEBUG" = true ]; then
        REDUCTION_ARGS+=(--debug)
    fi

    if [ "$NO_GROUP_REDUCTION" = true ]; then
        REDUCTION_ARGS+=(--no-group-reduction)
    fi

    python scripts/discovery_pipeline.py "${REDUCTION_ARGS[@]}"

    FINAL_RULES_FILE="${OUTPUT_DIR}/extracted_rules_maxprem${MAX_PREMISES}.txt"

    echo "[完成] 规则规约完成"
    echo "[输出] 最终规则: $FINAL_RULES_FILE"
    echo ""
fi

# ============================================================================
# Stage 3: 规则评估
# ============================================================================

if [ "$RUN_EVALUATION" = true ]; then
    echo "=========================================="
    echo "Stage 3: 规则评估"
    echo "=========================================="

    # 如果用户提供了规则文件，使用用户提供的
    if [ -n "$RULES_FILE" ]; then
        FINAL_RULES_FILE="$RULES_FILE"
    fi

    if [ -z "$FINAL_RULES_FILE" ] || [ ! -f "$FINAL_RULES_FILE" ]; then
        echo "[错误] 缺少最终规则文件: $FINAL_RULES_FILE"
        exit 1
    fi

    EVAL_ARGS=(
        evaluate
        --rules "$FINAL_RULES_FILE"
        --baseline-cache "${PROJECT_ROOT}/outputs/eval_baselines/"
        --output "${OUTPUT_DIR}/eval"
        --benchmarks "$BENCHMARKS"
        --workers "$EVAL_WORKERS"
        --timeout "$TIMEOUT_EVAL"
    )

    if [ "$SKIP_BASELINE_SOLVED" = false ]; then
        EVAL_ARGS+=(--no-skip-baseline-solved)
    fi

    python scripts/evaluate_rules.py "${EVAL_ARGS[@]}"

    echo "[完成] 规则评估完成"
    echo "[输出] 评估结果: ${OUTPUT_DIR}/eval/"
    echo ""
fi

# ============================================================================
# Stage 4: 可视化
# ============================================================================

if [ "$RUN_VISUALIZATION" = true ]; then
    echo "=========================================="
    echo "Stage 4: 可视化"
    echo "=========================================="

    # Pipeline flow图
    python scripts/figures/fig_pipeline_flow.py

    # Rule extraction图（如果有实验数据）
    if [ -d "${OUTPUT_DIR}/intermediates" ]; then
        python scripts/figures/fig_rule_extraction.py \
            --experiment "$OUTPUT_DIR" \
            --num-samples 5 || true
    fi

    echo "[完成] 可视化完成"
    echo "[输出] 图片目录: outputs/figures/discovery/"
    echo ""
fi

# ============================================================================
# 总结报告
# ============================================================================

echo "=========================================="
echo "Pipeline 运行完成"
echo "=========================================="
echo ""
echo "输出目录: $OUTPUT_DIR"
echo ""
echo "生成的文件:"
if [ "$RUN_EXTRACTION" = true ] && [ -n "$EXTRACTED_RULES_FILE" ]; then
    echo "  - 提取规则: $EXTRACTED_RULES_FILE"
fi
if [ "$RUN_REDUCTION" = true ] && [ -n "$FINAL_RULES_FILE" ]; then
    echo "  - 最终规则: $FINAL_RULES_FILE"
fi
if [ "$RUN_EVALUATION" = true ]; then
    echo "  - 评估结果: ${OUTPUT_DIR}/eval/"
fi
if [ "$SAVE_INTERMEDIATES" = true ]; then
    echo "  - 中间结果: ${OUTPUT_DIR}/intermediates/"
fi
echo "  - 配置文件: $CONFIG_FILE"
echo ""

# 生成总结报告
SUMMARY_FILE="${OUTPUT_DIR}/pipeline_summary.md"
cat > "$SUMMARY_FILE" << SUMMARY_EOF
# Pipeline 运行总结

**运行时间**: $(date -Iseconds)
**输出目录**: $OUTPUT_DIR

## 配置

- 数据集: $DATA_FILE
- 样本数: $N_SAMPLES
- n_clauses: $N_CLAUSES
- 并行度: $MAX_WORKERS

## 运行阶段

- Stage 0 (数据生成): $([ "$GENERATE_DATA" = true ] && echo "✓" || echo "✗")
- Stage 1 (规则提取): $([ "$RUN_EXTRACTION" = true ] && echo "✓" || echo "✗")
- Stage 2 (规则规约): $([ "$RUN_REDUCTION" = true ] && echo "✓" || echo "✗")
- Stage 3 (规则评估): $([ "$RUN_EVALUATION" = true ] && echo "✓" || echo "✗")
- Stage 4 (可视化): $([ "$RUN_VISUALIZATION" = true ] && echo "✓" || echo "✗")

## 输出文件

$([ -n "$EXTRACTED_RULES_FILE" ] && echo "- 提取规则: \`$EXTRACTED_RULES_FILE\`")
$([ -n "$FINAL_RULES_FILE" ] && echo "- 最终规则: \`$FINAL_RULES_FILE\`")
$([ "$RUN_EVALUATION" = true ] && echo "- 评估结果: \`${OUTPUT_DIR}/eval/\`")
$([ "$SAVE_INTERMEDIATES" = true ] && echo "- 中间结果: \`${OUTPUT_DIR}/intermediates/\`")

## 下一步

- 查看规则: \`head -20 $FINAL_RULES_FILE\`
- 查看评估: \`cat ${OUTPUT_DIR}/eval/*_comparison.json | jq\`
- 查看中间结果: \`ls ${OUTPUT_DIR}/intermediates/\`

SUMMARY_EOF

echo "总结报告已保存: $SUMMARY_FILE"
echo ""
echo "查看总结: cat $SUMMARY_FILE"
echo ""
