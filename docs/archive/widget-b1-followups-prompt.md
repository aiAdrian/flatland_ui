# Widget B1 follow-ups — delegated work brief (archive)

> **Status:** Delegated 2026-07-10 to **GLM 5.2** in a parallel Claude Cowork
> session; in implementation. Kept as an archive artifact to reflect on the
> delegation later (what was asked vs. what was built) and on AI-usage patterns.
>
> **Design decision baked in:** per-train consequences shown *primary*, system
> effect *secondary* (chosen over "train-only" so the local-action → global-effect
> teaching point stays visible).
>
> This is the verbatim brief handed to the building agent. The live spec is
> [`widget-b1-whatif-compare.md`](widget-b1-whatif-compare.md); update that (not
> this file) as the feature lands.

---

## Task: Extend the "What-if Compare" widget (B1) — per-train consequences + map overlay

You are working in the Flatland Dispatcher repo (AI4REALNET), branch `explore_db`.
Frontend: Angular standalone + signals + SBB Lyne. Backend: FastAPI + Flatland-RL.
Read CLAUDE.md and docs/plans/widget-b1-whatif-compare.md first.

### Context — the widget as it is today
The "What-if Compare" widget (Widget B1, kind=prediction) lets the operator pick a
train (store.selectedHandle) and propose an action (Hold/Forward/Left/Right). It then
calls the backend to forward-simulate and shows the AI plan vs "My plan" side-by-side.

- Component: frontend/src/app/features/whatif-compare/whatif-compare.component.{ts,html,scss}
- It calls: api.whatIfOverride(sessionId, { [handle]: action })  (api.service.ts:139)
- Backend endpoint: POST /{session_id}/what-if-override  (backend/app/api/overrides.py:152)
  - baseline = current AI course (committed overrides); branch = baseline + the proposed override
  - helper _branch_kpis_full (overrides.py:35) runs TrajectoryBranchRunner.run_branch and
    returns SYSTEM KPIs: { deadlocks, done, total, delay }
- Response type WhatIfResult (frontend/src/app/core/events/event-types.ts:129):
    { horizon, baseline: WhatIfKpis, branch: WhatIfKpis, delta:{delay,deadlocks,done}, summary }
  WhatIfKpis = { deadlocks, done, total, delay }
- Colour convention (AI4REALNET A3S/TraceRL, CLAUDE.md): human = BLUE, AI = YELLOW.
  Tokens already exist in frontend/src/styles.scss: --app-whatif-human (blue), --app-whatif-ai (yellow).
- The widget is mode-aware (modeBehavior computed): Commit available in recommendation +
  co-learning, hidden in director. It sits in the co-learning default-layout right pane.

Two things are missing. Build BOTH.

### TASK 1 — Show consequences for the SELECTED TRAIN (primary), system effect secondary
Today the KPIs are system-wide only, which is abstract for a single-train decision.
Desired: the selected train's OWN outcome is primary (big/top), the system effect stays
as secondary context (smaller/below). Do NOT drop the system numbers — the teaching point
is "local action → global effect", so keep both.

Backend:
- In run_branch (backend/app/core/scenario_runner.py:153), the forked `env` is fully
  available at ~line 232 before the BranchResult is built. Extract a per-agent outcome map
  and expose it on BranchResult (new optional field, e.g. `agent_outcomes: Dict[int, dict]`):
  for each agent handle → { arrived: bool (state == TrainState.DONE), deadlocked: bool,
  delay: int }.
  - Reuse the deadlock set: refactor count_deadlocked_agents (scenario_runner.py:61) into a
    `deadlocked_agents(env) -> set[int]` and keep the count as len(...) of it.
  - Per-agent delay: reuse the exact formula from serializer.py:118-128
    (delay = elapsed - latest_arrival when overdue and state != DONE, else 0).
- In _branch_kpis_full / the what-if-override endpoint (overrides.py), add a `train` block to
  the response for the overridden handle(s) (the operator selects ONE train, so use the first
  override key):
      "train": { "handle": h,
                 "baseline": {arrived, delay, deadlocked},
                 "branch":   {arrived, delay, deadlocked} }
  Keep the existing baseline/branch/delta/summary system KPIs unchanged.
- Add a backend test (mirror backend/tests style) for the per-train outcome (arrived flips,
  delay/deadlock reported for the selected handle).

