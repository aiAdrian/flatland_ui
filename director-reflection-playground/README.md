# Director Mode Reflection Playground

**Version 0.1 — fully local, no LLM.**

An interactive prototype to test a *Human–AI Co-Learning* approach for Director Mode
**before** integrating it into a real simulation and RL stack. You play through a
simulated Director-Mode session, make dispatching
decisions, see (simulated) consequences, and then run a **Reflection Session** in
which a *fake* reflection agent proposes shared learnings that you can confirm,
edit or reject.

Everything is simulated:

- No real optimiser — recommendations come from the scenario JSON files.
- No real simulation — outcomes come from the scenario JSON (seeded, reproducible).
- No LLM — the reflection agent is rule/template based, hidden behind a clean
  `ReflectionAgent` interface so it can later be swapped for a local LLM.

---

## Quick start

```bash
cd director-reflection-playground

# 1. create an isolated environment and install deps (uv shown; venv/pip works too)
uv venv .venv
uv pip install --python .venv -r requirements.txt

# 2. run the app
.venv/bin/streamlit run app.py
```

Or with plain `python`/`pip`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

### One command (recommended for demos)

```bash
./start-demo.sh              # http://localhost:8501
./start-demo.sh 8600         # a different port
./start-demo.sh 8501 --lan   # also reachable from the same network
```

Idempotent: it creates the venv and installs dependencies on first run, executes
the test suite as a self-check, then starts Streamlit. Nothing to remember before
a presentation.

There is **no hosted deployment**. Streamlit prints a "Network URL" (same LAN
only) and an "External URL" (your public IP — needs port forwarding, normally
unreachable). `--lan` binds on all interfaces for the LAN case; the app has no
authentication, so use it on a trusted network only. For a link that works from
anywhere, put a tunnel (`cloudflared`, `ngrok`) in front for the duration of the
session.

Run the tests:

```bash
.venv/bin/python -m pytest
```

### Sharing it with someone else

`START-HERE.md` is the short version for a colleague who just wants to run it
(German, matching the UI copy).

`.venv/` and the SQLite database under `data/` are not tracked, so both are rebuilt
locally on first start — a fresh clone begins with an empty session history. This folder
is self-contained: it shares no code with the Flatland UI in the repository root and
brings its own dependencies in `requirements.txt`.

---

## The flow

1. **Scenario selection** — pick one of four scenarios (and optionally a seed).
2. **Director Mode** — for each decision point you see:
   - a header with scenario, difficulty, step counter and an operational-pressure gauge
   - a small **SVG network diagram** (conflict = red, protected = green, train = blue,
     risk = orange, normal = grey)
   - the situation (critical connection, buffer, delay, ripple risk, follow-up
     conflicts, forecast confidence)
   - three (or more) **strategy cards** with the recommended one highlighted
   - a learning-adjusted recommendation notice when applicable
3. **Decision** — choose a strategy and a **confirmation mode** (derived from how you
   interact): Quick Accept, Informed Accept, Reasoned Accept (reason tags / free text),
   or Override.
4. **Outcome** — Expected vs Observed, with a "Mostly as expected / Unexpected outcome"
   status.
5. **Reflection Session** — after the last decision the app shows a session summary and
   a timeline, then the fake reflection agent walks you through **at most 3** selected
   moments and proposes **Learning Candidates** (Confirm / Edit / Reject).
6. **Session Learning Summary** — "WHAT DID WE LEARN?" with confirmed learnings,
   contradictory evidence and open questions. Optional JSONL export of the event log.

A collapsible **Debug view** (raw events, decision episodes, learnings) is available on
every screen.

---

## Project structure

```
director-reflection-playground/
  app.py                       # Streamlit UI + phase router
  director_mode.py             # DirectorSession controller (ties everything together)
  scenario_engine.py           # loads scenarios, seeded outcome selection
  event_logger.py              # structured event logging (SQLite + JSONL export)
  database.py                  # SQLite schema + connection helper
  decision_episode_builder.py  # builds & persists Decision Episodes
  pattern_analyzer.py          # rule-based user-pattern detection
  reflection_selector.py       # rule-based scoring of reflection moments
  fake_reflection_agent.py     # ReflectionAgent interface + FakeReflectionAgent
  learning_store.py            # persistence for learning candidates/learnings
  visualizations.py            # SVG network, gauges, KPI badges, pattern bars, timeline
  strategies.py                # semantic strategy IDs, confirmation modes, reason tags
  build_scenarios.py           # regenerates the scenario JSON files
  scenarios/                   # easy_morning / busy_junction / disruption_cascade / stress_test
  data/                        # SQLite DB + JSONL exports (created at runtime)
  tests/                       # unit tests for logger, pattern analyzer, selector
```

