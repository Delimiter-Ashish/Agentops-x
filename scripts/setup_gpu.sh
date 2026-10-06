#!/bin/bash
# Phase 2 setup: a separate virtualenv `Aopx-llm` for the vLLM inference server.
# (The model server is its own service with its own pinned torch/CUDA stack, as in production.)
set -euo pipefail
cd "$(dirname "$0")/.."
export PIP_CACHE_DIR="$(pwd)/.cache/pip"
SYS="$(pwd)/.tools/sys"
if [ ! -d Aopx-llm ]; then
  "$SYS/bin/python3" -m venv --prompt Aopx-llm Aopx-llm
fi
Aopx-llm/bin/pip install -q --upgrade pip
Aopx-llm/bin/pip install -r requirements-gpu.txt
Aopx/bin/pip install -q nvidia-ml-py==13.615.71
Aopx-llm/bin/python -c "import vllm, torch; print('vllm', vllm.__version__, '| torch', torch.__version__, '| cuda', torch.cuda.is_available())"
echo "GPU setup complete."
