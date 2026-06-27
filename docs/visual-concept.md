# Visual concept & naming — the Flatland Dispatcher HMI

> One shared vocabulary for our interface. Today the same surface has several
> names (code vs. UI label vs. conversation), which makes design discussion
> fuzzy. This doc fixes **canonical names**, their **role**, their **zone**, and
> their **InteractiveAI / Hypervision lineage**. Use these names everywhere:
> code, UI labels, docs, and mockups.

---

## 1. The three zones (information architecture)

The layout follows the AI4REALNET **Hypervision / InteractiveAI** pattern:
**situation → visualisation → intervention**. Read left-to-right, it mirrors the
dispatcher's loop: *understand the situation → see it in space/time → act on it*.

```
┌──────────────┬───────────────────────────┬──────────────┐
│  SITUATION   │       VISUALISATION       │ INTERVENTION │
│   (left)     │         (middle)          │   (right)    │
│  "what is    │   "where / when is it"    │  "what do I  │
│   going on"  │                           │   do about   │
│              │                           │   it"        │
└──────────────┴───────────────────────────┴──────────────┘
```

---

## 2. Canonical surface names

Each surface gets ONE canonical name. Where the current UI label or code name
differs, that is flagged as a rename to converge on.

### Situation zone (left)

| Canonical name | Code component | Current UI label | Role | InteractiveAI analogue |
|---|---|---|---|---|
| **Situation Summary** | `situation-summary` | "Situation" | Synthesised state: arrived/total, active, delayed, malfunctions | Hypervision synthesis |
| **Event Feed** | `notifications-panel` | "Event Feed" | Chronological list of incidents (criticality markers, count badges) | Event/card feed |
| **Train List** | `agents-panel` | "Agents" | All trains grouped by status (moving / waiting / done) | — (domain list) |

### Visualisation zone (middle)

| Canonical name | Code component | Current UI label | Role | InteractiveAI analogue |
|---|---|---|---|---|
| **Network Map** | `flatland-map` / `track-layout` | (map) | The live Flatland grid; trains, routes, conflicts in space | Geographic/topology view |
| **Time–Distance Chart** | `marey-chart` / `graphic-timetable` | (Marey) | Train trajectories over time; what-if branch preview | Timeline |
| **Train Detail Overlay** | `agent-inspector` | (map-corner overlay) | Selected train's key facts + next-decision actions, in spatial context | Detail-in-context template |
| **View Toggle / Layer Chips** | `view-toggle`, `layer-visibility` | "Layers" | Switch Map/Marey; toggle overlays (grid, decisions, trajectory, cell info, switches, signals) | Layer controls |

### Intervention zone (right)

| Canonical name | Code component | Current UI label | Role | InteractiveAI analogue |
|---|---|---|---|---|
| **Conflict Panel** | `impact-panel` | "Disruption Conflicts" | Trains blocked by another train's malfunction + per-train action (hold / reroute); drives auto-pause + decision countdown | Incident → recommended action |
| **Recommendation Panel** | `recommendations-panel` | "AI Recommendations" | Ranked policy-switch suggestions (Recommendation mode); hover previews the branch | Recommendation service |
| **Policy / Scenario Panel** | `scenario-panel` | (Policies / Scenarios) | Compare policy branches (what-if), confirm one as active | — (decision support) |
| **KPI Filter** | `kpi-filter` | "KPI Filter" | The objective lever: weight time / energy / routing → feeds scoring | — (objective weighting) |
| **Goal Achievement** | `goal-achievement` | "Goal Achievement" | Director-mode live KPI tracking against directive | — (supervision dashboard) |
| **Reflection Panel** | `co-learning-reflection` | "Co-Learning Reflection" | Post-incident mirroring + Socratic prompts (Co-Learning) | Capitalization / feedback |

---

## 3. Renames to converge on

To remove the current ambiguity, standardise on the canonical names above. The
most important fixes:

- `impact-panel` / "Disruption Conflicts" → **Conflict Panel** (one name).
- `agents-panel` / "Agents" → **Train List** (it's trains, not abstract agents,
  in the dispatcher's language).
- Keep **Event Feed** (already consistent) — but note it is still backed by the
  `notifications-panel` code name; align when touched.
- `agent-inspector` → **Train Detail Overlay** (it is no longer an inspector
  popover; it's the in-context overlay).

> These are presentation/vocabulary renames — no behaviour change. Apply
> opportunistically when a component is touched, not as a big-bang refactor.

---

## 4. Cross-surface interaction concepts

These behaviours span multiple surfaces and need shared names too:

- **Selection** — one train selected at a time (`selectedHandle`); highlighted on
  Map, Marey, Train List, and shown in the Train Detail Overlay.
- **Hover-link** — hovering a train anywhere highlights it everywhere
  (`notificationHoverHandles` / agent hover). One visual language across views.
- **Branch Preview** — hovering a Recommendation or Policy/Scenario row previews
  that alternative trajectory on Map + Time–Distance (`previewScenarioId`).
- **Decision Moment** — a conflict that pauses the run (auto-pause, configurable)
  and opens a **Decision Countdown**; the system applies a safe default if it
  expires. Lives on the Conflict Panel today; the Event-Detail-Card concept
  (§6) would move it onto the event itself.

---

## 5. Mode-aware framing (cross-cutting)

The three interaction modes are not separate screens — they **re-frame the same
surfaces** (`optionPresentation`):

| Surface | Recommendation (WP 3.1) | Co-Learning (WP 3.3) | Director (WP 3.4) |
|---|---|---|---|
| Conflict / Recommendation | ranked suggestion + confidence, Accept | neutral, unranked options | AI acts; read-only, intervene by exception |
| Reflection Panel | — | active (mirroring + Socratic) | — |
| Goal Achievement | — | — | active (supervision) |
| Auto-pause | yes | yes | no |

---

## 6. Event vocabulary (target state — see event-detail-card)

Toward InteractiveAI on the interaction level, incidents become **first-class
events** with a lifecycle, surfaced as cards in the Event Feed and expandable
into an **Event Detail Card** (context + embedded recommendation + accept/reject):

- **Event** — an incident with stable `id_event`, `criticality`, `data`.
- **Lifecycle** — `detected → acknowledged → decision → resolved → logged`.
- **Feedback** — accept / reject / override + reflection, attached to the event id
  (the study log and the co-learning loop both read from it).

See the Event Detail Card mockup/flow (to be captured in `docs/event-detail-card.md`).

---

## 7. Open naming decisions

1. **Conflict Panel vs. Event Detail Card** — do they merge? If incidents become
   events with inline detail+action, the standalone Conflict Panel may fold into
   the Event Feed (one place, not two).
2. **"Train" vs. "Agent"** — commit to **Train** in all operator-facing labels;
   keep "agent/handle" only in code/API.
3. **Zone labels in the UI** — do we ever show the zone names (situation /
   visualisation / intervention) to the user, or are they internal only?