### Data model (SQLite, `data/reflection.db`)

- `sessions` — one row per playthrough
- `events` — every logged interaction (`event_id, session_id, timestamp, simulation_step, actor, event_type, payload_json`)
- `decision_episodes` — compact record per decision (`context_json, recommendation_json, user_decision_json, outcome_json, pattern_json, reflection_score`)
- `learnings` — proposed/confirmed/corrected/rejected shared learnings

---

## Adding a new scenario

Scenarios are plain JSON files in `scenarios/`. To add one, either:

**Option A — copy an existing JSON** and edit it. Each file needs:

```jsonc
{
  "scenario_id": "my_scenario",   // must equal the file name (my_scenario.json)
  "name": "My Scenario",
  "difficulty": "Medium",          // Easy | Medium | Hard | Stress
  "seed": 55,
  "description": "...",
  "decision_points": [
    {
      "step": 1,
      "time_label": "09:54",
      "operational_pressure": "LOW",   // LOW | MEDIUM | HIGH | STRESS
      "situation": {
        "description": "...",
        "affected_trains": ["train_5", "train_6"],
        "main_conflict": "...",
        "critical_connection": true,
        "connection_buffer_min": 4,
        "current_delay_min": 2,
        "ripple_risk": "low",           // low | medium | high
        "expected_follow_up_conflicts": 0,
        "forecast_confidence": "high"
      },
      "network": {
        "nodes": [{"id": "center", "x": 230, "y": 120, "label": "Center"}],
        "edges": [{"from": "west_junction", "to": "center", "status": "conflict"}],
        "conflict_node": "center",
        "critical_connection": ["train_5", "train_6"],
        "trains": [{"id": "train_5", "label": "T5", "x": 150, "y": 120}]
      },
      "strategies": ["minimize_delay", "protect_critical_connection", "stabilize_network"],
      "strategy_effects": { "minimize_delay": {"delay_impact": "+1 min", "connection_impact": "At risk", "ripple_risk": "low", "follow_up_conflict_risk": "low"} },
      "baseline_recommendation": "minimize_delay",
      "personalized_recommendation": "protect_critical_connection",
      "learning_influence": true,
      "outcomes": {
        "protect_critical_connection": {
          "expected": {"additional_delay_min": 3, "connection": "Protected", "follow_up_conflicts": 0, "network_state": "stable"},
          "observed": [{"weight": 3, "values": {"additional_delay_min": 3, "connection": "Protected", "follow_up_conflicts": 0, "network_state": "stable"}}]
        }
      }
    }
  ]
}
```

Strategy IDs must be from the semantic set defined in `strategies.py`:
`minimize_delay`, `protect_critical_connection`, `stabilize_network`,
`avoid_follow_up_conflicts`, `maintain_current_plan`.

**Option B — extend `build_scenarios.py`** with a new builder function and re-run
`python build_scenarios.py`. This keeps geometry/outcome blocks consistent.

The scenario picker discovers files automatically, ordered by difficulty.

---

## Where the local LLM plugs in later

The whole reflection dialogue depends **only** on the `ReflectionAgent` interface in
`fake_reflection_agent.py`:

```python
class ReflectionAgent(abc.ABC):
    def generate_reflection_question(self, case): ...
    def interpret_answer(self, case, answer): ...
    def propose_learning(self, case, answer): ...
```

Version 0.1 ships `FakeReflectionAgent` (rules + templates). To move to a local LLM,
implement a `LocalLLMReflectionAgent(ReflectionAgent)` with the same three methods and
change the single line in `app.py`:

```python
ss.setdefault("agent", FakeReflectionAgent())   # -> LocalLLMReflectionAgent(...)
```

No UI or data-model changes are required — the app never depends on whether the agent
is fake or LLM-backed.

---

## Known limitations (v0.1)

- **No real optimiser, simulator, MARL or Flatland** — everything is scenario-driven.
- **No LLM / RAG / vector DB** — the reflection agent is purely rule/template based.
- **Similarity & scoring are intentionally simple** — the pattern analyzer uses coarse
  buckets (critical connection, delay ≤ 3 min, ripple low/medium) and the reflection
  selector uses a fixed additive score. They demonstrate the workflow, not accuracy.
- **Learning extraction is template-based** — free text is stored verbatim and wrapped
  in a template; there is no NLP/interpretation.
- **No automatic change of KPI weights or autonomous operational decisions** — learnings
  are recorded only.
- **Patterns are per-session** — no cross-session user model is persisted yet.
- **Outcomes are seeded per session** so a run can be replayed, but they are not a real
  simulation.
- **`AppTest` note:** Streamlit's headless test harness needs widget values initialised
  before serialisation; this is a harness quirk, not an app issue. The live app handles
  widget defaults normally.
