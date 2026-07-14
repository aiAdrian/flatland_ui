# Flatland Dispatcher — A Human-AI Teaming Playground (UI)

Human-in-the-loop train dispatching based on the [Flatland Reinforcement Learning environment](https://www.flatland-association.org/projects), integrated into the [AI4REALNET](https://ai4realnet.eu/) research project.

The frontend follows the official [SBB Design System](https://digital.sbb.ch/en/) and uses [SBB Lyne Web Components](https://lyne-angular.app.sbb.ch/).

![Guided demo: Recommendation → Co-Learning → Director](docs/media/guided-demo.gif)

> Guided demo walkthrough. For the full-quality clip see [guided-demo.mp4](docs/media/guided-demo.mp4).

> **Playground branch (`experiment/vibecoding-playground`):** this fork makes the
> three AI4REALNET collaboration modes behaviourally distinct (Recommendation /
> Co-Learning / Director), adds a guided demo flow, a live impact panel, a wired
> KPI filter, and a post-session survey. See **[PLAYGROUND.md](PLAYGROUND.md)**
> for a review-friendly summary of what changed and why.

## Video gallery - current version 08.07.2026

[mov_001.webm](https://github.com/user-attachments/assets/d68ee248-5965-4d58-acfc-5f9e1f1e80ac)

[mov_002.webm](https://github.com/user-attachments/assets/992810c6-c38a-4bea-8fe9-2bb1b5334add)

[mov_003.webm](https://github.com/user-attachments/assets/81a2fb58-4d2b-4465-ae56-f6e3886f85c8)

[mov_004.webm](https://github.com/user-attachments/assets/f4a610f7-6a46-439e-9d30-428be260d66c)

[mov_005.webm](https://github.com/user-attachments/assets/1663d39d-f1a1-4e01-9ae8-d629696ab905)

[mov_006.webm](https://github.com/user-attachments/assets/4ec3b311-e630-4c17-a37b-679a7871a703)


---

## Quick start

Prerequisites:

| Need | Version | Notes |
|---|---|---|
| **Python** | 3.12+ | |
| **Node.js** | **22.22.3+**, 24.15+, or 26+ | Angular 22 rejects older Node — including all of Node 20 — and odd-numbered releases (21/23/25) are not supported. |
| **[Ollama](https://ollama.com)** | any current | Serves the local model behind the LLM Chat panel. |

Budget ~**4 GB of disk** for the two models and ideally **8 GB+ of free RAM**; on a
smaller machine use `qwen3.5:2b` (see [llm-setup.md](docs/reference/llm-setup.md)).

### 1. Clone

```bash
git clone -b experiment/vibecoding-playground https://github.com/danib8005/flatland_ui.git
cd flatland_ui
```

### 2. Install Ollama

It runs natively on all three OSes and picks up your GPU automatically — no
configuration, no API key, and nothing leaves your machine.

```bash
brew install ollama                  # macOS  (or the app: https://ollama.com/download)
winget install Ollama.Ollama         # Windows (no WSL needed)
curl -fsSL https://ollama.com/install.sh | sh   # Linux
```

> **Do not run Ollama in Docker on macOS** — Docker Desktop cannot reach the Apple
> GPU, so the model falls back to CPU and is unusably slow. Details in
> [docs/reference/llm-setup.md](docs/reference/llm-setup.md).

### 3. Install dependencies (once)

```bash
cd backend && python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt && cd ..

cd frontend && npm install && cd ..

./scripts/setup-llm.sh                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File scripts\setup-llm.ps1  # Windows
```

The last step downloads the two models — `qwen3.5:4b` (3.4 GB, the chat model) and
`nomic-embed-text` (274 MB, used to search the docs) — and smoke-tests the chat model.

### 4. Run

One command starts the model server, the backend and the frontend together, and
stops them all again on **Ctrl-C**:

```bash
./scripts/start.sh                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File scripts\start.ps1  # Windows
```

It only stops what it started: an Ollama already running as a system service
(brew, menu-bar/tray app, systemd) is left alone, because it may be serving other
things.

Then open **http://localhost:4200**. Interactive API docs are at
**http://localhost:8000/docs** (Swagger UI — the authoritative endpoint list).

### Or by hand, in two terminals

```bash
# Terminal 1 — backend (port 8000)
cd backend && source .venv/bin/activate      # Windows: .venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (port 4200)
cd frontend && npm run start
```

This assumes Ollama is already serving (`ollama serve`, or a system service).

### Running the tests

Backend tests need the dev dependencies (pytest, ruff — `requirements.txt` alone is
not enough). No model or API key is required: the LLM tests use a fake provider, and
the one live test skips itself when nothing is running.

```bash
cd backend
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                               # ruff check app/ tests/   for linting

cd ../frontend
npm test -- --watch=false            # ChromeHeadless
```

---

## Overview

The Flatland Dispatcher UI is a modular HMI for interactive railway dispatching
experiments. It combines:

- **Flatland-RL** — multi-agent RL environment for railway networks
- **FastAPI backend** — simulation control, conflict detection, recommendations
- **Angular frontend** (standalone components + signals) using **SBB Lyne**
- **Human-in-the-loop decision support** — scenarios, KPIs, recommendations, what-if analysis
- **LLM seam + docs Q&A** — an **LLM Chat** panel that answers questions about the
  project, grounded in these docs and citing them. It runs on a local model by
  default (no API key, nothing leaves the machine); pointing it at Claude or a
  cloud endpoint is one `.env` variable. See
  [docs/reference/llm-setup.md](docs/reference/llm-setup.md).

### Three collaboration modes

The core of this fork is making the three AI4REALNET interaction modes
behaviourally distinct and switchable from the header:

| Mode | Work package | Behaviour |
|------|--------------|-----------|
| **Recommendation** | WP 3.1 | AI suggests **with** a ranked recommendation; the human decides. |
| **Co-Learning** | WP 3.3 | AI offers **neutral** options; the human decides, reflects, and runs what-ifs. |
| **Director** | WP 3.4 | AI runs autonomously on high-level directives; the human supervises (adjustable autonomy). |

A **guided demo** walks through all three modes on the same conflict-rich
environment. See [docs/interaction-modes-brief.md](docs/reference/interaction-modes-brief.md)
for the authoritative spec and [docs/mode-guide.md](docs/reference/mode-guide.md) for a
quick tour.

---

## Architecture

3-column HMI layout:

- **LEFT** — Situation summary, Notifications, Trains (agent list)
- **MIDDLE** — Director directive bar, view toggle, Layer visibility, Track Layout (map) + Agent inspector, Graphic Timetable (Marey)
- **RIGHT** — Goal achievement (Director), Impact panel, Scenarios, Recommendations, KPI filter, Co-Learning reflection

**Backend:** FastAPI + Flatland-RL
**Frontend:** Angular (standalone components, signals) + SBB Lyne Elements

A more detailed write-up is in [docs/architecture.md](docs/reference/architecture.md).
Project conventions and guardrails live in [CLAUDE.md](CLAUDE.md).

---

## Backend — API

The backend exposes a session-based REST API plus a WebSocket for live updates.
The full, always-current list is at **http://localhost:8000/docs**; the most-used
endpoints are:

```
POST   /session                              # Create new session
GET    /session/{id}/state                   # Current state
POST   /session/{id}/step                    # Execute one step
POST   /session/{id}/reset                   # Replay identical scenario (same rail/schedule/malfunctions)
DELETE /session/{id}                         # Delete session
POST   /session/{id}/agent/{handle}/override # Set action override at a decision cell
DELETE /session/{id}/agent/{handle}/override # Remove override
POST   /session/{id}/policy                  # Set the global session policy
POST   /session/{id}/play                    # Start auto-play
POST   /session/{id}/pause                   # Pause auto-play

GET    /policies                             # Available policies (heuristics / planners)
GET    /session/{id}/scenario-policies       # What-if scenario branches
GET    /session/{id}/hmi                     # HMI bundle (notifications, scenarios, recommendations, impact)
GET    /session/{id}/hmi/impact              # Live impact analysis (blocked trains, severities)
GET    /session/{id}/hmi/marey-data          # Time-distance (Marey) data

WS     /ws/session/{id}                      # Live state stream
```

> Notifications, recommendations, and impact are **computed** from the live
> simulation (conflict detection, proximity recommender, impact analysis) —
> not seeded mock data.

### Smoke test (curl)

```bash
# Create a session and capture its id
SID=$(curl -sL -X POST http://localhost:8000/session \
  -H "Content-Type: application/json" \
  -d '{"width":50,"height":20,"number_of_agents":3}' | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')

curl -s "http://localhost:8000/session/$SID/state" | head -c 500
curl -s "http://localhost:8000/session/$SID/hmi"
```

---

## Deployment

The root [`Dockerfile`](Dockerfile) builds the Angular frontend and serves it
same-origin from the FastAPI backend (`backend/app/main.py` mounts the built
UI with an SPA fallback once `backend/static` exists) — one container, one
URL, no CORS configuration needed.

```bash
docker build -t flatland-dispatcher .
docker run -p 8000:8000 flatland-dispatcher
# → http://localhost:8000
```

To host it online, point any Dockerfile-based platform at the repo root:

- **Render** — New → Web Service → connect the repo, it auto-detects the
  Dockerfile. Free tier available.
- **Fly.io** — `fly launch` from the repo root, then `fly deploy`.
- **Any VPS** — `docker build` + `docker run` (above) behind your reverse
  proxy of choice for TLS.

No environment variables are required for a same-origin deploy. `CORS_ORIGINS`
(see `backend/app/config.py`) only matters if you instead host the frontend
and backend on separate domains — set it to the frontend's origin in that case.

---

## Troubleshooting

**Backend does not start** — verify Flatland is installed in the active venv:

```bash
cd backend && source .venv/bin/activate
python -c "import flatland; print(flatland.__version__)"
# If ModuleNotFoundError: pip install -r requirements.txt
```

**Frontend does not compile** — clear and reinstall:

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install && npm run start
```

---

## Recording the demo video

The `preview.webm` at the top of this README is hosted as a GitHub asset (not a
file in the repo). To replace it:

1. **Record the screen.** On macOS, `Cmd+Shift+5` → record a region (or the
   browser window) → save as `.mov`. Run the guided demo so the clip shows all
   three modes. Keep it ~30–60 s.
2. **Trim / convert** (optional, keeps the file small):
   ```bash
   ffmpeg -i demo.mov -vf "scale=1280:-2" -c:v libvpx-vp9 -b:v 1M -an preview.webm
   ```
   (`-an` drops audio; GitHub plays `.webm`/`.mp4` inline. `.mp4` works too.)
3. **Upload to GitHub** so it gets a hosted asset URL: open a new issue or a PR
   comment, **drag the file into the text box**, wait for the upload, then copy
   the generated `https://github.com/user-attachments/assets/...` URL. (You don't
   have to submit the issue/comment — it's just the upload mechanism.)
4. **Replace the link** on line 8 of this README with the new URL. GitHub renders
   a bare `https://…/assets/…` line as an inline video player.

> Tip: keep the file under ~10 MB so it loads fast. 1280px-wide VP9 at ~1 Mbps is
> plenty for a UI walkthrough.

---

## References

- **Flatland-RL** — multi-agent railway RL environment: https://github.com/flatland-association/flatland-rl
- **SBB Design System** — https://digital.sbb.ch/en/ · **SBB Lyne** — https://lyne-angular.app.sbb.ch/ · [Lyne on GitHub](https://github.com/sbb-design-systems/lyne-components)
- **AI4REALNET** (EU Horizon) — https://ai4realnet.eu

The Flatland Dispatcher UI serves as a research tool for interactive RL
experiments, a demonstrator for human–AI teaming, and a modular HMI for railway
dispatching prototypes.
