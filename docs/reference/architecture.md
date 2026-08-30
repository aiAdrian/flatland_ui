# Architecture

> System overview. For *why* things are shaped this way see
> [OVERVIEW.md](OVERVIEW.md); for mode behaviour see
> [interaction-modes-brief.md](interaction-modes-brief.md); for the Director
> planner internals see [director-mode.md](director-mode.md).

```
Angular frontend  ──HTTP + WebSocket──▶  FastAPI backend  ──▶  Flatland-RL env
(standalone components,                  (in-memory sessions)     (RailEnv)
 signals, SBB Lyne)
```

## Frontend (`frontend/src/app`)

| Layer | Where | Notes |
|---|---|---|
| Session state | `core/session.store.ts` | One store of signals: env state, mode, overrides, decision log, Director previews. The single place the UI reads from |
| Interaction mode | `interactionMode` signal | `recommendation \| co-learning \| director` — the only mode flag (guardrail) |
| Widget registry | `core/widgets/widget-catalog.ts` | Every panel type with `kind`, `status`, `availableModes` |
| Mode availability | `core/layout/panel-mode-availability.ts` | Which panel types a mode offers; mirrors [panel-mode-matrix.md](panel-mode-matrix.md) |
| Layout | `core/layout/`, `features/layout/` | Columns of stacked panels; the plugin host renders registered panels |
| Features | `features/<name>/` | One directory per panel/surface, standalone components |

Styling is SBB Lyne plus app tokens; no hardcoded colours in new code
([frontend-lyne-conventions.md](frontend-lyne-conventions.md)).

## Backend (`backend/app`)

| Layer | Where | Notes |
|---|---|---|
| API | `api/` | `sessions`, `overrides`, `hmi`, `policies`, `operator`, `websockets` |
| Session lifecycle | `core/session_manager.py` | **In-memory dict** — no database; a restart loses all sessions |
| Simulation control | `core/play_manager.py`, `core/scenario_runner.py` | Stepping, play/pause, scenario execution |
| Conflicts & impact | `core/conflict_detector.py`, `core/impact_analysis.py` | Decision moments and their consequences |
| Serialisation | `core/serializer.py` | Env state → frontend payload |

## The two pluggable seams

1. **Policy seam** (`app/policies/`, `registry.py`) — drives the trains.
   Heuristics (`shortest_path`, `deadlock_avoidance`, …), the Director's
   `goal_directed_policy`, and any trained RL model implement the same `Policy`
   interface. `override_policy.py` wraps the active policy and injects the
   human's per-agent overrides.
2. **Recommender seam** (`app/core/recommenders/`, `registry.py`) — suggests the
   local fix for a malfunction. Proximity-based today; a PP-replan or RL
   recommender plugs in behind the same dict contract.

Keep these apart: **policy change** is a system-wide strategy switch,
**intervention** is a local fix. See
[recommender-roadmap.md](../plans/recommender-roadmap.md).

## The Director planner

`app/policies/goal_based_policies/` is a planning stack of its own — decision
point graph, branching action space, ensemble value function, safety axis, three
search strategies (greedy / beam / MCTS) and mid-episode re-planning gated on
simulated rollouts. Documented separately in [director-mode.md](director-mode.md).

## What is deliberately not here

- **No persistence.** Sessions, trajectories and logs live in memory (backend)
  or `localStorage` (frontend). See
  [interaction-logging-plan.md](../plans/interaction-logging-plan.md).
- **No per-agent policy.** Policy is global per session; the only per-agent lever
  is an action override (interaction-modes-brief §4.4).
- **No auth, no multi-user.** Single-operator research prototype.
