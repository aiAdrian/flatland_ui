# Build Brief — Widget #1: Conflict-aware Marey

> For Claude Code. Implements the highest-convergence idea from
> `docs/reference/ui-exploration-synthesis.md` (6/6 models). Turns the Marey from a passive
> replay into a **predictive conflict instrument**. Written to satisfy the Fusion
> review's build-readiness gaps (resource semantics, rollout-based numbers,
> honest uncertainty). Read `docs/interaction-modes-brief.md` (modes) and
> `docs/reference/ui-exploration-synthesis.md` (§Fusion review) first.

## Goal
On the existing Marey (`features/marey-chart/`), add three optional layers:
1. **Forecast projection** — dashed forward stringline per train to its target.
2. **Conflict markers** — a marker at the exact (step, track-position) where two
   trains are predicted to contend for the **same resource**, sized by severity.
3. **Headway / occupancy ribbon** (phase 2) — a faint band around each line; tight
   overlap = small margin.

Ship in that order. (1)+(2) are the value; (3) is a refinement.

---

## Hard rules from the Fusion review (do not skip)
- **A line crossing is NOT a conflict.** A conflict marker may only be drawn where
  the backend reports two agents contending for the **same resource** — i.e. a
  `Conflict` with a concrete `position` (cell), `step`, and `agents`. Never infer a
  conflict from two SVG lines intersecting (multi-track / parallel / level-free
  crossings make that wrong).
- **Every number shown comes from a rollout, labelled "estimated".** Any
  "+N delay / −1 deadlock / clears in K" must be produced by a forward
  simulation (see Data), shown as *estimated over horizon H*, never fabricated or
  hard-coded. If no rollout backs a number, don't show the number.
- **Resource semantics on every marker:** cell `(r,c)` (+ direction/edge when
  available), `step`, involved `agents`, and `clearsAtStep` if known — carried in
  the payload, not re-derived in the view.

---

## Data — where the predictions come from (backend)

We already have the machinery; wire it, don't reinvent it.

- **`core/conflict_detector.py` → `ConflictDetectionCallbacks`** is a passive
  observer over a **trajectory run**. It emits `Conflict{kind, step, agents,
  position, info}` (kinds: `blocked`, `swap_attempt`, `deadlock_cycle`,
  `malfunction`, `overdue_arrival`, `agent_done`), plus per-step snapshots and
  `get_kpis()`. This is the **resource-tied, rollout-based** conflict source.
  - ⚠️ **Verify first:** the per-step detectors (`_detect_blocked`, `_detect_swap`,
    `_detect_malfunctions`, `_detect_deadlock_cycles`, `_detect_overdue`) appear as
    `pass` stubs in the file, yet `tests/test_conflict_detector*.py` exist. Confirm
    whether detection is implemented (maybe in a later part) or whether wiring them
    is a prerequisite. **If stubbed, implementing them is task 0** — the widget is
    worthless without real conflict events.
- **Forecast trajectories already exist:** `GET /{id}/hmi/scenarios` returns
  `ScenarioOption.trajectories` — per-agent `TrajectoryPoint{step,row,col,dir}`
  over the simulated horizon (`models/hmi.py`, built by `scenario_builder` /
  `hmi_scenario_adapter`). The **active baseline** scenario's trajectories ARE the
  dashed forecast lines — no new sim needed for layer (1).
- **New endpoint `GET /{id}/hmi/conflicts`** (thin): run a short forward rollout
  from the current env state with `ConflictDetectionCallbacks` attached (reuse
  `scenario_runner` / `TrajectoryBranchRunner`, same horizon as scenarios), return
  the predicted `Conflict[]` as JSON (`Conflict.to_dict()` already JSON-safe).
  Cache it next to the scenario cache (`scenario_cache`) keyed the same way, since
  it's the same expensive rollout — see throttling rule below.
- **Per-option consequence numbers** (for the marker tooltip / linked rec card):
  reuse `api/overrides.py`'s existing before/after estimate (it already computes
  deadlock & arrival deltas of an override via `TrajectoryBranchRunner`). That is
  the honest, rollout-based delta — surface it, don't invent one.

Suggested payload per conflict:
```jsonc
{ "kind": "deadlock_cycle", "step": 130, "position": [9, 27],
  "agents": [11, 14], "severity": "high", "clearsAtStep": 148,
  "estimated": true, "horizon": 250 }
```

---

## Frontend — rendering in `features/marey-chart/`

