#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

###############################################
# Configuration
###############################################

export LOGLEVEL="${LOGLEVEL:-WARNING}"

MODEL_NAME="${MODEL_NAME:-sft_simple}"
MODEL_DIR="${MODEL_DIR:-$REPO_ROOT/models/$MODEL_NAME}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/logs/$(date +%m%d_%H%M%S)_${MODEL_NAME}_eval}"

DATASETS="${DATASETS:-benchmarks/dev_imo.txt benchmarks/imo_95.txt}"
EVAL_CONFIGS="${EVAL_CONFIGS:-32:512}"
CHECKPOINTS="${CHECKPOINTS:-latest}"

MAX_WORKERS="${MAX_WORKERS:-40}"
SEARCH_DEPTH="${SEARCH_DEPTH:-4}"
TIMEOUT="${TIMEOUT:-3600}"
AGENT="${AGENT:-lm}"

CUDA_DEVICES="${CUDA_DEVICES:-0,1,2,3}"
RAY_MEMORY_USAGE_THRESHOLD="${RAY_MEMORY_USAGE_THRESHOLD:-0.95}"

REPORT_TO="${REPORT_TO:-}"
SWANLAB_PROJECT="${SWANLAB_PROJECT:-genesisgeo}"
SWANLAB_WORKSPACE="${SWANLAB_WORKSPACE:-}"
SWANLAB_EXP_NAME="${SWANLAB_EXP_NAME:-${MODEL_NAME}_eval}"
SWANLAB_MODE="${SWANLAB_MODE:-cloud}"
SWANLAB_TOKEN="${SWANLAB_TOKEN:-}"
SWANLAB_RUN_ID="${SWANLAB_RUN_ID:-}"
SWANLAB_RESUME="${SWANLAB_RESUME:-allow}"
SWANLAB_LOG_TABLE="${SWANLAB_LOG_TABLE:-true}"

mkdir -p "$LOG_DIR"

REPORT_TO_ENABLED=false
SWANLAB_ENABLED=false
SWANLAB_ACTIVE_RUN_ID="$SWANLAB_RUN_ID"

if [ -n "$REPORT_TO" ]; then
    REPORT_TO_ENABLED=true
    read -r -a REPORT_TO_ITEMS <<< "$(printf '%s' "$REPORT_TO" | tr ',' ' ')"
    for report_target in "${REPORT_TO_ITEMS[@]}"; do
        if [ "$report_target" = "swanlab" ]; then
            SWANLAB_ENABLED=true
            break
        fi
    done
fi

read -r -a DATASET_ITEMS <<< "$(printf '%s' "$DATASETS" | tr ',' ' ')"
read -r -a CONFIG_ITEMS <<< "$(printf '%s' "$EVAL_CONFIGS" | tr ',' ' ')"
read -r -a CHECKPOINT_ITEMS <<< "$(printf '%s' "$CHECKPOINTS" | tr ',' ' ')"

if [ "${#DATASET_ITEMS[@]}" -eq 0 ] || [ -z "${DATASET_ITEMS[0]}" ]; then
    echo "Error: DATASETS is empty." >&2
    exit 1
fi

if [ "${#CONFIG_ITEMS[@]}" -eq 0 ] || [ -z "${CONFIG_ITEMS[0]}" ]; then
    echo "Error: EVAL_CONFIGS is empty." >&2
    exit 1
fi

if [ "${#CHECKPOINT_ITEMS[@]}" -eq 0 ] || [ -z "${CHECKPOINT_ITEMS[0]}" ]; then
    echo "Error: CHECKPOINTS is empty." >&2
    exit 1
fi

require_swanlab() {
    python - <<'PY'
import importlib.util
import sys

sys.exit(0 if importlib.util.find_spec("swanlab") is not None else 1)
PY
}

resolve_model_path() {
    local checkpoint="$1"
    local latest_checkpoint

    if [ "$checkpoint" = "latest" ]; then
        latest_checkpoint="$(find "$MODEL_DIR" -maxdepth 1 -mindepth 1 -type d -name 'checkpoint-*' | sort -V | tail -1)"
        if [ -n "$latest_checkpoint" ]; then
            printf '%s\n' "$latest_checkpoint"
        else
            printf '%s\n' "$MODEL_DIR"
        fi
        return 0
    fi

    if [ "$checkpoint" = "final_model" ]; then
        printf '%s\n' "$MODEL_DIR"
        return 0
    fi

    if [ -d "$checkpoint" ]; then
        printf '%s\n' "$checkpoint"
        return 0
    fi

    if [ -d "$MODEL_DIR/$checkpoint" ]; then
        printf '%s\n' "$MODEL_DIR/$checkpoint"
        return 0
    fi

    echo "Error: checkpoint path not found for '$checkpoint'" >&2
    return 1
}

