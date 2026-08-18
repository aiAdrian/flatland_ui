#!/usr/bin/env bash
#
# Start the Director Mode Reflection Playground.
#
# Idempotent: creates the venv and installs dependencies on first run, then
# starts Streamlit. Safe to run repeatedly — the point is that the demo can be
# brought back up in one command, without remembering any setup.
#
# Usage:
#   ./start-demo.sh              # http://localhost:8501
#   ./start-demo.sh 8600         # a different port
#   ./start-demo.sh 8501 --lan   # also reachable from the same network
set -euo pipefail

cd "$(dirname "$0")"

PORT="${1:-8501}"
MODE="${2:-}"

if [ ! -x .venv/bin/python ]; then
  echo "→ creating .venv"
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
fi

# Cheap check: only install when Streamlit is missing, so a normal start is fast.
if ! .venv/bin/python -c "import streamlit" >/dev/null 2>&1; then
  echo "→ installing requirements"
  .venv/bin/python -m pip install --quiet -r requirements.txt
fi

echo "→ self-check"
.venv/bin/python -m pytest -q >/dev/null && echo "  tests ok"

echo "→ starting on http://localhost:${PORT}"

# Two explicit exec paths instead of an argument array: macOS ships bash 3.2,
# where expanding an empty array under `set -u` aborts the script.
if [ "$MODE" = "--lan" ]; then
  # Bind on all interfaces so colleagues on the same network can open it. Only
  # deliberately: the app has no authentication.
  echo "  LAN mode — no authentication, use on a trusted network only"
  exec .venv/bin/python -m streamlit run app.py \
    --server.port "${PORT}" \
    --server.headless true \
    --server.address 0.0.0.0
fi

exec .venv/bin/python -m streamlit run app.py \
  --server.port "${PORT}" \
  --server.headless true
