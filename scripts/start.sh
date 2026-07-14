#!/usr/bin/env bash
# Start the whole stack — LLM server, backend, frontend — and shut down again on Ctrl-C.
# Windows: use scripts/start.ps1. First-time LLM install: scripts/setup-llm.sh.
#
# Only processes this script starts are stopped again. An Ollama that was already
# running (brew service, menu-bar app, systemd) is left exactly as it was found.
set -euo pipefail
set -m                                   # each background job leads its own process group

cd "$(dirname "$0")/.."
ROOT="$PWD"

MODEL="${LLM_MODEL:-qwen3.5:4b}"
BASE_URL="${LLM_BASE_URL:-http://localhost:11434/v1}"
OLLAMA_HOST_URL="${BASE_URL%/v1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

OLLAMA_PID=""     # set only if *we* start the server
BACKEND_PID=""
FRONTEND_PID=""

log() { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$1" >&2; }

stop() {
  local name="$1" pid="$2"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null || return 0
  log "stopping $name"
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.25
  done
  kill -KILL -- "-$pid" 2>/dev/null || true
}

cleanup() {
  trap - EXIT INT TERM
  echo
  stop "frontend" "$FRONTEND_PID"
  stop "backend" "$BACKEND_PID"
  if [ -n "$OLLAMA_PID" ]; then
    stop "ollama (we started it)" "$OLLAMA_PID"
  else
    log "leaving Ollama running — it was already up before this script"
  fi
}
trap cleanup EXIT INT TERM

wait_for() {                             # wait_for <url> <seconds> <what>
  for _ in $(seq 1 "$2"); do
    curl -fsS "$1" >/dev/null 2>&1 && return 0
    sleep 1
  done
  warn "$3 did not come up at $1"
  return 1
}

# ---------------------------------------------------------------- 1. LLM server
if ! command -v ollama >/dev/null 2>&1; then
  warn "Ollama is not installed — run ./scripts/setup-llm.sh first (see docs/reference/llm-setup.md)"
  exit 1
fi

if curl -fsS "$OLLAMA_HOST_URL/api/version" >/dev/null 2>&1; then
  log "Ollama already running at $OLLAMA_HOST_URL — leaving it alone"
else
  log "starting Ollama at $OLLAMA_HOST_URL"
  ollama serve >/dev/null 2>&1 &
  OLLAMA_PID=$!
  wait_for "$OLLAMA_HOST_URL/api/version" 30 "Ollama" || exit 1
fi

if ! ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
  log "model $MODEL is missing — pulling it (one time, ~3.4 GB)"
  ollama pull "$MODEL"
fi
log "model ready: $MODEL"

# Embedding model for docs Q&A — the chat degrades to keyword-only retrieval
# without it, so missing is a warning, not a failure.
EMBED_MODEL="${RAG_EMBED_MODEL:-nomic-embed-text}"
if ! ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx -e "$EMBED_MODEL" -e "$EMBED_MODEL:latest"; then
  log "embedding model $EMBED_MODEL is missing — pulling it (one time, ~274 MB)"
  ollama pull "$EMBED_MODEL" || warn "could not pull $EMBED_MODEL — docs Q&A falls back to keyword search"
fi

# ------------------------------------------------------------------- 2. backend
[ -d "$ROOT/backend/.venv" ] || warn "no backend/.venv — using the active Python (see README)"
log "starting backend on :$BACKEND_PORT"
(
  cd "$ROOT/backend"
  # shellcheck disable=SC1091
  [ -f .venv/bin/activate ] && source .venv/bin/activate
  exec uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
) &
BACKEND_PID=$!
wait_for "http://localhost:$BACKEND_PORT/health" 60 "backend" || exit 1

# ------------------------------------------------------------------ 3. frontend
[ -d "$ROOT/frontend/node_modules" ] || (log "installing frontend deps" && cd "$ROOT/frontend" && npm install)
log "starting frontend on :4200"
(cd "$ROOT/frontend" && exec npm start) &
FRONTEND_PID=$!

cat <<EOF

  UI        http://localhost:4200      (LLM Chat panel, bottom of the left pane)
  API docs  http://localhost:$BACKEND_PORT/docs
  LLM       $MODEL via $OLLAMA_HOST_URL

  Ctrl-C stops everything this script started.

EOF

# Exit as soon as *any* of them dies, so a crashed backend doesn't look like a hang.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
warn "a service exited — shutting the rest down"
