#!/bin/bash
# Build the React dashboard into dashboard/dist (served by the API at "/").
set -euo pipefail
cd "$(dirname "$0")/../dashboard"
npm ci --no-audit --no-fund
npm run build
