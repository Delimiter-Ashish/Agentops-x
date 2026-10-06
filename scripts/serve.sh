#!/bin/bash
# Start Postgres (if needed) and the AgentOps-X API on :8000
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/db.sh start
exec uvicorn server.main:app --host 127.0.0.1 --port "${API_PORT:-8000}"
