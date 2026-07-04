# Panel × Interaction-Mode Matrix

**Status:** first draft / working reference.
**Companion of:** [interaction-modes-brief.md](interaction-modes-brief.md) (authoritative
mode spec) and [mode-scoped-layouts-plan.md](../plans/mode-scoped-layouts-plan.md) (how
per-mode layouts get resolved).

This file answers two questions for every panel:

1. **Availability** — does the panel appear at all in a given mode?
2. **Behaviour** — if it appears, how does the *same* panel behave differently
   per mode?

It is grounded in the current code, not aspiration. The mode selectors that drive
this today live in `session.store.ts`:

| Selector | Meaning |
|----------|---------|
| `interactionMode()` | `'recommendation' \| 'co-learning' \| 'director'` — the single source of truth |
| `optionPresentation()` | `recommendation → 'recommended'`, `co-learning → 'neutral'`, `director → 'none'` |
| `aiInControl()` / `isCoLearning()` | `=== 'director'` / `=== 'co-learning'` |

Legend: **●** available · **○** not shown · **◐** available but secondary/collapsed.

## Availability

| Panel (`type`) | Recommendation | Co-Learning | Director |
|----------------|:--------------:|:-----------:|:--------:|
| `situation-summary` | ● | ● | ● |
| `notifications` | ● | ● | ● |
| `agents` (`agents-list`) | ● | ● | ● |
| `flatland-map` | ● | ● | ● |
| `graphic-timetable` (`marey`) | ● | ● | ● |
| `agent-inspector` | ● | ● | ● |
| `impact` | ● | ● | ◐ overview only |
| `risk-uncertainty` | ● | ● | ● read-only |
| `scenario` | ◐ collapsed | ◐ collapsed | ● expanded |
| `kpi-filter` | ◐ | ◐ | ● expanded |
| `recommendations` | ● | ○ | ○ |
| `co-learning-reflection` | ○ | ● | ○ |
| `goal-achievement` | ○ | ○ | ● |
| `director-directive` | ○ | ○ | ● |

## Behaviour per mode

Only panels whose behaviour actually branches on the mode are listed; the rest
render identically everywhere.

### `impact`
- **Recommendation** — surfaces the AI's recommended action; keeps the gentle
  global pause + decision countdown so the human decides *with* a suggestion.
  (`impact-panel.component.ts`)
- **Co-Learning** — affected trains shown **neutrally**; the human inspects and
  decides. Empty-state handled explicitly (`isCoLearning() && items().length === 0`).
- **Director** — **overview only**; per-decision hooks are suppressed
  (`interactionMode() !== 'director'`) because the AI handles it.

### `risk-uncertainty` (Tile A1 — Trust)
- **Recommendation** — reliability shown **with** the ranked recommendation:
  `confidence` from `store.recommendations()` + a spread band derived from
  `store.scenarios()` score dispersion. Low-and-wide → amber + invites scrutiny.
- **Co-Learning** — uncertainty shown **neutrally per option** (Evaluative AI):
  each scenario gets an "evidence for / against / mixed" tag from its score
  position; no single trust-score winner.
- **Director** — **aggregate** policy reliability (mean confidence), read-only;
  a low-confidence aggregate surfaces as the **exception trigger** for
  adjustable autonomy. No accept/override instrumentation (supervisory).
- Availability is **all modes** (omitted from `PANEL_MODE_AVAILABILITY` = 'all');
  only the *behaviour* branches, inside `risk-uncertainty-panel.component.ts`.
  First cut is frontend-only and **not calibrated** — the label reads
  "model-reported confidence" until the backend UQ/calibration extension lands
  (spec §4). Not in the hardcoded default layout; available via the designer
  palette.

### `scenario`
- **Recommendation** — alternatives **ranked by the operator's KPI priorities**
  (`optionPresentation() === 'recommended'`).
- **Co-Learning** — options presented **neutrally**, no KPI-score ranking.
- **Director** — neutral framing too, and the panel is **expanded by default**
  (policy is the directive); collapsed by default in Rec/Co-Learning.

### `kpi-filter`
- **Director** — the KPI filter is the **primary directive lever**, so it is
  **expanded** on entering Director.
- **Recommendation / Co-Learning** — available but secondary.

### `recommendations` / `co-learning-reflection` / `goal-achievement` / `director-directive`
Pure availability panels — each is the signature surface of exactly one mode
(see the availability table). They do not need internal mode branching.

## Design guidance (from this matrix)

- **Availability** belongs in the layout/registry layer (a declarative
  `availableModes` on the panel *type* — see the sketch below), resolved once by
  the mode-scoped-layout resolver — **not** as scattered `@if isCoLearning()` in
  `app.component.html`, which is where most of this lives today.
- **Behaviour** stays inside a **single mode-aware component** per panel (read
  `store.interactionMode()`, branch internally) — not separate registered panel
  types per mode, which would explode the designer catalogue.
- Reserve fully separate components for panels whose modes share almost nothing,
  and even then prefer a shared shell + mode-specific sub-views.

## Sketch: `availableModes` on the panel type

Availability is a property of the panel **type** (its catalogue entry), not of a
placed instance, so it belongs on `PanelDefinition`. Proposed optional,
non-breaking field:

```ts
// core/layout/models/layout.models.ts
export interface PanelDefinition {
  // …existing fields…
  /**
   * Modes in which this panel type is offered. Omitted / 'all' = every mode.
   * Consumed by the mode-scoped-layout resolver to decide availability;
   * per-mode *behaviour* is handled inside the component, not here.
   */
  availableModes?: InteractionMode[] | 'all';
}
```

Example catalogue values implied by the table above:

| `type` | `availableModes` |
|--------|------------------|
| `recommendations` | `['recommendation']` |
| `co-learning-reflection` | `['co-learning']` |
| `goal-achievement` | `['director']` |
| `director-directive` | `['director']` |
| everything else | `'all'` |

This is a sketch: the field is declared but not yet wired into the resolver. Next
step would be to have the mode-scoped-layout resolver filter the catalogue by
`availableModes` when building a mode's default layout.
