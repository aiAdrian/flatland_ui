# Mode layouts — three zones, one variable

> **Status:** plan, ready to implement. Dated 2026-09-02.
> **Decided in this round (danib):** events are **re-drawn per mode**, the right
> column is **not** segmented in Recommendation, and left-zone panels may
> **navigate but not act**.
> **Companions:** [interaction-modes-brief.md](../reference/interaction-modes-brief.md)
> (authoritative mode spec) · [mode-scoped-layouts-plan.md](mode-scoped-layouts-plan.md)
> (the resolver this plan depends on) · [panel-mode-matrix.md](../reference/panel-mode-matrix.md)
> (per-panel availability/behaviour) · [center-view-tabs.md](center-view-tabs.md)
> (the centre container) · [scripted-events-plan.md](scripted-events-plan.md)
> (the deterministic event layer this plan extends).

---

## 1. The rule

> **Left and centre are the same in all three modes. Only the right column
> differs.**

This is not tidiness, it is the **experimental control**. If a participant
behaves differently in mode 2, that difference has to come from the interaction,
not from the screen having been rearranged. Today the layout is itself a
confounding variable: Director renders `two-col` with no left column at all
([app.component.html:161-170](../../frontend/src/app/app.component.html)), so
"Director felt different" is partly a statement about pixels.

| Zone | Question it answers | Rule |
|------|---------------------|------|
| **Left** | *What is going on?* | Status + events. **Read-only, enforced** |
| **Centre** | *How do I look at it?* | Streckenplan · ZWL · Fahrplan as tabs. Identical |
| **Right** | *What do I do?* | The one decision column. **This is where the mode lives** |

**Read-only means: view yes, act no.** Clicking a train in the left column to
focus it on the map is navigation and stays. Setting an override from there does
not. (Decision, 2026-09-02.)

---

## 2. Starting point, verified in code

Four facts that the plan has to move:

1. **The left column carries dispatch actions.** The trains roster renders
   per-train override buttons
   ([left-sidebar.component.html:96-116](../../frontend/src/app/features/left-sidebar/left-sidebar.component.html)),
   and `agents-table` has a `col-actions` column
   ([agents-table.component.html:104-121](../../frontend/src/app/features/agents-table/agents-table.component.html)).
2. **The centre carries mode decisions.** `director-directive` and
   `strategy-options` sit above the map, `co-learning-reflection` below it
   ([app.component.html:176-268](../../frontend/src/app/app.component.html)).
   Both belong to the right column under the rule above.
3. **The Fahrplan is in no mode layout.** `timetable` is registered as a centre
   view ([center-views.ts:33](../../frontend/src/app/features/view-tabs/center-views.ts))
   but only the Combined-Actions preset configures it.
4. **Zone detection is string-sniffing and gets presets wrong.**
   `toRuntimeZone()` ([app.component.ts:1254-1266](../../frontend/src/app/app.component.ts))
   derives the zone from the column's `role`/`name`: a preset column named
   `"Entscheidung"` matches neither `right` nor `center|main|map` and is typed
   **`left`**. The CSS-class sibling has an extra `index === 1` fallback the zone
   function lacks, so the two already disagree. Any zone-based rule must fix this
   first (§7 P0).

---

## 3. Left zone — three slots, filled per mode

Same three slots everywhere; what fills them may differ, because a Director's
"what is going on" is not a dispatcher's. Notifications alone would leave
Director's left column empty — measured over ~120 steps, the feed there reports
nothing, since malfunctions and operator overrides are the two things that do not
happen in that mode (see the comment at
[app.component.html:317-321](../../frontend/src/app/app.component.html)).

| Slot | Recommendation | Co-Learning | Director |
|------|----------------|-------------|----------|
| **Status** | `situation-summary` | `situation-summary` | `situation-summary` + **`goal-achievement`** |
| **Events** | `notifications` | `notifications` | `notifications` + **`ai-activity`** |
| **Trains** | `agents` *(read-only)* | `agents` *(read-only)* | — *(Director does not dispatch per train)* |

Two things fall out of this that are worth having on their own:

- **`goal-achievement` comes back.** It is offered in *no* mode today
  (`'goal-achievement': []` in
  [panel-mode-availability.ts](../../frontend/src/app/core/layout/panel-mode-availability.ts))
  because the A/B/C strategy tiles superseded it as a *decision* surface. As a
  pure status readout with no lever it is exactly what the left zone wants, and
  it is `shipped` code that currently renders nowhere.
