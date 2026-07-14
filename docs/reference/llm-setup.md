# LLM setup — local, hosted API, and cloud-hosted

The backend talks to language models through one interface (`app/llm/base.py`)
with three interchangeable providers. Which one is live is an environment
variable, not a code change:

| Provider id | What it is | Needs a key |
|---|---|---|
| `ollama` *(default)* | A small model on **your own machine** | No |
| `anthropic` | **Claude**, via the official Anthropic SDK | Yes |
| `openai_compatible` | Any **cloud-hosted** OpenAI-compatible endpoint (vLLM, TGI, Ollama Cloud) | Usually |

If you only want the project to run, do **Part 1** and stop.

---

## Part 1 — Local model (the default)

You need [Ollama](https://ollama.com). It runs natively on macOS, Windows and
Linux, and picks up your GPU automatically with no configuration.

### 1. Install Ollama

**macOS** (Apple Silicon or Intel)
```bash
brew install ollama
# or download the app: https://ollama.com/download
```
Homebrew installs the CLI; the `.dmg` from the website installs a menu-bar app
that keeps the server running in the background. Either is fine.

**Windows** (x86_64 *and* ARM64 — no WSL required)
```powershell
winget install Ollama.Ollama
# or download the installer: https://ollama.com/download
```

**Linux**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Run the setup script

It starts the server, downloads the model (~3.4 GB) and smoke-tests it.

```bash
# macOS / Linux
./scripts/setup-llm.sh
```
```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\setup-llm.ps1
```

That is the whole setup. The backend defaults to exactly this configuration, so
there is no `.env` to write unless you want to change something.

### 3. Verify

```bash
cd backend && ./run.sh          # or: uvicorn app.main:app --reload

curl localhost:8000/llm/health
# {"provider":"ollama","model":"qwen3.5:4b","reachable":true, ...}

curl -X POST localhost:8000/llm/complete \
     -H 'content-type: application/json' \
     -d '{"prompt":"Say hello in one sentence."}'
```

`GET /llm/providers` lists all three backends and marks the active one.

### 4. Or just chat with it in the UI

```bash
./scripts/start.sh                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File scripts\start.ps1  # Windows
```

This brings up the model server, the backend and the frontend together, and stops
them again on Ctrl-C. Nothing here is a background daemon the app owns — see
*Who starts what* below.

Open <http://localhost:4200>, start a session, and there is an **LLM Chat** panel at
the bottom of the left pane — collapsed by default, so expand it.

It shows which model is live (green dot + model name), and you can talk to it. It
calls `POST /llm/chat` and resends the transcript each turn, so follow-up questions
keep their context. Because it goes through the same seam, it talks to whichever
provider is configured — swap `LLM_PROVIDER` to `anthropic` and the panel is
suddenly talking to Claude, with no frontend change.

The panel answers **questions about the project** — how the UI works, what the
modes do, how Flatland behaves — grounded in the repo's own docs (see *Docs Q&A*
below), and shows which files an answer came from. It still has no access to the
**running simulation** and will say so if you ask about the live run.

### Who starts what

There are three separate processes, and **starting the frontend does not start the
others**. The frontend talks to the backend; the backend talks to the model server
over HTTP. Nothing in the app spawns a daemon on its own — deliberately, because
with `LLM_PROVIDER=anthropic` or a remote endpoint there is nothing local to spawn.

| Process | Listens on | Started by |
|---|---|---|
| Ollama (holds the model) | `11434` | you, or `scripts/start.sh` |
| FastAPI backend | `8000` | you, or `scripts/start.sh` |
| Angular frontend | `4200` | you, or `scripts/start.sh` |

`scripts/start.sh` (and `start.ps1`) is the convenience wrapper: it starts whatever
is not already up, and on Ctrl-C stops **only what it started**. If Ollama was
already running as a system service — `brew services start ollama`, the macOS
menu-bar app, the Windows tray app, systemd — it is left running, because it may
be serving other things and it was not ours to stop.

If the model server is down, nothing hangs: the chat panel probes `GET /llm/health`
when it opens and shows a red dot with the actual reason.

Note the model itself is loaded into RAM lazily, on the first request, and Ollama
unloads it again after a few idle minutes — so the first message after a pause is
slower than the rest. That is paging, not a bug.

### The model

`qwen3.5:4b` — 3.4 GB, 256K context, and (the part that matters) it supports
**tool calling**, which anything driving the dispatcher will need. Sizes:

| Tag | Download | For |
|---|---|---|
| `qwen3.5:2b` | 2.7 GB | 8 GB RAM machines, CI |
| **`qwen3.5:4b`** | **3.4 GB** | **default** |
| `qwen3.5:9b` | 6.6 GB | 16 GB+, better quality |

