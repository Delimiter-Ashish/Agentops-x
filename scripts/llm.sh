#!/bin/bash
# Start the self-hosted LLM (OpenAI-compatible API) with tool calling and Prometheus metrics.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
export HF_HOME="$(pwd)/models"                  # model weights are cached inside the project
unset HF_TOKEN_PATH HF_HUB_CACHE TRANSFORMERS_CACHE  # ignore cache settings from other projects
export VLLM_USE_FLASHINFER_SAMPLER=0             # PyTorch sampler: no CUDA toolkit (nvcc) required
MODEL="${LOCAL_MODEL:-Qwen/Qwen2.5-14B-Instruct}"
echo "serving $MODEL on 127.0.0.1:${VLLM_PORT:-8001} (first start downloads the weights)"
exec Aopx-llm/bin/vllm serve "$MODEL" \
  --host 127.0.0.1 --port "${VLLM_PORT:-8001}" --api-key "${VLLM_API_KEY:-local}" \
  --enable-auto-tool-choice --tool-call-parser "${TOOL_PARSER:-hermes}" \
  --max-model-len "${MAX_MODEL_LEN:-16384}" --gpu-memory-utilization "${GPU_MEM_UTIL:-0.85}"
