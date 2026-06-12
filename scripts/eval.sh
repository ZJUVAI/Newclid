#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export LOGLEVEL="${LOGLEVEL:-WARNING}"

VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000}"
AGENT="${AGENT:-qwen3_text}"
LOG_DIR="${LOG_DIR:-$REPO_ROOT/results}"
DATASETS="${DATASETS:-benchmarks/dev_imo.txt}"
EVAL_CONFIGS="${EVAL_CONFIGS:-32:512}"
SEARCH_DEPTH="${SEARCH_DEPTH:-4}"
SEARCH_VERSION="${SEARCH_VERSION:-hybrid}"
TIMEOUT="${TIMEOUT:-7200}"
RAY_NUM_CPUS="${RAY_NUM_CPUS:-40}"
ENABLE_TRACE="${ENABLE_TRACE:-false}"

BASELINE_CSV="${BASELINE_CSV:-$REPO_ROOT/results/eval_vllm_dev_imo_checkpoint-7049_svhybrid_d32_b512_s4_7823e3f.csv}"
MIN_SOLVED="${MIN_SOLVED:-13}"
MAX_TOTAL_TIME_S="${MAX_TOTAL_TIME_S:-400}"

mkdir -p "$LOG_DIR"

read -r -a DATASET_ITEMS <<< "$(printf '%s' "$DATASETS" | tr ',' ' ')"
read -r -a CONFIG_ITEMS <<< "$(printf '%s' "$EVAL_CONFIGS" | tr ',' ' ')"

if [ "${#DATASET_ITEMS[@]}" -eq 0 ] || [ -z "${DATASET_ITEMS[0]}" ]; then
    echo "Error: DATASETS is empty." >&2
    exit 1
fi

if [ "${#CONFIG_ITEMS[@]}" -eq 0 ] || [ -z "${CONFIG_ITEMS[0]}" ]; then
    echo "Error: EVAL_CONFIGS is empty." >&2
    exit 1
fi

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

append_boolean_optional_arg() {
    local -n target_args_ref="$1"
    local flag_name="$2"
    local raw_value="$3"
    local normalized_value

    normalized_value="$(printf '%s' "$raw_value" | tr '[:upper:]' '[:lower:]')"
    case "$normalized_value" in
        1|true|yes|on)
            target_args_ref+=("--$flag_name")
            ;;
        0|false|no|off|'')
            target_args_ref+=("--no-$flag_name")
            ;;
        *)
            echo "Error: invalid boolean value '$raw_value' for $flag_name" >&2
            exit 1
            ;;
    esac
}

latest_eval_csv_path() {
    local dataset_path="$1"
    local decoding_size="$2"
    local beam_size="$3"
    python - "$LOG_DIR" "$dataset_path" "$AGENT" "$SEARCH_VERSION" "$decoding_size" "$beam_size" "$SEARCH_DEPTH" <<'PY'
from pathlib import Path
import sys

log_dir = Path(sys.argv[1])
dataset_path = Path(sys.argv[2])
agent = sys.argv[3]
search_version = sys.argv[4]
decoding_size = sys.argv[5]
beam_size = sys.argv[6]
search_depth = sys.argv[7]
pattern = (
    f"eval_vllm_{agent}_{dataset_path.stem}_*_sv{search_version}"
    f"_d{decoding_size}_b{beam_size}_s{search_depth}_*.csv"
)
candidates = sorted(log_dir.glob(pattern))
if not candidates:
    raise SystemExit(f"no evaluation csv found for pattern {pattern}")
print(candidates[-1])
PY
}

