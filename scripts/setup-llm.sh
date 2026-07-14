#!/usr/bin/env bash
# Set up the local LLM (macOS / Linux). Windows: use scripts/setup-llm.ps1.
# See docs/reference/llm-setup.md for the full guide.
set -euo pipefail

MODEL="${LLM_MODEL:-qwen3.5:4b}"
BASE_URL="${LLM_BASE_URL:-http://localhost:11434/v1}"

echo "==> Checking for Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  cat <<'EOF'
Ollama is not installed.

  macOS   : brew install ollama     (or download the app: https://ollama.com/download)
  Linux   : curl -fsSL https://ollama.com/install.sh | sh

Install it, then re-run this script.

Note: do NOT run Ollama in Docker on macOS — Docker Desktop cannot reach the
Apple Silicon GPU, so the model falls back to CPU and is unusably slow.
EOF
  exit 1
fi
echo "    found: $(ollama --version)"

echo "==> Checking the Ollama server is up"
if ! curl -fsS "${BASE_URL%/v1}/api/version" >/dev/null 2>&1; then
  echo "    server not responding — starting it"
  if command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | grep -q '^ollama'; then
    brew services start ollama
  elif command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q '^ollama'; then
    sudo systemctl start ollama
  else
    echo "    could not start it automatically — run 'ollama serve' in another terminal"
    exit 1
  fi
  for _ in $(seq 1 30); do
    curl -fsS "${BASE_URL%/v1}/api/version" >/dev/null 2>&1 && break
    sleep 1
  done
fi
echo "    server up at ${BASE_URL%/v1}"

echo "==> Pulling model: $MODEL"
ollama pull "$MODEL"

EMBED_MODEL="${RAG_EMBED_MODEL:-nomic-embed-text}"
echo "==> Pulling embedding model: $EMBED_MODEL (docs Q&A retrieval, ~274 MB)"
ollama pull "$EMBED_MODEL"

# Tested over HTTP rather than `ollama run`: same wire format the backend uses, and
# the output stays readable when piped to a log.
echo "==> Smoke test: chat model"
reply=$(curl -fsS "$BASE_URL/chat/completions" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly one word: ready\"}],\"reasoning_effort\":\"none\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"].strip())')
if [ -z "$reply" ]; then
  echo "    FAILED — $MODEL returned no text" >&2
  exit 1
fi
echo "    $MODEL says: $reply"

echo "==> Smoke test: embedding model (docs Q&A)"
dims=$(curl -fsS "$BASE_URL/embeddings" \
  -H 'content-type: application/json' \
  -d "{\"model\":\"$EMBED_MODEL\",\"input\":\"railway dispatching\"}" \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["data"][0]["embedding"]))')
echo "    $EMBED_MODEL returns ${dims}-dimensional vectors"

cat <<EOF

==> Done.

The backend defaults to this setup, so there is nothing else to configure.
To override, copy backend/.env.example to backend/.env.

Verify through the API:
  cd backend && ./run.sh
  curl localhost:8000/llm/health
  curl -X POST localhost:8000/llm/complete -H 'content-type: application/json' \\
       -d '{"prompt":"Say hello in one sentence."}'
EOF