- **`ai-activity` moves left.** It is a feed without actions; it was only ever in
  the right column because Director had no left column to put it in.

### Enforcing read-only

Derive it from the zone rather than writing it into each widget:
`panel.zone === 'left'` ⇒ the host passes `readonly` to the widget. `PanelInstance`
already carries `zone`
([layout.models.ts:60](../../frontend/src/app/core/layout/models/layout.models.ts)),
and `panel-plugin-host` already receives the whole `PanelInstance`, so the seam
exists. Only three widgets need to honour the flag today (`agents` →
`left-sidebar`, `agents-table`, `notifications`' dismiss); everything else in the
left zone is already passive. Selection/focus emissions stay untouched.

---

## 4. Centre zone — one `view-tabs` container

`Streckenplan (flatland-map)` · `ZWL (marey)` · `Fahrplan (timetable)`, in every
mode, via `settings.tabs: ['flatland-map', 'marey', 'timetable']`. The container
is registry-driven and already does this; what is missing is the configuration in
the mode layouts.

### Does that make sense for Director? Yes — with a different default tab

The Director does not ask "which train, where", it asks **"does the plan hold?"**
That is a question about time, not about place: plan-vs-actual divergence is
legible on the ZWL and nearly illegible on a map with 52 trains. So the same
three tabs, a different entry point:

| Mode | Default tab | Why |
|------|-------------|-----|
| Recommendation | Streckenplan | resolve a conflict spatially, where it happens |
| Co-Learning | Streckenplan | "my plan (blue) vs AI plan (yellow)" is drawn on the map |
| **Director** | **ZWL** | plan↔actual is a time axis; the map is too dense at scale |

`MODE_DEFAULT_VIEW` ([view-tabs.component.ts:14-18](../../frontend/src/app/features/view-tabs/view-tabs.component.ts))
already encodes exactly this table — its Director entry becomes `'marey'` now
that `goal-achievement` moves left. The mode-switch reset of the active tab stays
as is.

The map keeps the Director look-ahead overlay (`directorPreviewPaths`): it is
supervisory evidence, not a lever.

---

## 5. Right zone — per mode

### 5.1 Recommendation (WP 3.1) — a stack, one reading order

```
Empfehlung (confidence + countdown)      recommendations
  └ reliability strip                    risk-uncertainty, embedded
Folgen: who is affected                  impact
Zug-Detail (the intervention)            agent-inspector
Entscheidungsprotokoll (collapsed)       decision-log
```

*Suggestion → reliability → consequence → intervention.* **No segments here**
(decision, 2026-09-02): Recommendation should feel fast and unambiguous, and a
tab bar in front of a single decision surface is friction. It is the only mode
whose right column reads top-to-bottom in one pass.

The `agent-inspector` carries more weight than today, because the left roster
loses its buttons: together with the map's agent overlay it becomes *the*
intervention surface.

`risk-uncertainty` moves from "its own panel somewhere" to a strip inside the
recommendation card. An uncertainty number that is not adjacent to the claim it
qualifies is not calibration support, it is decoration.

### 5.2 Co-Learning (WP 3.3) — segmented: Entscheiden / Explorieren / Reflektieren

Five stacked panels do not fit a 26 % column, and the mode genuinely has three
distinct activities. A segmented control at the head of the right column — the
same idea as `view-tabs`, applied to the right zone (new container widget
`decision-tabs`, see §6):

| Segment | Contents |
|---------|----------|
| **Entscheiden** | `combined-actions` in neutral framing (A/B/C, no badge, no ranking) + `agent-inspector` |
| **Explorieren** | `whatif-compare` (B1, blue = mine / yellow = AI), free branching |
| **Reflektieren** | `co-learning-reflection`, with `decision-log` beneath it as the evidence |

The **Reflektieren** segment carries a badge when a reflection moment is pending.
The selection logic exists and is transparently scored — pattern deviation,
override, deferral, confirmed preference, max 3 per run
([reflection-moments.ts](../../frontend/src/app/core/reflection-moments.ts)) —
and `store.reflectionRequested` is already the signal that opens it. This gets
reflection out of the centre (where it sat under the map, collapsed, easy to
miss) without burying it at the bottom of a long column.

Exploration and reflection are the two things this mode is *for*, so they get
equal billing with the decision itself rather than sharing its scroll.

### 5.3 Director (WP 3.4) — a stack, objective first

```
Auftrag setzen / autonomen Lauf starten    director-directive   (from the centre)
Zielsetzung A/B/C                          strategy-options     (from the centre)
Autonomiegrad                              NEW (§6)
Prognose der gewählten Strategie           strategy-forecast
Reflexion & Gelerntes (collapsed)          strategy-reflection
                                           + co-learning-effect + learning-records
```

`ai-activity` moves left. The three learning panels become one collapsible block:
they are three views of the same object and cost three panel headers today.

**The honest cost of this move.** `strategy-options` sits in the centre on
purpose — "decide here, see it on the map below, read the consequence under the
map", and the forecast was moved out of that slot precisely because stacking it
there pushed the map off a laptop screen
([app.component.html:180-199](../../frontend/src/app/app.component.html)). In a
26 % column the A/B/C tiles have to stack vertically instead of sitting side by
side, which weakens the "compare three at a glance" reading. What survives is the
coupling to the map: hovering a tile already drives the dashed look-ahead overlay,
so "decide right, see centre" replaces "decide above, see below". If the vertical
tiles turn out to read badly, the fallback is a wider right column in Director
only (32 %) — a layout constant, not a structural exception.

---

## 6. Widget work

| Widget | What changes | Effort |
|--------|--------------|:------:|
| `agents` / `agents-table` | honour `readonly` from the zone; hide action affordances, keep selection | S |
| `notifications` | `readonly` (no dismiss in the left zone) — decide whether dismiss counts as an action | S |
| `ai-activity` | render as a left-zone feed peer next to notifications | S |
| `goal-achievement` | re-enable for Director (`['director']` instead of `[]`), left zone, status framing | S |
| `risk-uncertainty` | embed as a strip inside the recommendation card | S |
| `view-tabs` | Fahrplan tab in all mode layouts; Director default `marey` | S |
| **`decision-tabs`** | **new** — right-column segment container; registry-driven like `view-tabs` | S |
| `timetable` | filter "affected / delayed only" — 52 trains (Olten) are unreadable otherwise | S–M |
| `strategy-options` | vertical tile layout for a sidebar column | S–M |
| `co-learning-reflection` | **collect**: one reflection artefact per run + JSON export, so reflections are study data and not just UI state | M |
| `whatif-compare` (B1) | **free exploration**: branch from any train/step, hold and compare several branches (the TraceRL branching-tree pattern) | M–L |
| **Autonomy dial / allocation** | **new** — `planned` in the catalog; the adjustable-autonomy lever D3.1 §7 asks for, and the thing that makes Director more than "the AI runs, you watch" | M |
| `marey` (ZWL) | B2: conflict ribbons + plan-vs-actual. The largest single lever for Director supervision | L |

Effort scale per [widget-catalog.md](widget-catalog.md): S ≤150k tokens/≤1 day ·
M 150–400k/1–3 days · L >400k/3–5+ days.

**The two development priorities** are free exploration in B1 (without it
Co-Learning only reacts, it never explores) and the autonomy dial (without it
Director has no adjustable autonomy, only autonomy).

---

## 7. Scenario — 2–3 events, sampled not scripted

Today there are two extremes and nothing between them: **disturbance files** at
fixed steps (deterministic, `malfunction_rate: 0`,
[disturbances.py](../../backend/app/core/disturbances.py)) or **random
malfunctions** via the rate — where the number of events is whatever the seed
gives. What a study wants is a *bounded* number of *unauthored* events.

### Event budget

A third layer, `backend/app/core/event_budget.py`, beside `disturbances.py`:

```json
{
  "count": [2, 3],
  "windows": [[10, 45], [45, 95], [95, 145]],
  "types": { "train_delay": 0.5, "area_block": 0.3, "warning": 0.2 },
  "targets": "conflict_prone",
  "min_spacing": 20,
  "quiet_tail": 30
}
```

The sampler draws 2–3 events, at most one per window, with the step drawn inside
the window and the type drawn by weight. The **target** is drawn only from
eligible candidates — a train approaching the single-track section, a cell with a
viable alternative route — so every event is consequential without its timing or
its victim being authored. Guard rails: minimum spacing, no event inside the
closing window (consequences must play out), and a feasibility check against the
planner so a draw cannot produce an unresolvable deadlock.

It reuses the existing event vocabulary and application path entirely
(`train_delay` becomes a Flatland malfunction, so the state machine, the delay
KPI, the map badge and the notifications treat it exactly like an emergent
breakdown). No new HMI concept.

**Seeding:** an `event_seed` separate from the env `seed`
([session.py:9](../../backend/app/models/session.py)). Same env, different event
draw is one parameter; the same draw replays exactly. `malfunction_rate` stays 0
so the budget *is* the event count.

### Which scenario

`pf-ch-corridor-stops` — 16 trains with intermediate calls, so knock-on effects
and connections actually exist. The 3-train `wn-wal` conflict scenarios are too
small: a second event has nothing to interact with. Olten stays the "environment
we did not design the answer for" validation case, not the demo default.

### Events are re-drawn per mode

Decision, 2026-09-02. The guided demo runs the three modes on the same
environment; if it also ran the same event draw, a participant would arrive at
mode 3 already knowing the answer, and the mode comparison would measure recall.
So: **same budget, a different `event_seed` per mode**, with the seed set fixed
per participant and the mode order counterbalanced (Latin square). Comparability
comes from the budget and the network being identical, not from the incident
being identical.

Trade-off, stated so it is not rediscovered later: variance between modes now has
an event-draw component. The budget's guard rails (fixed count, fixed windows,
eligible-target rule) are what keep that variance bounded; if a study needs
tighter control, a drawn set can be frozen to a disturbance file and replayed —
the formats are compatible by construction.