The Marey SVG already exists (`marey-chart.component.ts`, ~1850 lines: `W=1200
H=700`, `xRange` = time window, `yRange` = topology window, brush sync,
`scenarios` signal, `forecastScenarioId`). Add layers **inside the existing
coordinate system** — reuse the same x (step) and y (topology position) scales the
stringlines already use. Do not build a second chart.

1. **Forecast projection layer**
   - Source: active baseline `ScenarioOption.trajectories` (already on
     `store.scenarios()`); draw each agent's future points as a **dashed** line
     continuing from its current position, fading with horizon distance.
   - Gate behind a `layerVisibility.forecast` toggle (extend `LayerVisibility` in
     `core/events/event-types.ts` + `layer-visibility` component).
2. **Conflict marker layer**
   - Source: new `store.conflicts` signal fed by `GET /hmi/conflicts`.
   - For each conflict, place a marker at `x = scaleStep(step)`,
     `y = scaleTopology(position)`; size/colour by `severity`; only render markers
     whose `position` resolves to a row currently shown on the y-axis.
   - Hover → highlight the `agents` on map + Marey (reuse
     `store.setAgentHoverAgents`), tooltip shows cell, step, `clearsAtStep`, and
     the **estimated** consequence (from overrides before/after). Click → select
     both agents + open the matching recommendation/decision card on the right.
   - Gate behind `layerVisibility.conflicts`.
3. **Headway ribbon layer (phase 2)** — faint ±k-step band per line; overlap tints
   hot. Needs a cell-occupancy/safe-separation model on the abstract grid (no real
   signalling) — scope separately; label margins as *estimated*.

### Store wiring (`core/session.store.ts`)
- Add `readonly conflicts = signal<PredictedConflict[]>([])` and a
  `refreshConflicts()` that calls the new endpoint, mirroring `refreshForecasts()`.
- **Throttle exactly like scenarios** (brief §6): conflicts come from the same
  expensive rollout, so fetch only on structural change (session change, play
  start/stop), NOT on every WebSocket state tick. Reuse the `scenario-panel`
  effect rationale; do not add per-tick refetch.

---

## Mode behaviour (via `optionPresentation`, brief §3.1)
- **Recommendation:** conflict marker is annotated with the AI's recommended
  resolution (hold/reroute) + confidence; the consequence delta is shown.
- **Co-Learning:** markers neutral (no preferred resolution); a what-if compare
  draws the human branch **blue** and the AI-simulated branch **yellow**
  (synthesis §what-if; brief §3.3).
- **Director:** markers the AI will auto-resolve are muted grey; only markers that
  breach the directive (e.g. would cause a deadlock / miss a KPI target) stay red
  and pull the supervisor in.

---

## Acceptance criteria
- The **Train 14 @ (9,27) cascade** scenario reproduces: with conflicts on, a
  marker appears at the predicted step/cell where Train 11 meets the malfunctioning
  Train 14; hovering links both trains; the tooltip's delta comes from a rollout.
- Toggling `conflicts`/`forecast` layers off returns the Marey to today's look.
- No conflict marker exists without a backend `Conflict` (no crossing-only markers).
- Every displayed number is traceable to a rollout and labelled estimated.
- Conflicts are **not** refetched on every WS tick (verify via network panel during
  Play); existing scenario/Marey performance unchanged.
- `backend/tests/` stay green; add a test for `/hmi/conflicts` (shape + that it
  reuses the cache).

## Do not touch (brief §6)
- Trajectory compression (`session.store.ts _recordTrajectory`).
- Scenario-refresh throttling rationale in `scenario-panel`.
- `_recoverPolicyAndRetry*` fallbacks; the `InteractionMode` union.

## Smallest first version → defer
- **V1:** forecast dashed lines (from existing scenario trajectories) + conflict
  markers (from `/hmi/conflicts`) with hover-link + estimated tooltip. No ribbon.
- **Defer:** headway/occupancy ribbon (phase 2), edge/direction-level resource
  semantics, multi-branch what-if overlay (that's the Co-Learning compare widget).

## Open questions to resolve before coding
1. Are `ConflictDetectionCallbacks` per-step detectors actually implemented? (If
   `pass`, implement + unit-test them first — prerequisite.)
2. Horizon: reuse the scenarios' horizon (≈250 steps) or a shorter conflict
   look-ahead? Pick one and label it on every estimate.
3. Topology y-mapping: a conflict `position` (cell) must map to the Marey's
   topology row — confirm the existing cell→row mapping the stringlines use and
   reuse it (no parallel mapping).
