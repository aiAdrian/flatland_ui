# Playground — what's new in this branch

> Branch: `experiment/vibecoding-playground` (fork `danib8005/flatland_ui`).
> This document summarises the changes made on top of `upstream/aiAdrian` so the
> work is easy to review and selectively adopt. Nothing here changes the backend
> contract — all features are frontend-first unless noted.

To see the raw diff against the original:

```bash
git fetch upstream
git diff upstream/main...experiment/vibecoding-playground
```

---

## TL;DR

The branch turns the dispatcher into a **mode-driven human-AI teaming prototype**
aligned with the three AI4REALNET collaboration modes (WP 3.1 / 3.3 / 3.4), plus
a round of UI cleanup toward the SBB design system and the InteractiveAI
event-centric direction.

The full design rationale (grounded in AI4REALNET RP2 Part B) lives in
[`docs/interaction-modes-brief.md`](docs/reference/interaction-modes-brief.md).

---

## 1. Three interaction modes (WP 3.1 / 3.3 / 3.4)

A new `InteractionMode` (`recommendation` | `co-learning` | `director`) drives the
whole UI. Switchable at runtime from the header; behaviour differs per mode.

- **Recommendation (WP 3.1):** AI surfaces a preferred option with confidence; the
  recommendations panel is shown and scenarios are ranked/badged by KPI score.
- **Co-Learning (WP 3.3):** options are presented **neutrally** — no recommended
  badge, no score reordering, recommendation panel hidden. Human interventions
  (overrides) are logged (`coLearningFeedback`) and a **reflection panel** appears
  at episode end (questions mirror AI4REALNET/T3.3-3.4-HMI).
- **Director (WP 3.4):** AI dispatches autonomously (auto-play on entering the
  mode), per-incident option prompts are suppressed, and an **"AI in control"**
  banner is shown; overrides count as manual interventions.

The single source of truth for option framing is the `optionPresentation`
computed (`recommended` | `neutral` | `none`) in `SessionStore` — every options
surface reads it, there is no parallel flag.

Key files: `core/session.store.ts`, `core/events/event-types.ts`,
`app.component.*`, `features/scenario-panel/*`, `features/co-learning-reflection/*`.

## 2. KPI filter is now wired

Previously the KPI sliders set a signal that nothing consumed. Added
`kpiWeights` (normalised) in `SessionStore` as the single consumption surface;
the scenario panel now ranks alternatives by a KPI-weighted score in
Recommendation mode (`rankedScenarios`). The concrete weight→KPI scoring is
intentionally provisional — the wiring is the point; final semantics (and any
backend scoring) are open.

Key files: `core/session.store.ts`, `features/kpi-filter/*`,
`features/scenario-panel/*`.

## 3. Header redesign (SBB app-shell direction)

- AI4REALNET logo + title on the left.
- **Mode switcher** as an sbb.ch-style dropdown (`sbb-menu`) showing the current
  mode with a colour dot; WP labels in the menu.
- **☰ app menu** holds Session Settings, Scenarios / Policy, and Reset — these
  moved out of the toolbar. The toolbar now only carries simulation controls
  (Play/Pause, speed, step, policy).
- The old top **toggle switches** for Settings / Scenarios (semantically wrong —
  they opened dialogs) were replaced by real buttons / menu entries.

Key files: `app.component.*`, `features/toolbar/*`, `main.ts` (menu imports).

## 4. Event feed (toward InteractiveAI)

The notifications panel became a leading **Event Feed**: header with
error/warning/total **count badges**, criticality colour markers (replacing the
emoji icons), clearer hierarchy. Lays groundwork for the event-centric layout.

Key files: `features/notifications-panel/*`.

## 5. Three-zone information architecture (Hypervision direction)

The layout was restructured into three clear zones, following the AI4REALNET
Hypervision / InteractiveAI pattern (situation → visualisation → intervention):

- **LEFT — situation:** a new `situation-summary` (Hypervision synthesis:
  arrived/total, active, delayed, malfunctions), the Event Feed, and the Agents
  list — Event Feed and Agents split 50/50 below the summary.
- **MIDDLE — visualisation:** map controls bar (View + Layer chips) + map/marey,
  plus **agent details as a floating map-corner overlay** (key facts +
  next-decision action buttons). The old side panel of numbers is gone — details
  now have spatial context where the action happens.
- **RIGHT — intervention:** all leverage grouped here — Policies (scenario
  comparison), Recommendations (WP 3.1 only), then Options (KPI weights). The KPI
  filter moved here from the left, fixing the earlier left/right inconsistency
  (it is the "objective" lever, alongside the policy and per-agent levers).

The agent-inspector was rewritten from a hover-popover into the map overlay; its
~500-line `!important`-heavy SCSS is now ~90 clean lines.

Key files: `app.component.*`, `features/situation-summary/*`,
`features/agent-inspector/*`, `features/layer-visibility/*`,
`features/view-toggle/*`.

## 6. Relationship to Adrian's Designer prompt

Adrian's `aiAdrian/Designer` branch specifies a **configurable layout *designer***
(drag-and-drop panels, EventBus/SharedState, persistence). This branch ships a
**fixed** three-zone layout instead — intended to become one `LayoutDefinition`
**preset** inside that future system. The feature work (modes, KPI, Hypervision,
reflection) is independent of the layout system and can be adopted on its own.
See [`docs/layout-preset-and-designer-alignment.md`](docs/archive/layout-preset-and-designer-alignment.md)
for a panel-by-panel mapping and a feature-layer vs. layout-layer split.

## 7. Cleanup

- Removed ~180 lines of dead/duplicated settings + policy dialog markup in
  `app.component.html` (the welcome `@else` branches were unreachable).
- Replaced emoji icons (KPI filter, notifications) with SBB-consistent markers.

---

## Status / known limitations

- All AI in every mode still runs the existing **heuristic policies**. Real RL
  agents (e.g. the PPO agent from AI4REALNET/T3.4-with-HMI, or CBS/PP from
  Tokener) are the intended next step via the existing `Policy` registry — see
  the brief.
- Co-Learning feedback and reflection answers are **client-side only** (no
  persistence layer yet).
- KPI weights affect scenario ordering, not backend scoring.
- Not yet implemented from the brief: reflection "when calm" (§3.2), Director
  pre-run directive + goal-achievement view (§3.4), what-if "actual vs
  alternative" compare (§3.3).

## Build & run

Unchanged from the main README — `npm install` + `ng serve` in `frontend/`,
FastAPI backend in `backend/`.
