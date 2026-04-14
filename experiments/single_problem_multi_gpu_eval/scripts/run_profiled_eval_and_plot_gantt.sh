#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
usage:
  run_profiled_eval_and_plot_gantt.sh [wrapper args] -- <evaluation args...>

wrapper args:
  --problem <problem name or index>   required; forwarded to plot_worker_gantt.py
  --output <path>                     optional; default is under $RESULT_ROOT/analysis/<run_stem>/
  --depth <n>                         optional; repeatable
  --dpi <n>                           optional; default 160
  --include_base_ddar                 optional

example:
  bash experiments/single_problem_multi_gpu_eval/scripts/run_profiled_eval_and_plot_gantt.sh \
    --problem 0 \
    -- --problems_path benchmarks/imo_2008_p1b.txt \
       --model_path /path/to/checkpoint \
       --agent vlm \
       --max_workers 40 \
       --decoding_size 32 \
       --beam_size 512 \
       --search_depth 4 \
       --timeout 3600 \
       --num_gpus_for_eval 4 \
       --gpu_batch_size 2 \
       --gpu_batch_timeout_ms 100 \
       --torch_seed 42
EOF
  exit 1
}

PLOT_PROBLEM=""
PLOT_OUTPUT=""
PLOT_DPI="160"
INCLUDE_BASE_DDAR=0
DEPTH_ARGS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --problem)
      [ "$#" -ge 2 ] || usage
      PLOT_PROBLEM="$2"
      shift 2
      ;;
    --output)
      [ "$#" -ge 2 ] || usage
      PLOT_OUTPUT="$2"
      shift 2
      ;;
    --depth)
      [ "$#" -ge 2 ] || usage
      DEPTH_ARGS+=("--depth" "$2")
      shift 2
      ;;
    --dpi)
      [ "$#" -ge 2 ] || usage
      PLOT_DPI="$2"
      shift 2
      ;;
    --include_base_ddar)
      INCLUDE_BASE_DDAR=1
      shift
      ;;
    --help|-h)
      usage
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "unknown wrapper arg: $1" >&2
      usage
      ;;
  esac
done

if [ -z "$PLOT_PROBLEM" ] || [ "$#" -eq 0 ]; then
  usage
fi

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT_DIR"

COMMIT_ID="$(git rev-parse HEAD)"
RESULT_ROOT="${RESULT_ROOT:-results/profiling/single_problem_multi_gpu_${COMMIT_ID}}"
export RESULT_ROOT

RUN_STEM="$(python - "$@" <<'PY'
import argparse
from pathlib import Path
from scripts.evaluation import build_eval_output_stem

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--agent", required=True)
parser.add_argument("--problems_path", required=True)
parser.add_argument("--model_path", required=True)
parser.add_argument("--decoding_size", type=int, required=True)
parser.add_argument("--beam_size", type=int, required=True)
parser.add_argument("--search_depth", type=int, required=True)
parser.add_argument("--gpu_batch_size", type=int, default=1)
parser.add_argument("--gpu_batch_timeout_ms", type=int, default=0)
parser.add_argument("--torch_seed", type=int, default=123)
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
        torch_seed=args.torch_seed,
    )
)
PY
)"

bash experiments/single_problem_multi_gpu_eval/scripts/run_profiled_eval.sh "$@"

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

if [ -z "$PLOT_OUTPUT" ]; then
  SAFE_PROBLEM="$(python - "$PLOT_PROBLEM" <<'PY'
import re
import sys
value = sys.argv[1]
if value.isdigit():
    value = f"problem_{value}"
print(re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "problem")
PY
)"
  PLOT_OUTPUT="$RESULT_ROOT/analysis/$RUN_STEM/${SAFE_PROBLEM}_worker_gantt.svg"
fi

PLOT_CMD=(
  python
  scripts/plot_worker_gantt.py
  --run_dir "$LATEST_RUN_DIR"
  --problem "$PLOT_PROBLEM"
  --output "$PLOT_OUTPUT"
  --dpi "$PLOT_DPI"
)
if [ "$INCLUDE_BASE_DDAR" -eq 1 ]; then
  PLOT_CMD+=(--include_base_ddar)
fi
if [ "${#DEPTH_ARGS[@]}" -gt 0 ]; then
  PLOT_CMD+=("${DEPTH_ARGS[@]}")
fi

"${PLOT_CMD[@]}"
echo "Worker gantt written to $PLOT_OUTPUT"