To use a different size, set `LLM_MODEL` in `backend/.env` and `ollama pull` it.

### Docs Q&A — how the panel knows the project

A 4B model cannot be trusted to *know* this repo, so it doesn't have to: each
question to `POST /llm/chat` first retrieves the most relevant snippets from the
repo's own markdown (`README.md`, `PLAYGROUND.md`, `docs/reference/`,
`docs/scenarios/`) and hands them to the model, which answers from them and
cites the files. Retrieval also sees the recent conversation (at reduced
weight), so follow-ups like "and how do I turn that on?" find the right docs
even though the question alone names no topic. Why it is built this way —
hybrid retrieval, no vector database — is in *Design decisions* below.

It needs one extra model, pulled automatically by `setup-llm` and `start`:

```bash
ollama pull nomic-embed-text     # 274 MB, runs on the same Ollama server
```

Verify with:

```bash
curl localhost:8000/llm/rag/status
# {"enabled":true,"files":24,"chunks":292,"embeddings_available":true,...}
```

The first question after a docs change is slower — the index rebuilds lazily
(changed chunks only) and persists to `backend/.rag-index/` (gitignored). If the
embedding model is missing, retrieval degrades to keyword-only search and
`/llm/rag/status` says so; chat itself never breaks. Knobs in `backend/.env`:
`RAG_ENABLED`, `RAG_EMBED_MODEL`, `RAG_EMBED_BASE_URL`, `RAG_TOP_K`, `RAG_DOCS`
(retrieval always talks to the local endpoint, even when the chat provider is
Claude or a cloud box).

### Why thinking is switched off by default

Qwen3.5 is a *thinking* model: left to its own devices it writes a chain of
thought before answering, and Ollama enables that by default. On a laptop this
is painful — "say hi in one sentence" spent **13 s** reasoning, hit the token
cap, and returned an **empty** answer. The same prompt with reasoning off
answers in **0.85 s**.

So the default is `LLM_REASONING_EFFORT=none`, which makes the model answer
directly. Raise it (`low` / `medium` / `high`) if a task genuinely needs
deliberation, and raise `LLM_MAX_TOKENS` with it. If the model ever runs out of
budget mid-thought, the backend raises a clear error rather than handing you an
empty string.

### ⚠️ Do not run Ollama in Docker on macOS

Apple Silicon has a GPU — it is integrated into the SoC rather than a separate
card, and Ollama drives it through Metal automatically. But **Docker Desktop for
Mac cannot reach it**: containers run inside a Linux VM with no Metal
passthrough. Ollama in a Mac container is therefore CPU-only and unusably slow.

Docker GPU passthrough works only on native Linux (NVIDIA/CUDA) and on Windows
via WSL2. This is why the backend does not depend on an Ollama container and why
the install instructions above are native ones. On Linux you may of course run
Ollama in Docker yourself and just point `LLM_BASE_URL` at it.

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `reachable: false`, "Connection refused" | Server isn't running. `ollama serve` (or `brew services start ollama`). |
| `reachable: false`, "endpoint is up but has no model …" | Model not pulled. `ollama pull qwen3.5:4b`. |
| Answers take tens of seconds | Model doesn't fit in RAM and is swapping. Drop to `qwen3.5:2b`. |
| First request is slow, later ones fast | Normal — the model is being loaded into memory. |
| Answers ignore the docs / no "Sources:" line | `curl localhost:8000/llm/rag/status` — if `embeddings_available` is false: `ollama pull nomic-embed-text`. |

---

## Part 2 — Claude (hosted API)

```dotenv
# backend/.env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-opus-4-8
LLM_API_KEY=sk-ant-...
LLM_EFFORT=medium          # low | medium | high | xhigh | max
```

No other change is needed — every consumer of the seam keeps working.

Claude does **not** go through the OpenAI-compatible adapter. It uses the
official `anthropic` SDK (`app/llm/anthropic.py`), because an OpenAI shim would
cost us adaptive thinking, prompt caching and full tool-use fidelity. The
adapter enables adaptive thinking and exposes the depth/cost tradeoff as
`LLM_EFFORT`; `LLM_MAX_TOKENS` caps thinking *and* the answer together, so keep
it generous.

---

## Part 3 — Cloud-hosted model

Anything that speaks the OpenAI `/v1/chat/completions` format — a vLLM or TGI
server on a university/cloud GPU box, or Ollama Cloud:

```dotenv
# backend/.env
LLM_PROVIDER=openai_compatible
LLM_MODEL=Qwen/Qwen3.5-9B
LLM_BASE_URL=https://your-gpu-box.example.org/v1
LLM_API_KEY=...
```

