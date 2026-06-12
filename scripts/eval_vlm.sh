#!/bin/bash
set -euo pipefail

echo "scripts/eval_vlm.sh is deprecated."
echo "Evaluation is now vLLM-only."
echo "1. Start a server with scripts/launch_vllm_server.py --model_name <checkpoint>"
echo "2. Run scripts/eval.sh with AGENT=qwen3_vl and VLLM_BASE_URL pointing to that server."
exit 1
