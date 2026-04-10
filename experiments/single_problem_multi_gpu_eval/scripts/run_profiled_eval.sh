#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <evaluation args...>" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT_DIR"

COMMIT_ID="$(git rev-parse HEAD)"
RESULT_ROOT="${RESULT_ROOT:-results/profiling/vlm_sft44_4gpu_new_${COMMIT_ID}}"
mkdir -p "$RESULT_ROOT/logs" "$RESULT_ROOT/system_metrics" "$RESULT_ROOT/analysis"

RUN_STEM="$(python - "$@" <<'PY'
import argparse
from pathlib import Path
from experiments.single_problem_multi_gpu_eval.evaluation_single_problem_multi_gpu import build_eval_output_stem

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--agent", required=True)
parser.add_argument("--problems_path", required=True)
parser.add_argument("--model_path", required=True)
parser.add_argument("--decoding_size", type=int, required=True)
parser.add_argument("--beam_size", type=int, required=True)
parser.add_argument("--search_depth", type=int, required=True)
parser.add_argument("--gpu_batch_size", type=int, default=1)
parser.add_argument("--gpu_batch_timeout_ms", type=int, default=0)
args, _ = parser.parse_known_args()
print(
    build_eval_output_stem(
        agent_type=args.agent,
        problems_path=Path(args.problems_path),
        model_path=args.model_path,
        decoding_size=args.decoding_size,
        beam_size=args.beam_size,
        search_depth=args.search_depth,
        gpu_batch_size=args.gpu_batch_size,
        gpu_batch_timeout_ms=args.gpu_batch_timeout_ms,
    )
)
PY
)"

LOG_PATH="$RESULT_ROOT/logs/${RUN_STEM}.log"
SYSTEM_DIR="$RESULT_ROOT/system_metrics/${RUN_STEM}"
ANALYSIS_DIR="$RESULT_ROOT/analysis/${RUN_STEM}"
mkdir -p "$SYSTEM_DIR" "$ANALYSIS_DIR"

cleanup() {
  for pid in ${MPSTAT_PID:-} ${PIDSTAT_PID:-} ${NVIDIA_PID:-}; do
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

mark_unavailable() {
  local path="$1"
  local message="$2"
  printf '%s\n' "$message" >"$path"
}

if command -v mpstat >/dev/null 2>&1; then
  mpstat -P ALL 1 >"$SYSTEM_DIR/mpstat.log" 2>&1 &
  MPSTAT_PID=$!
else
  mark_unavailable "$SYSTEM_DIR/mpstat.log" "mpstat unavailable: install sysstat to enable CPU sampling"
fi

if command -v pidstat >/dev/null 2>&1; then
  pidstat -u -r -w -H 1 >"$SYSTEM_DIR/pidstat.log" 2>&1 &
  PIDSTAT_PID=$!
else
  mark_unavailable "$SYSTEM_DIR/pidstat.log" "pidstat unavailable: install sysstat to enable per-process sampling"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi dmon -s pucm -d 1 >"$SYSTEM_DIR/nvidia_smi_dmon.log" 2>&1 &
  NVIDIA_PID=$!
else
  mark_unavailable "$SYSTEM_DIR/nvidia_smi_dmon.log" "nvidia-smi unavailable: GPU sampling disabled"
fi

cat >"$SYSTEM_DIR/meta.json" <<EOF
{
  "git_commit": "${COMMIT_ID}",
  "result_root": "${RESULT_ROOT}",
  "run_stem": "${RUN_STEM}",
  "argv": $(python - "$@" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1:], ensure_ascii=False))
PY
)
}
EOF

python experiments/single_problem_multi_gpu_eval/evaluation_single_problem_multi_gpu.py \
  --log_dir "$RESULT_ROOT" \
  --trace_dir "$RESULT_ROOT" \
  --enable_profiling \
  "$@" | tee "$LOG_PATH"

LATEST_RUN_DIR="$(python - "$RESULT_ROOT" "$RUN_STEM" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
stem = sys.argv[2]
candidates = sorted(p for p in root.glob(f"{stem}_*") if p.is_dir())
if not candidates:
    raise SystemExit("no trace run directory found")
print(candidates[-1])
PY
)"

python experiments/single_problem_multi_gpu_eval/scripts/analyze_eval_trace.py \
  --run_dir "$LATEST_RUN_DIR" \
  --output_dir "$ANALYSIS_DIR" | tee "$ANALYSIS_DIR/summary.txt"
