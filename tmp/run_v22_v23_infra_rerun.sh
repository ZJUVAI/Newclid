#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p "$REPO_ROOT/tmp"
exec > >(tee "$REPO_ROOT/tmp/run_v22_v23_infra_rerun.log") 2>&1

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting v22 infra rerun"
bash "$REPO_ROOT/tmp/eval_v22_infra_rerun.sh"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting v23 infra rerun"
bash "$REPO_ROOT/tmp/eval_v23_infra_rerun.sh"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] All infra reruns finished"
