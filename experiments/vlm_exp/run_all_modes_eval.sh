#!/bin/bash
set -euo pipefail

# 1. 动态获取脚本所在目录和项目根目录 (和你原脚本保持一致)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

# 2. 评估脚本就在当前包裹脚本的同级目录下
EVAL_SCRIPT="$SCRIPT_DIR/run_qwen3vl_eval.sh"

# 状态记录文件，存放在项目根目录
STATE_FILE="$REPO_ROOT/.eval_completed_modes.log"

# 需要遍历的图像模式
MODES=("full" "white" "masked_quadrant" "downsample_upsample")

if [ ! -f "$EVAL_SCRIPT" ]; then
    echo "Error: 找不到评估脚本 $EVAL_SCRIPT"
    exit 1
fi

touch "$STATE_FILE"

echo "=========================================="
echo "开始多模式评估任务"
echo "状态记录文件: $STATE_FILE"
echo "=========================================="

for mode in "${MODES[@]}"; do
    if grep -Fxq "$mode" "$STATE_FILE"; then
        echo "⏭️  检测到 $mode 模式已完成，跳过..."
        continue
    fi

    echo "▶️  开始运行评估，当前图像模式: $mode"
    
    # 导出环境变量供原脚本使用
    export EVAL_IMAGE_MODE="$mode"
    
    # 调用原脚本。外部传入的 MODEL_PATH 等环境变量会自动传递进去
    bash "$EVAL_SCRIPT"
    
    # 执行成功后记录状态
    echo "$mode" >> "$STATE_FILE"
    echo "✅  $mode 模式评估完成并已记录。"
    echo "------------------------------------------"
done

echo "🎉 所有图像模式评估已全部完成！"