Frontend:
- Extend WhatIfResult (event-types.ts) with the optional `train` field + a WhatIfTrainOutcome type.
- In whatif-compare.component.html, restructure the result: PRIMARY row = the selected train
  (Arrives? on-time/late by N / runs into deadlock), comparing My plan (blue) vs AI plan (yellow);
  SECONDARY, smaller = the system effect (done/total, deadlocks) as today. Keep blue/yellow tokens,
  no hardcoded colours. Keep the mode-aware Commit behaviour untouched.

### TASK 2 — Show the two proposals ON THE MAP (blue = human, yellow = AI)
Today nothing about the branch is drawn on the map. The map already has a forecast-trajectory
overlay for POLICY previews:
- flatland-map.component.ts:353 (selectedTrajectoryFutureSegments) reads store.previewScenarioId
  and draws activeScenario.trajectories[handle]. This is keyed to policy scenarios that already
  carry trajectories — the what-if override branch has none.

Backend:
- Make what-if-override ALSO return per-agent trajectories for BOTH branches (baseline = AI,
  branch = human), in the same shape scenarios use. See how scenarios expose trajectories:
  hmi_scenario_adapter (_extract_trajectories) and Scenario.trajectories — a dict
  { handle: [ {step, row, col}, ... ] }. Capture snapshots from the forked env during
  run_branch (or reuse the existing snapshot/trajectory machinery) and return
  { baseline_trajectories, branch_trajectories } on the what-if response.
  IMPORTANT: do NOT touch the trajectory-compression path in session.store.ts _recordTrajectory
  or the scenario-refresh throttling — this is a separate what-if payload.

Frontend:
- Add a store signal for the what-if map preview, e.g.
  store.whatIfPreview = signal<{ baseline: TrajById; branch: TrajById; handles: number[] } | null>(null).
- whatif-compare sets it on choose() (and clears it on mouse-leave / ngOnDestroy, following the
  same discipline as recommendations-panel previewOn/previewOff at
  recommendations-panel.component.ts:147-156).
- Extend the map overlay (flatland-map.component.ts) to, when store.whatIfPreview() is set, draw
  TWO forecast paths for the affected handle(s): the branch path in --app-whatif-human (blue) and
  the baseline path in --app-whatif-ai (yellow). Keep it visually distinct from the existing
  single-scenario preview. No hardcoded colours.

### Guardrails (from CLAUDE.md)
- Frontend stays Angular standalone + signals + SBB Lyne. NO hardcoded colours — use the
  --app-whatif-* tokens and --sbb-color-* / light-dark(). Agent colours via AgentColorService.
- Keep interaction-mode semantics in the InteractionMode union — no parallel flags. Per-mode
  behaviour lives in the widget's modeBehavior computed; don't change rec/director behaviour.
- Do NOT touch: session.store.ts _recordTrajectory (trajectory compression), the scenario-panel
  refresh throttling, the _recoverPolicyAndRetry* fallbacks.
- Reuse the existing what-if-override + trajectory machinery; do NOT rebuild the branch-sim
  algorithm. (The endpoint contract is meant to later swap in AI4REALNET A3S/TraceRL.)
- Keep backend/tests green; add coverage for the new fields.

### How to run / verify
- Backend + frontend launch configs are in .claude/launch.json (uvicorn :8000, ng serve).
- Verify with the preview tools per interaction mode:
  * Co-Learning: select a train, pick "Hold" → the selected train's own outcome shows primary,
    system effect secondary; the map draws blue (My plan) vs yellow (AI plan) forecast paths.
  * Director: Commit stays hidden; the what-if is read-only.
- `ng build` must be clean. Update docs/plans/widget-b1-whatif-compare.md (remove the two
  "flagged extension" caveats now that per-train + map overlay are built) and the B1 grounding
  note in frontend/src/app/core/widgets/widget-catalog.ts if behaviour text changes.

### Acceptance
1. Selecting Train X + an action shows X's own arrival/delay/deadlock prominently, with the
   system effect kept as secondary context; blue=My plan, yellow=AI plan.
2. The same action draws the two branch trajectories on the map (blue=human, yellow=AI) for the
   affected train(s), clearing on leave.
3. Per-mode behaviour (recommendation/co-learning/director) is unchanged except the new content.
4. Backend tests green; ng build clean; no hardcoded colours.
