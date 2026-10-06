#!/bin/bash
# One-time setup on Linux without root or Docker.
# Installs Python 3.11, PostgreSQL 16 and Node.js 20 into ./.tools (user space),
# creates the project virtualenv ./Aopx, installs dependencies, and initializes the database.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
export MAMBA_ROOT_PREFIX="$ROOT/.tools/mamba"
export PIP_CACHE_DIR="$ROOT/.cache/pip"
MAMBA="$ROOT/.tools/bin/micromamba"
SYS="$ROOT/.tools/sys"

if [ ! -x "$MAMBA" ]; then
  echo ">> downloading micromamba"
  mkdir -p .tools
  curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C .tools bin/micromamba
fi
if [ ! -x "$SYS/bin/python3" ]; then
  echo ">> installing python 3.11, postgresql 16, nodejs 20 (user space)"
  "$MAMBA" create -y -q -p "$SYS" -c conda-forge python=3.11 postgresql=16 nodejs=20
fi
if [ ! -d Aopx ]; then
  echo ">> creating virtualenv Aopx"
  "$SYS/bin/python3" -m venv --prompt Aopx Aopx
  # make postgres + node available whenever the venv is active
  echo "export PATH=\"$SYS/bin:\$PATH\"" >> Aopx/bin/activate
fi
source Aopx/bin/activate
pip install -q --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
bash scripts/db.sh init
echo
echo "Setup complete. Each new terminal:  source Aopx/bin/activate"
