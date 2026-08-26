#!/usr/bin/env bash
#
# Start the Flatland Dispatcher demo (Angular UI served by the FastAPI backend).
#
# Idempotent: sets up whatever is missing, skips whatever is there, then starts
# the server. A warm start takes seconds; a cold one builds the frontend and
# installs Python deps.
#
# Usage:
#   ./start-demo.sh              # http://127.0.0.1:8000
#   ./start-demo.sh 8080         # a different port
#   ./start-demo.sh 8000 --lan   # also reachable from the same network
#   ./start-demo.sh 8000 "" --rebuild   # force a frontend rebuild
set -euo pipefail

cd "$(dirname "$0")"

PORT="${1:-8000}"
MODE="${2:-}"
REBUILD="${3:-}"

BACKEND=backend
FRONTEND=frontend
VENV="$BACKEND/.venv-run"

# ── backend deps ────────────────────────────────────────────────────────────
if [ ! -x "$VENV/bin/python" ]; then
  echo "→ creating $VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
fi

# flatland-rl and torch resolve only against public PyPI here: the default index
# in this environment is an internal mirror that does not carry them.
PYPI=(--index-url https://pypi.org/simple)

if ! "$VENV/bin/python" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "→ installing backend requirements"
  "$VENV/bin/python" -m pip install --quiet "${PYPI[@]}" -r "$BACKEND/requirements.txt"
fi

if ! "$VENV/bin/python" -c "import flatland" >/dev/null 2>&1; then
  echo "→ installing flatland-rl"
  "$VENV/bin/python" -m pip install --quiet "${PYPI[@]}" "flatland-rl==4.2.6"
fi

# torch is only needed by the goal-directed planner's models. Without it the
# Director still runs, but on the model-free fallback: no per-axis utilities, so
# the A/B/C strategy tiles come back without numbers.
if ! "$VENV/bin/python" -c "import torch" >/dev/null 2>&1; then
  if [ -f "$BACKEND/models/goal_directed/evaluator.ckpt" ]; then
    echo "→ installing torch (needed by the Director planner's models)"
    "$VENV/bin/python" -m pip install --quiet "${PYPI[@]}" "torch==2.8.0"
  else
    echo "! no model checkpoints in $BACKEND/models/goal_directed — the Director"
    echo "  will run model-free and the strategy tiles will show no forecast"
  fi
fi

# ── frontend build → served statically by the backend ───────────────────────
DIST="$FRONTEND/dist/frontend/browser"
if [ "$REBUILD" = "--rebuild" ] || [ ! -f "$BACKEND/static/index.html" ]; then
  if [ ! -d "$FRONTEND/node_modules" ]; then
    echo "→ npm install (this takes a while)"
    (cd "$FRONTEND" && npm install --no-fund --no-audit >/dev/null)
  fi
  echo "→ building the frontend"
  (cd "$FRONTEND" && npx ng build --configuration development >/dev/null)
  echo "→ deploying to $BACKEND/static"
  mkdir -p "$BACKEND/static"
  cp -R "$DIST/." "$BACKEND/static/"
fi

# ── run ─────────────────────────────────────────────────────────────────────
echo "→ starting on http://127.0.0.1:${PORT}"

if [ "$MODE" = "--lan" ]; then
  # Bind on all interfaces for colleagues on the same network. Deliberate only:
  # the app has no authentication.
  echo "  LAN mode — no authentication, use on a trusted network only"
  cd "$BACKEND"
  exec .venv-run/bin/python -m uvicorn app.main:app \
    --host 0.0.0.0 --port "${PORT}" --log-level warning
fi

cd "$BACKEND"
exec .venv-run/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port "${PORT}" --log-level warning
