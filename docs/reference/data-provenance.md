# Data provenance — real simulation vs mock vs demo

> What is **real Flatland simulation**, what is **mock/placeholder**, and what the
> guided **Demo** actually changes. Written because the two are easy to conflate.
> The per-widget flag lives on `WidgetMeta.dataSource` (widget-catalog.ts) and shows
> as a badge in the Widget Gallery; this doc is the grounding for those values.

## The key point: two orthogonal axes

**Axis 1 — data provenance** (a property of the *widget's data source*):

| value | meaning |
|---|---|
| `simulation` | Computed from the real Flatland run / real session data. |
| `derived` | Frontend-computed **proxy** from simulation data — not a backend KPI. |
| `mock` | Synthesized **placeholder**, not from the simulation. Mock in *every* mode. |
| `mixed` | A combination — real data + derived proxies, or real with a mock fallback. |
| `none` | Pure control / UI surface, no data source of its own. |

**Axis 2 — the guided Demo** (a property of the *session*, not the data): `demoActive`
turns on a scripted path — a **fixed-seed** environment ("Guided Demo Environment ·
fixed seed 42"), **guaranteed decision moments** (`guarantee=true` lowers the
recommendation surfacing threshold so a decision always appears), and the scripted
mode-intro sequence.

> **Demo ≠ Mock.** The guided demo runs *real* simulation on a fixed seed; it does not
> fake data. It only guarantees that decision moments surface and scripts the intro.
> Conversely, `mock` data (notifications, bundle) is mock in **all** modes — demo or not.

## Where the data actually comes from (backend `app/api/hmi.py`)

| Surface | Provenance | Grounding |
|---|---|---|
| Scenarios | **mixed** — real what-if branches via `ScenarioBuilder`, **mock fallback** when the builder can't run | `hmi.py` "scenarios (real, with mock fallback)"; `mock_generate_scenarios` fallback |
| Recommendations | **mixed** — `real_recommendations` derived from the top-scoring real scenario; the three metric chips: Delay is a real KPI, **Connection/Ripple are frontend proxies** | `hmi.py:326/368`; strategy-card proxies in `recommendations-panel.component.ts` |
| Impact | **simulation** — `active_recommender().recommend(env)` over the real env (Phase-1 proximity heuristic today) | `hmi.py get_impact` |
| Marey data | **simulation** — computed from the run | `hmi.py get_marey_data` |
| What-if compare | **simulation** — real forward-simulation of a proposed override | `whatIfOverride` → backend forward-sim |
| Situation summary / Trains / Agent Inspector / Map / Goal Achievement / Decision Log | **simulation** — real session state / captured decisions | session state, `decision-log.ts` |
| **Notifications** | **mock** — "still come from the mock (will follow in a separate step)" | `hmi.py:3, get_notifications` |
| **HMI bundle** | **mock** — "still mock, used by some UI panels" | `hmi.py:607` |
| Risk & Uncertainty | **derived** — spread band from scenario-score dispersion | widget A1 (first-cut) |
| Co-Learning Reflection | **mixed** — real interventions mirrored back + static reflection questions + frontend learning records | `co-learning-reflection`, `learning-store.service.ts` |
| Controls (Toolbar, KPI Filter, Layer Visibility, Director Directive) | **none** — pure controls | — |

Malfunctions are real; their **operational type label** ("synthetic operational type
from the AI4REALNET D4.1 taxonomy", `session.store.ts`) is a cosmetic overlay on the
real event.

## Keeping this honest

- `WidgetMeta.dataSource` is the machine-readable source of truth; this table is its
  grounding. When a mock surface is replaced by a real one (e.g. notifications), flip
  the `dataSource` and update the row here.
- The frontend `api.service.ts` still labels its HMI section "Mock-API" — a historical
  name; most of those endpoints now compute real values (see the table). Don't read the
  label as "all mock".
- The `derived` proxies (Connection/Ripple) are the Phase-2 flagship heuristics; when a
  real backend KPI replaces them, move Recommendations from `mixed` toward `simulation`.