This is the same adapter the local provider uses — Ollama and vLLM speak the
same wire format — so a model validated on a laptop behaves the same way when
moved to a server.

---

## For developers: using the seam

Depend on `LLMProvider`, never on a concrete provider:

```python
from app.llm.base import ChatMessage
from app.llm.registry import active_provider

result = await active_provider().complete(
    [ChatMessage(role="user", content="...")],
    system="You are a railway dispatcher assistant.",
)
result.text  # str
```

Provider failures arrive as `LLMError`, whichever SDK is underneath.

**In tests, use `FakeProvider`** (`tests/test_llm_registry.py`) rather than a
running model, so the suite stays hermetic and fast:

```python
monkeypatch.setattr("app.api.llm.active_provider", lambda cfg: FakeProvider(reply="..."))
```

`tests/test_llm_live.py` is the only test that touches a real model, and it
skips itself when none is running.

To add a fourth provider: implement `LLMProvider` and register a `ProviderSpec`
in `app/llm/registry.py`. Nothing else changes.

---

## Design decisions

The reasoning behind the choices above, so they are not silently re-litigated.
Each was a real fork in the road.

### Why a thin in-repo registry, not LiteLLM

LiteLLM is the obvious "one library, 100+ providers" answer, and it works — but
it normalises *every* provider onto the OpenAI request shape, which for Claude
costs exactly the things worth having: adaptive thinking, prompt caching, and
full tool-use fidelity. Anthropic's own guidance is to call Claude through its
official SDK, never an OpenAI shim. It is also a large dependency tree for a
backend that needs three providers.

So the seam mirrors the two registries the repo already has
(`app/policies/registry.py`, `app/core/recommenders/registry.py`): ABC + spec
dataclass + dict registry + factory. If we ever need many providers cheaply
(benchmarking ten models), LiteLLM can be added as a *fourth adapter behind the
same interface* — a contained change, not a rewrite.

### Why no vector database for the docs Q&A

The corpus is ~24 files → ~290 chunks. Vector databases exist to make
*approximate* search over millions of vectors fast; at a few hundred, exact
cosine over a numpy matrix is microseconds — **faster and more accurate than any
database**, with zero new dependencies (`numpy` is already pinned; the keyword
side is SQLite FTS5 from the standard library).

Rejected, and why: **ChromaDB** (heavy dependency tree; its own docs call it a
prototyping tool) · **sqlite-vec** (the lightest real store, but pre-v1 alpha,
warns of breaking storage-format changes) · **FAISS/LanceDB** (native builds for
no benefit at this size) · **LangChain/LlamaIndex** (frameworks owning ~150 lines
of plain Python) · **fine-tuning** (bakes the docs into weights: every edit means
retraining, and small models hallucinate tuned facts) · **stuffing all the docs
into the 256K context** (minutes of prompt processing per question on a laptop,
and it evicts the model from RAM).

If the corpus grows 10×+ or goes per-session dynamic, swap the numpy store for
sqlite-vec/Chroma behind the same retrieval interface — nothing above it changes.

### Why hybrid retrieval (BM25 **and** embeddings)

Not garnish — load-bearing. Questions about this repo are full of exact
identifiers ("Marey", `setOverride`, "Director mode") where keyword search beats
embeddings; paraphrases ("how do I make a train wait?") go the other way. A 4B
model cannot recover from a missed retrieval, so both rankings are merged with
reciprocal-rank fusion. Two further rules, both added after live testing:

- **At most 2 snippets per source file.** One discussion-heavy document
  otherwise fills the entire context budget on its own.
- **Only the *living truth* docs are indexed** (`RAG_DOCS`). Indexing all of
  `docs/` made the model cite `docs/plans/` widget specs — *unbuilt* features —
  as though they were current behaviour, which is worse than "I don't know".

### Known limits

- Terse reference tables can rank below prose: BM25 rewards term frequency, so
  "which endpoint sets an override?" may surface a discussion of overrides over
  the README's one-line API table. Fix if it bites: heading/keyword boosting,
  tuned against a small known-answer eval set.
- The corpus is docs, not code — it answers "how do I…", not "where is the bug in…".
- The chat panel **cannot see the running simulation** (no trains, conflicts or
  current step). Giving it that context — live session state in the prompt, or
  the simulation exposed as tools — is the next real feature, and belongs with
  the mode work in [interaction-modes-brief.md](interaction-modes-brief.md).
- No token streaming: request/response only. `app/core/ws_manager.py` makes it
  feasible, but it roughly doubles the adapter surface — worth it only once a
  consumer needs it.