---

## 8. Sequencing

- **P0 — zones become data.** Add an explicit `zone: 'left' | 'center' | 'right'`
  to `LayoutPresetColumn`, keep `toRuntimeZone()`'s string-sniffing only as the
  legacy fallback (§2.4). Nothing else in this plan is safe until a right column
  is actually typed `right`.
- **P1 — the three layouts as presets.** Write Recommendation / Co-Learning /
  Director into [layout-presets.ts](../../frontend/src/app/core/layout/layout-presets.ts)
  so they are reviewable and diffable, instead of growing the hardcoded default
  further. Needs P1 of [mode-scoped-layouts-plan.md](mode-scoped-layouts-plan.md)
  — the resolver that picks a layout from `interactionMode()` — otherwise the
  presets stay manually chosen and the saved-layout path keeps bypassing mode
  behaviour.
- **P2 — read-only left zone** (the `readonly` flag + the three widgets), and the
  moves that need no new code: `ai-activity` left, `goal-achievement` re-enabled,
  Fahrplan tab, Director default tab.
- **P3 — `decision-tabs`** + the Co-Learning segments; `strategy-options` vertical.
- **P4 — event budget** (backend, testable on its own, independent of P0–P3).
- **P5 — the development items:** B1 free exploration, autonomy dial, reflection
  collection/export, then B2.

