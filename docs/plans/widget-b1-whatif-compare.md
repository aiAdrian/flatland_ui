# Widget spec — What-if Compare ("My solution vs. AI")

> Catalog **B1** — flips the `status: 'planned'` A3S-light entry in
> `core/widgets/widget-catalog.ts` to `first-cut`. Grounded in the §3.3
> dual-path (formulate-own vs AI plan). Reuses the **existing** what-if backend
> — no new endpoint.

## 1. Identity
- **Name:** What-if Compare ("My solution vs. AI")
- **`kind`:** prediction (answers *"what happens next / what-if?"*)
- **`granularity`:** detail
- **Default zone:** right
- **Panel `type`:** `whatif-compare`
- **Catalog id:** B1
- **Source(s):** [UIX] widget-catalog.md B1; interaction-modes-brief §3.3
- **Grounding reference:** AI4REALNET/`agent-as-a-service-trace-rl` (A3S/TraceRL)
  — Flatland-configured restore → simulate-forward → report action space; the
  branch-compare convention **human steps = blue, AI-simulated = yellow**.
- **Source origin:** `Source: from-scratch, deliberately` for the frontend
  widget UI, but the *algorithm* (forward-simulate a branch, KPI delta) is **not**
  rebuilt — it reuses this repo's existing `POST /{id}/what-if-override`
  (`overrides.py:152`, `TrajectoryBranchRunner`), which is our in-repo stand-in
  for A3S restore/simulate. Swapping in the real A3S service later is a backend
  change behind the same endpoint contract (Open questions).

## 2. Promise
> Formulate your own action for the selected train and see its simulated future
> **side-by-side with the AI's plan** — the selected train's own fate primary
> (arrives / delay / deadlock), the system effect secondary, and the two branch
> paths drawn on the map (blue = you, yellow = AI) — before committing anything.

## 3. Per-mode behaviour
Prediction widget, offered in **all** modes; framing differs (neutral, never
ranked in Co-Learning — this is the dual-path core, not a recommendation).

- **Recommendation (WP 3.1):** the "AI plan" column is anchored to the current
  course *including the AI's recommended action if one is active*; the human's
  proposed action is compared against it. Compare-with-a-suggestion.
- **Co-Learning (WP 3.3):** the **dual-path core** — the human formulates their
  own action ("My plan", blue) and it is simulated forward against the AI's plan
  ("AI plan", yellow), both neutral, no winner marked. Committing "My plan"
  records a `docLearningFeedback` override that feeds the reflection module.
- **Director (WP 3.4):** **read-only supervisory what-if** — inspect a branch to
  understand a decision point without taking per-step control; the Commit button
  is hidden (the AI owns actuation under the directive).

## 4. System interaction
- **Data in** — `store.selectedHandle` (target train), `store.interactionMode()`
  (→ `modeBehavior`), `store.session()`, `api.whatIfOverride(id, {handle: action})`
  → `WhatIfResult { baseline, branch, delta, summary, train, baseline_trajectories,
  branch_trajectories, handles }`.
- **Actions out** — `store.setOverride(handle, action)` (Commit "My plan", not in
  Director); `store.whatIfPreview.set({baseline, branch, handles})` on choose()
  (and cleared on commit / destroy) so the map draws the two branch paths;
  `store.selectedHandle.set(...)` is set elsewhere (agents/impact/map).
- **Backend table:**

| Field / capability | Available now | To build (flagged) |
|--------------------|:-------------:|:------------------:|
| Forward-sim a branch (override) → KPIs | ✓ (`what-if-override`) | |
| baseline (AI course) vs branch (human) KPIs | ✓ | |
| KPI delta (delay / deadlocks / done) + summary | ✓ | |
| Per-train candidate actions (Hold/Forward/Left/Right/Stop) | ✓ (`ActionInt`) | |
| **Per-train outcome** (selected train arrives/delay/deadlock, both branches) | ✓ | |
| **Blue/yellow trajectory overlay** on the map (branch vs baseline paths) | ✓ | |
| Real A3S/TraceRL Redis service behind the endpoint | | ✓ (flagged — same contract) |

## 5. Allocation & accountability touchpoints
- **Loop stage:** decision (what-if before commit) → capitalization (on commit).
- **Owner per mode:** Recommendation = shared (AI advises, human acts);
  Co-Learning = human (owns actuation + reflection); Director = ai (read-only).
- **Decision events emitted:** committing "My plan" goes through
  `store.setOverride` → existing `docLearningFeedback` / decision-log seam
  (`session.store.ts:1040`). The what-if itself is read-only (no event).

## 6. Acceptance scenario
> In Co-Learning, the operator selects a blocked train, clicks **Hold** in the
> What-if Compare widget. The widget forward-simulates and shows: **AI plan**
> (yellow) `done 6/8 · delay 41 · 0 deadlocks` vs **My plan** (blue)
> `done 7/8 · delay 22 · 0 deadlocks`, delta `+1 done · −19 delay`, summary line.
> The operator commits "My plan"; the override is recorded for reflection.
>
> **Measurable success (Q1 distinct modes):** the same widget, same train, same
> action shows a **Commit** affordance in Co-Learning/Recommendation but **not**
> in Director; and the Co-Learning columns carry **no** "recommended"/ranked
> marker while Recommendation anchors the AI column to the active suggestion.

## 7. Effort & changes
- **Effort:** M (frontend widget + registration; backend reused).
- **Files / seams to touch:** new `features/whatif-compare/*`; register in
  `panel-plugin-host.{ts,html}`, `layout-designer.component.ts` palette,
  `widget-catalog.ts` (B1 → first-cut, set `type`), `panel-mode-matrix.md`,
  `widget-catalog.md` status. `panel-mode-availability.ts`: **omit** (all modes).

## 8. Open questions / risks
- **A3S integration:** this cut reuses the in-repo `what-if-override`
  (TrajectoryBranchRunner), *not* the real AI4REALNET A3S/TraceRL Redis service.
  That is a **deliberate** reuse-of-our-own-forward-sim decision; the endpoint
  contract (`WhatIfResult`) is shaped so the real A3S can replace the
  implementation without a frontend change. **Not built from scratch** — the
  algorithm is the existing branch runner.
- **Per-train outcome (built):** the selected train's own
  arrived/delay/deadlock is now primary content (top), system KPIs secondary
  (bottom) — the "local action → global effect" teaching point. Backend
  `BranchResult.agent_outcomes` + a `train` block on the what-if response;
  delay reuses the exact `serializer.py` formula.
- **Trajectory overlay (built):** the blue (human = branch) / yellow
  (AI = baseline) per-cell paths are now drawn on the map via
  `store.whatIfPreview` (dashed, distinct from the solid scenario preview),
  fed by `baseline_trajectories` / `branch_trajectories` on the what-if
  response (scenario shape, from `_extract_trajectories` on the branch
  snapshots). Clears on commit / leave / destroy (previewOn/Off discipline).
- **Action set:** offers the raw Flatland actions for the selected train
  (Hold/Forward/Left/Right/Stop). Whether to restrict to *reachable* actions per
  cell (like impact-panel's reroute gating) is a refinement, not blocking.
