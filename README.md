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

---

## Quick start

Requires **Python 3.12+** and **Node.js 20+ / npm 10+**. Use **two terminals**.

```bash
git clone -b experiment/vibecoding-playground https://github.com/danib8005/flatland_ui.git
cd flatland_ui
```

**Terminal 1 — backend (port 8000):**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend (port 4200):**

```bash
cd frontend
npm install
npm run start
```

Then open **http://localhost:4200**. Interactive API docs are at
**http://localhost:8000/docs** (Swagger UI — the authoritative endpoint list).

---

## Overview

The Flatland Dispatcher UI is a modular HMI for interactive railway dispatching
experiments. It combines:

- **Flatland-RL** — multi-agent RL environment for railway networks
- **FastAPI backend** — simulation control, conflict detection, recommendations
- **Angular frontend** (standalone components + signals) using **SBB Lyne**
- **Human-in-the-loop decision support** — scenarios, KPIs, recommendations, what-if analysis

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