resolve_dataset_path() {
    local dataset="$1"

    if [ -f "$dataset" ]; then
        printf '%s\n' "$dataset"
        return 0
    fi

    if [ -f "$REPO_ROOT/$dataset" ]; then
        printf '%s\n' "$REPO_ROOT/$dataset"
        return 0
    fi

    if [ -f "$REPO_ROOT/benchmarks/$dataset" ]; then
        printf '%s\n' "$REPO_ROOT/benchmarks/$dataset"
        return 0
    fi

    echo "Error: dataset path not found for '$dataset'" >&2
    return 1
}

dataset_stem_from_arg() {
    local dataset="$1"
    local dataset_name

    dataset_name="$(basename "$dataset")"
    printf '%s\n' "${dataset_name%.txt}"
}

eval_output_stem() {
    local dataset="$1"
    local model_path="$2"
    local decoding_size="$3"
    local beam_size="$4"
    python - "$dataset" "$model_path" "$decoding_size" "$beam_size" "$SEARCH_DEPTH" "$AGENT" <<'PY'
from pathlib import Path
import sys

from scripts.evaluation import build_eval_output_stem, normalize_agent_type

dataset, model_path, decoding_size, beam_size, search_depth, agent = sys.argv[1:]
print(
    build_eval_output_stem(
        agent_type=normalize_agent_type(agent),
        problems_path=Path(dataset),
        model_path=model_path,
        decoding_size=int(decoding_size),
        beam_size=int(beam_size),
        search_depth=int(search_depth),
        gpu_batch_size=1,
        gpu_batch_timeout_ms=0,
        torch_seed=123,
    )
)
PY
}

latest_eval_csv_path() {
    local output_stem="$1"
    python - "$LOG_DIR" "$output_stem" <<'PY'
from pathlib import Path
import sys

log_dir = Path(sys.argv[1])
stem = sys.argv[2]
candidates = sorted(log_dir.glob(f"{stem}_*.csv"))
csv_candidates = [path for path in candidates if not path.name.endswith("_profiling.csv")]
if not csv_candidates:
    raise SystemExit(f"no evaluation csv found for stem {stem}")
print(csv_candidates[-1])
PY
}

init_swanlab_run_if_needed() {
    local output

    if [ "$SWANLAB_ENABLED" != true ]; then
        return 0
    fi

    if ! require_swanlab; then
        echo "Error: REPORT_TO includes swanlab, but the 'swanlab' package is not installed." >&2
        exit 1
    fi

    if [ -n "$SWANLAB_ACTIVE_RUN_ID" ]; then
        return 0
    fi

    output="$(python "$REPO_ROOT/scripts/upload_eval_to_swanlab.py" init-run \
        --project "$SWANLAB_PROJECT" \
        --workspace "$SWANLAB_WORKSPACE" \
        --experiment_name "$SWANLAB_EXP_NAME" \
        --mode "$SWANLAB_MODE" \
        --token "$SWANLAB_TOKEN" \
        --model_name "$MODEL_NAME" \
        --model_dir "$MODEL_DIR" \
        --datasets "$DATASETS" \
        --checkpoints "$CHECKPOINTS" \
        --eval_configs "$EVAL_CONFIGS" \
        --agent "$AGENT" \
        --max_workers "$MAX_WORKERS" \
        --search_depth "$SEARCH_DEPTH" \
        --timeout "$TIMEOUT")"

    SWANLAB_ACTIVE_RUN_ID="$(printf '%s\n' "$output" | awk -F= '/^RUN_ID=/{print $2}' | tail -1)"

    if [ -z "$SWANLAB_ACTIVE_RUN_ID" ]; then
        echo "Error: failed to initialize a SwanLab run for evaluation uploads." >&2
        printf '%s\n' "$output" >&2
        exit 1
    fi
}

upload_eval_to_swanlab() {
    local csv_path="$1"
    local dataset="$2"
    local checkpoint_label="$3"
    local model_path="$4"
    local decoding_size="$5"
    local beam_size="$6"

    if [ "$SWANLAB_ENABLED" != true ]; then
        return 0
    fi

    if [ ! -f "$csv_path" ]; then
        echo "Warning: evaluation CSV not found, skipping SwanLab upload: $csv_path" >&2
        return 0
    fi

    python "$REPO_ROOT/scripts/upload_eval_to_swanlab.py" upload \
        --project "$SWANLAB_PROJECT" \
        --workspace "$SWANLAB_WORKSPACE" \
        --experiment_name "$SWANLAB_EXP_NAME" \
        --mode "$SWANLAB_MODE" \
        --token "$SWANLAB_TOKEN" \
        --csv_path "$csv_path" \
        --run_id "$SWANLAB_ACTIVE_RUN_ID" \
        --resume "$SWANLAB_RESUME" \
        --dataset_name "$dataset" \
        --checkpoint_label "$checkpoint_label" \
        --model_name "$MODEL_NAME" \
        --model_path "$model_path" \
        --agent "$AGENT" \
        --decoding_size "$decoding_size" \
        --beam_size "$beam_size" \
        --search_depth "$SEARCH_DEPTH" \
        --timeout "$TIMEOUT" \
        --max_workers "$MAX_WORKERS" \
        --log_table="$SWANLAB_LOG_TABLE"
}