compare_eval_csv() {
    local csv_path="$1"
    python - "$csv_path" "$BASELINE_CSV" "$MIN_SOLVED" "$MAX_TOTAL_TIME_S" <<'PY'
import csv
import re
import sys
from pathlib import Path

csv_path = Path(sys.argv[1])
baseline_path = Path(sys.argv[2])
min_solved = int(sys.argv[3])
max_total_time_s = float(sys.argv[4])

def parse_header(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))[0]
    match = re.search(r"Solved: (\d+)/(\d+), Total Time: ([0-9.]+)s", header)
    if match is None:
        raise SystemExit(f"failed to parse summary header from {path}: {header}")
    solved = int(match.group(1))
    total = int(match.group(2))
    total_time = float(match.group(3))
    return solved, total, total_time

solved, total, total_time = parse_header(csv_path)
print(f"[summary] csv={csv_path} solved={solved}/{total} total_time_s={total_time:.2f}")

if baseline_path.exists():
    base_solved, base_total, base_total_time = parse_header(baseline_path)
    print(
        f"[baseline] csv={baseline_path} solved={base_solved}/{base_total} "
        f"total_time_s={base_total_time:.2f}"
    )
else:
    print(f"[baseline] missing={baseline_path}")

if solved < min_solved:
    raise SystemExit(
        f"solved threshold failed: got {solved}, expected at least {min_solved}"
    )
if total_time > max_total_time_s:
    raise SystemExit(
        f"time threshold failed: got {total_time:.2f}s, expected at most {max_total_time_s:.2f}s"
    )
PY
}

echo "=========================================="
echo "vLLM Evaluation"
echo "=========================================="
echo "Base URL   : $VLLM_BASE_URL"
echo "Agent      : $AGENT"
echo "Log Dir    : $LOG_DIR"
echo "Datasets   : $DATASETS"
echo "Configs    : $EVAL_CONFIGS"
echo "Search Ver : $SEARCH_VERSION"
echo "SearchDepth: $SEARCH_DEPTH"
echo "Ray CPUs   : $RAY_NUM_CPUS"
echo "Trace      : $ENABLE_TRACE"
echo "=========================================="

for dataset in "${DATASET_ITEMS[@]}"; do
    dataset_path="$(resolve_dataset_path "$dataset")"
    dataset_name="$(basename "$dataset_path")"

    for config in "${CONFIG_ITEMS[@]}"; do
        IFS=':' read -r decoding_size beam_size <<< "$config"
        if [ -z "${decoding_size:-}" ] || [ -z "${beam_size:-}" ]; then
            echo "Error: invalid config '$config'. Use decoding_size:beam_size." >&2
            exit 1
        fi

        eval_log="$LOG_DIR/$(basename "$dataset_path" .txt)_${AGENT}_d${decoding_size}_b${beam_size}.log"
        EVAL_ARGS=(
            --vllm_base_url "$VLLM_BASE_URL"
            --agent "$AGENT"
            --problems_path "$dataset_path"
            --decoding_size "$decoding_size"
            --beam_size "$beam_size"
            --search_depth "$SEARCH_DEPTH"
            --search_version "$SEARCH_VERSION"
            --ray_num_cpus "$RAY_NUM_CPUS"
            --timeout "$TIMEOUT"
            --log_dir "$LOG_DIR"
        )
        append_boolean_optional_arg EVAL_ARGS "enable_trace" "$ENABLE_TRACE"

        echo "Dataset    : $dataset_name"
        echo "Config     : decoding_size=$decoding_size beam_size=$beam_size"
        echo "Eval Log   : $eval_log"
        echo "------------------------------------------"

        set +e
        python "$REPO_ROOT/scripts/evaluation.py" "${EVAL_ARGS[@]}" 2>&1 | tee "$eval_log"
        status=${PIPESTATUS[0]}
        set -e

        if [ "$status" -ne 0 ]; then
            echo "Evaluation failed with exit code $status" >&2
            exit "$status"
        fi

        csv_path="$(latest_eval_csv_path "$dataset_path" "$decoding_size" "$beam_size")"
        echo "CSV Output : $csv_path"
        compare_eval_csv "$csv_path"
        echo "=========================================="
    done
done

echo "All evaluation tasks completed."
