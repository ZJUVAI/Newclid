#!/bin/bash
set -euo pipefail

# Rerun the two v23 safe-eval infrastructure failures with the normal
# evaluator so they no longer depend on Ray startup inside safe-eval.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3}"

MODEL_DIR="${MODEL_DIR:-models/grpo_vlm_sft44_geometry100k_v23_s1_4gpu_drgrpo_grouptoken}"
MODEL_RUN_DIR="${MODEL_RUN_DIR:-}"
CHECKPOINT_NAME="${CHECKPOINT_NAME:-checkpoint-500}"
MODEL_PATH="${MODEL_PATH:-}"
RESULTS_DIR="${RESULTS_DIR:-results/v23_drgrpo_grouptoken_checkpoint500_qwen3_vl_text_multiaux_infra_rerun}"

AGENT="${AGENT:-qwen3_vl_text}"
SEARCH_VERSION="${SEARCH_VERSION:-v1}"
MAX_WORKERS="${MAX_WORKERS:-40}"
DECODING_SIZE="${DECODING_SIZE:-32}"
BEAM_SIZE="${BEAM_SIZE:-512}"
SEARCH_DEPTH="${SEARCH_DEPTH:-4}"
TIMEOUT="${TIMEOUT:-3600}"
NUM_GPUS_FOR_EVAL="${NUM_GPUS_FOR_EVAL:-4}"
GPU_BATCH_SIZE="${GPU_BATCH_SIZE:-2}"
GPU_BATCH_TIMEOUT_MS="${GPU_BATCH_TIMEOUT_MS:-100}"

mkdir -p "$RESULTS_DIR"

if [ -z "$MODEL_PATH" ]; then
  if [ -z "$MODEL_RUN_DIR" ]; then
    MODEL_RUN_DIR="$(find "$MODEL_DIR" -maxdepth 1 -mindepth 1 -type d -name 'v*-*' | sort -V | tail -1)"
  fi

  if [ -z "$MODEL_RUN_DIR" ] || [ ! -d "$MODEL_RUN_DIR" ]; then
    echo "Unable to locate model run directory under $MODEL_DIR" >&2
    exit 1
  fi

  MODEL_PATH="$MODEL_RUN_DIR/$CHECKPOINT_NAME"
fi

if [ ! -d "$MODEL_PATH" ]; then
  echo "Checkpoint not found: $MODEL_PATH" >&2
  exit 1
fi

run_one() {
  local problem_file="$1"
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Evaluating $(basename "$problem_file")"
  .venv/bin/python scripts/evaluation.py \
    --problems_path "$problem_file" \
    --model_path "$MODEL_PATH" \
    --agent "$AGENT" \
    --search_version "$SEARCH_VERSION" \
    --max_workers "$MAX_WORKERS" \
    --decoding_size "$DECODING_SIZE" \
    --beam_size "$BEAM_SIZE" \
    --search_depth "$SEARCH_DEPTH" \
    --timeout "$TIMEOUT" \
    --num_gpus_for_eval "$NUM_GPUS_FOR_EVAL" \
    --gpu_batch_size "$GPU_BATCH_SIZE" \
    --gpu_batch_timeout_ms "$GPU_BATCH_TIMEOUT_MS" \
    --enable_trace \
    --log_dir "$RESULTS_DIR"
}

run_one "$REPO_ROOT/tmp/imo95_score_diff_11_epu2let4/0001_imo_sl_2002_g7_variant.txt"
run_one "$REPO_ROOT/tmp/imo95_score_diff_11_epu2let4/0006_imo_sl_2013_g2.txt"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Infra rerun finished"