init_swanlab_run_if_needed

echo "=========================================="
echo "Evaluation"
echo "=========================================="
echo "Model Name : $MODEL_NAME"
echo "Model Dir  : $MODEL_DIR"
echo "Log Dir    : $LOG_DIR"
echo "CUDA       : $CUDA_DEVICES"
echo "Datasets   : $DATASETS"
echo "Configs    : $EVAL_CONFIGS"
echo "Checkpoints: $CHECKPOINTS"
echo "Workers    : $MAX_WORKERS"
echo "Agent      : $AGENT"
if [ "$REPORT_TO_ENABLED" = true ]; then
    echo "Report To  : $REPORT_TO"
fi
if [ "$SWANLAB_ENABLED" = true ]; then
    echo "SwanLab    : project=$SWANLAB_PROJECT exp=$SWANLAB_EXP_NAME mode=$SWANLAB_MODE run_id=${SWANLAB_ACTIVE_RUN_ID:-<new>}"
fi
echo "=========================================="

total_commands=$((${#CHECKPOINT_ITEMS[@]} * ${#DATASET_ITEMS[@]} * ${#CONFIG_ITEMS[@]}))
echo "Total commands to execute: $total_commands"
echo ""

for checkpoint in "${CHECKPOINT_ITEMS[@]}"; do
    model_path="$(resolve_model_path "$checkpoint")"
    checkpoint_label="$(basename "$model_path")"

    echo "Processing checkpoint: $checkpoint_label"
    echo "Model path: $model_path"
    echo "=========================================="

    for dataset in "${DATASET_ITEMS[@]}"; do
        for config in "${CONFIG_ITEMS[@]}"; do
            IFS=':' read -r decoding_size beam_size <<< "$config"
            if [ -z "${decoding_size:-}" ] || [ -z "${beam_size:-}" ]; then
                echo "Error: invalid config '$config'. Use the format decoding_size:beam_size." >&2
                exit 1
            fi

            dataset_path="$(resolve_dataset_path "$dataset")"
            dataset_name="$(basename "$dataset_path")"
            output_stem="$(eval_output_stem "$dataset_path" "$model_path" "$decoding_size" "$beam_size")"
            eval_log="$LOG_DIR/${output_stem}.log"

            EVAL_ARGS=(
                --problems_path "$dataset_path"
                --model_path "$model_path"
                --log_dir "$LOG_DIR"
                --max_workers "$MAX_WORKERS"
                --decoding_size "$decoding_size"
                --beam_size "$beam_size"
                --search_depth "$SEARCH_DEPTH"
                --timeout "$TIMEOUT"
                --agent "$AGENT"
            )

            echo "Dataset    : $dataset_name"
            echo "DatasetPath: $dataset_path"
            echo "Config     : decoding_size=$decoding_size beam_size=$beam_size search_depth=$SEARCH_DEPTH"
            echo "CSV Stem   : $output_stem"
            echo "Eval Log   : $eval_log"
            echo "------------------------------------------"

            set +e
            CUDA_VISIBLE_DEVICES="$CUDA_DEVICES" \
            RAY_memory_usage_threshold="$RAY_MEMORY_USAGE_THRESHOLD" \
            python "$REPO_ROOT/scripts/evaluation.py" \
                "${EVAL_ARGS[@]}" \
                2>&1 | tee "$eval_log"
            status=${PIPESTATUS[0]}
            set -e

            if [ "$status" -eq 0 ]; then
                csv_path="$(latest_eval_csv_path "$output_stem")"
                echo "Evaluation completed successfully"
                echo "CSV Output : $csv_path"
                upload_eval_to_swanlab \
                    "$csv_path" \
                    "$dataset_name" \
                    "$checkpoint_label" \
                    "$model_path" \
                    "$decoding_size" \
                    "$beam_size"
            else
                echo "Evaluation failed with exit code $status" >&2
            fi

            echo "=========================================="
        done
    done
done

echo ""
echo "All evaluation tasks completed."
echo "Logs: $LOG_DIR"