---

## 9. Guardrails

- Frontend work here is presentation and layout selection only. Do not touch
  `_recordTrajectory` or the scenario-refresh throttling; do not reshape payloads
  to suit a column.
- `InteractionMode` stays the single mode flag. A layout is *selected by* the
  mode; it never becomes a second mode flag.
- Availability stays in `panel-mode-availability.ts`; behaviour stays inside the
  components reading `store.interactionMode()`. This plan changes *where* panels
  render, and adds `readonly` — it does not add a third gating mechanism.
- No hardcoded colours in any new container (`decision-tabs` follows the
  `view-tabs` token usage).
- Backend: the event budget is additive next to `disturbances.py`; existing
  scripted scenarios and their tests keep working unchanged. New gating needs
  coverage in `backend/tests/`.

---

## 10. Open questions

1. **Does "dismiss" count as an action?** Dismissing a notification changes no
   train, but it changes what the operator sees later — and in a study it is
   recorded behaviour. Draft: keep it, it is annotation, not dispatch.
2. **Director right column width.** 26 % like the others (consistency) or 32 %
   (the A/B/C tiles read better)? Decide after seeing the vertical tiles.
3. **Where does `combined-actions` belong in Recommendation?** The matrix gives
   it a recommendation framing in that mode, but the column above has no slot for
   it. Either it replaces `impact` there, or Recommendation keeps a single-action
   surface and E1 stays a Co-Learning/Director widget.
4. **Timetable filter default.** "Affected only" by default is readable but hides
   the plan; "all, affected highlighted" is honest but unreadable at 52 trains.
   Probably mode-dependent — which contradicts §4's "identical centre" and should
   therefore be data-driven, not mode-driven.
