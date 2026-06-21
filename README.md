# Flatland Dispatcher- A Human-AI Teaming Playground (UI)


Human-in-the-loop train dispatching based on the [Flatland Reinforcement Learning environment](https://www.flatland-association.org/projects), integrated into the [AI4REALNET](https://ai4realnet.eu/) research project.  

Frontend follows the official [SBB Design System](https://digital.sbb.ch/en/) and uses [SBB Lyne Web Components](https://lyne-angular.app.sbb.ch/).

[preview.webm](https://github.com/user-attachments/assets/0162eea7-570a-4d50-a979-b0b2b84d3707)

> **Playground branch (`experiment/vibecoding-playground`):** this fork adds the
> three AI4REALNET collaboration modes (Recommendation / Co-Learning / Director),
> a wired KPI filter, an SBB-style header with a mode switcher, an event feed, and
> UI cleanups. See **[PLAYGROUND.md](PLAYGROUND.md)** for a full, review-friendly
> summary of what changed and why.

---

## Quick start

Requires Python 3.12+ and Node.js 20+ / npm 10+. Use **two terminals**.

```bash
# 0) clone the playground branch
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

Then open **http://localhost:4200**. The backend API docs are at
http://localhost:8000/docs. Detailed setup and endpoints are below.

---

## Overview

The Flatland Dispatcher UI is a modular HMI for interactive railway dispatching experiments.  
It combines:

- **Flatland-RL** (multi-agent RL environment for railway networks)  
- **FastAPI backend** for simulation control  
- **Angular 18 frontend** using **SBB Lyne** components  
- **Human-in-the-loop decision support** (scenarios, KPIs, recommendations)

---

## Architecture

3-column HMI layout (Phase A–D during migration):

- **LEFT (280px)** — Notifications, Layer Visibility, KPI Filter,
- **MIDDLE (1fr)** — Simulation Slider and Control, Track Layout (Map), Graphic Timetable (Marey), 
- **RIGHT (320px)** — Scenarios, Recommendations, Agents Sidebar, Agent Inspector  

**Backend:** FastAPI + Flatland-RL  
**Frontend:** Angular 18 (standalone components, signals) + SBB Lyne Elements

---

## Requirements

- Python **3.12+**  
- Node.js **20+** / npm **10+**

---

## Backend — Setup & Start

```bash
cd ~/workspace/ai4realnet/flatland_ui/backend
```

### First-time setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Start backend (auto-reload)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend available at:

- API Docs: http://localhost:8000/docs  
- Health Check: http://localhost:8000/health  

### Important Endpoints

```
POST   /session                              # Create new session
GET    /session/{id}/state                   # Current state
POST   /session/{id}/step                    # Execute step
POST   /session/{id}/play                    # Start auto-play
POST   /session/{id}/pause                   # Pause
POST   /session/{id}/reset                   # Reset
POST   /session/{id}/agent/{handle}/override # Set action override
DELETE /session/{id}/agent/{handle}/override # Remove override
```

### HMI Mock Data (procedural via seed)

```
GET    /session/{id}/hmi/notifications
GET    /session/{id}/hmi/scenarios
GET    /session/{id}/hmi/recommendations
GET    /session/{id}/hmi                      # All in one bundle
```

### WebSocket (live updates)

```
WS     /ws/session/{id}
```

---

## Frontend — Setup & Start

```bash
cd ~/workspace/ai4realnet/flatland_ui/frontend
```

### First-time setup

```bash
npm install
```

### Start frontend (HMR)

```bash
npm run start
```

Frontend available at:  
http://localhost:4200

---

## Quickstart (two terminals)

### Terminal 1 — Backend

```bash
cd ~/workspace/ai4realnet/flatland_ui/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Terminal 2 — Frontend

```bash
cd ~/workspace/ai4realnet/flatland_ui/frontend
npm run start
```

Browser: http://localhost:4200

---

## Smoke Test (curl)

### Create session

```bash
curl -sL -X POST http://localhost:8000/session \
  -H "Content-Type: application/json" \
  -d '{"width":50,"height":20,"number_of_agents":3}'
```

### Get state

```bash
curl -s http://localhost:8000/session/<ID>/state | head -c 500
```

### Get HMI bundle

```bash
curl -s http://localhost:8000/session/<ID>/hmi
```

---

## Troubleshooting

### Backend does not start

```bash
cd ~/workspace/ai4realnet/flatland_ui/backend
source .venv/bin/activate
python -c "import flatland; print(flatland.__version__)"
```

If `ModuleNotFoundError`:  
`pip install -r requirements.txt`

### Frontend does not compile

```bash
cd ~/workspace/ai4realnet/flatland_ui/frontend
rm -rf node_modules package-lock.json
npm install
npm run start
```

---

## References

### SBB Design System & SBB Lyne

The UI follows the official SBB Design System and uses SBB Lyne Web Components:

- SBB Design System: https://digital.sbb.ch/en/
- SBB Lyne Web Components: https://lyne-angular.app.sbb.ch/)
- Lyne GitHub: https://github.com/sbb-design-systems/lyne-components  

Benefits:

- WCAG 2.1 AA accessibility  
- Corporate Identity compliance  
- Consistent interaction patterns  
- Native integration with Angular standalone components  

### Flatland (Reinforcement Learning Environment)

Flatland is a multi-agent RL environment for railway dispatching:

- GitHub:  https://github.com/flatland-association/flatland-rl
- Documentation: https://flatland-association.github.io/flatland-book/challenges/ecml2026.html
Features:

- Grid-based railway topology  
- Multi-agent pathfinding  
- Deadlocks, conflicts, stochastic delays  
- Step-based simulation API  

### AI4REALNET (EU Horizon Project)

The project focuses on applying AI to real-world networked systems:

- Project Page: https://ai4realnet.eu  

Research topics:

- Human-in-the-loop dispatching  
- Multi-agent reinforcement learning  
- Real-time decision support  
- Explainable AI for railway operations  

The Flatland Dispatcher UI serves as:

- Research tool for interactive RL experiments  
- Demonstrator for human–AI teaming  
- Modular HMI for railway dispatching prototypes  

---

Pan via mouse drag + 5 pan buttons.
