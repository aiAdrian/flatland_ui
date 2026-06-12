# Flatland Dispatcher UI

Human-in-the-Loop train dispatching based on Flatland-RL.

## Architecture

3-column HMI (Phase A–D during migration):

- LEFT (280px): Notifications + Layer Visibility + Sidebar
- MIDDLE (1fr): Track Layout (Map) + Graphic Timetable (Marey) + Simulation Slider
- RIGHT (320px): Scenarios + KPI Filter + Recommendations + Inspector

Backend: FastAPI + Flatland-RL  
Frontend: Angular 18 (standalone components, signals) + SBB Lyne Elements

## Requirements

- Python 3.12+
- Node.js 20+ / npm 10+

## Backend – Setup & Start

```bash
cd ~/workspace/ai4realnet/flatland_ui/backend
```

### First time: virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Start (auto-reload on code changes)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend runs on http://localhost:8000:

- Interactive API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Important Endpoints

POST   /session                              # Create new session  
GET    /session/{id}/state                   # Current state  
POST   /session/{id}/step                    # Execute step  
POST   /session/{id}/play                    # Start auto-play  
POST   /session/{id}/pause                   # Pause  
POST   /session/{id}/reset                   # Reset  
POST   /session/{id}/agent/{handle}/override # Set action override  
DELETE /session/{id}/agent/{handle}/override # Remove override  

### HMI Mock Data (procedural via seed)

GET    /session/{id}/hmi/notifications  
GET    /session/{id}/hmi/scenarios  
GET    /session/{id}/hmi/recommendations  
GET    /session/{id}/hmi                      # All in one bundle  

### WebSocket (live state updates)

WS     /ws/session/{id}

## Frontend – Setup & Start

```bash
cd ~/workspace/ai4realnet/flatland_ui/frontend
```

### First time

```bash
npm install
```

### Start (Hot Module Reload)

```bash
npm run start
```

Frontend runs on http://localhost:4200.

## Quick Start (two terminals)

### Terminal 1 – Backend

```bash
cd ~/workspace/ai4realnet/flatland_ui/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Terminal 2 – Frontend

```bash
cd ~/workspace/ai4realnet/flatland_ui/frontend
npm run start
```

Browser: http://localhost:4200

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

### HMI bundle

```bash
curl -s http://localhost:8000/session/<ID>/hmi
```

## Troubleshooting

### Backend does not start

```bash
cd ~/workspace/ai4realnet/flatland_ui/backend
source .venv/bin/activate
python -c "import flatland; print(flatland.__version__)"
```

If `ModuleNotFoundError`: run `pip install -r requirements.txt`.

### Frontend does not compile

```bash
cd ~/workspace/ai4realnet/flatland_ui/frontend
rm -rf node_modules package-lock.json
npm install
npm run start
```

Pan via mouse drag + 5 pan buttons.
