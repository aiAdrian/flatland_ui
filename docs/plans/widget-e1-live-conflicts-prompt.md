# Widget E1 — packages from live conflicts — delegated work brief

> **Status:** Delegated 2026-08-27 to **GLM 5.2** (open-weight, selected in
> Claude) in a parallel session. Kept as an archive artifact to reflect on the
> delegation later (what was asked vs. what was built) and on AI-usage patterns.
>
> **Why now:** the PF–CH scenarios (3 trains) exposed a defect the 8-train demo
> hid — the action cards name trains the session does not contain. See
> "The defect" below.
>
> **Scope decision baked in:** this is *Stufe 1* only — packages derived from
> live conflicts, impact figures still from the deterministic model. The real
> PP/CBS re-solve stays out (see "Explicitly out of scope").
>
> This is the verbatim brief handed to the building agent. The live spec is
> [`widget-e1-combined-actions.md`](widget-e1-combined-actions.md); update that
> (not this file) as the feature lands.

---

## Task: Derive Combined Actions packages from the session's real conflicts

You are working in the Flatland Dispatcher repo (AI4REALNET), branch `explore_db`.
Frontend: Angular standalone + signals + SBB Lyne. Backend: FastAPI + Flatland-RL.

**Read first:** `CLAUDE.md`, then `docs/plans/widget-e1-combined-actions.md`
(especially §4's flagged table and §8's open questions — this task turns one
flagged row green and deliberately leaves the others alone).

### The defect

Load the scenario preset `pf-ch-wn-wal-conflict` (3 trains: handles 0, 1, 2).
The Combined Actions panel shows three cards whose chips read:

```
A: IC_703, ICE_42, RE_18, S8_214
B: EC_91,  IC_703, RB_51,  ICE_42
C: IR_227, RE_18,  TGV_12, S8_214
```

Only `IC_703`, `ICE_42`, `RE_18` exist. The other five are phantoms.

Two hardcoded lists produce this:

- `SERVICE_ROSTER` — `frontend/src/app/core/train-identity.service.ts:26` — eight
  authored names; the i-th train by handle gets the i-th name. Three trains ⇒
  five names stay unassigned.
- `ACTION_PACKAGES` — `frontend/src/app/core/combined-actions/action-packages.ts:35`
  — three authored packages that reference names across the *whole* roster,
  independent of the session.

The existing guard does not catch it: `bound` at
`frontend/src/app/features/combined-actions/combined-actions.component.ts:208`
is `Object.keys(handleByTrain()).length > 0` — "is there *any* train", not "does
every referenced train exist". `handleFor(train)` (same file, ~line 218) returns
`null` for the phantoms, so the map/ZWL overlay silently cannot point at them.

The 8-train Guided Demo assigns the whole roster, so every chip resolves and the
defect is invisible there. Do not treat this as a regression from the PF–CH
scenarios — it is a fixture limitation they exposed.

### The goal

Packages are built from the trains actually contending in *this* session, so
every chip resolves to a real handle. Impact figures keep coming from the
existing deterministic model.

---

## TASK 1 — Backend: expose the conflicts ahead

**Reuse the existing trajectory machinery. Do not write a new conflict detector.**

`TrajectoryBranchRunner` (`backend/app/core/scenario_runner.py:183`) already
forks the env, runs forward and collects conflicts through
`ConflictDetectionCallbacks`. `run_branch()` (`scenario_runner.py:206`) returns a
`BranchResult` (`scenario_runner.py:139`) whose `conflicts: List[Conflict]` field
is exactly what this task needs. A no-override run — `run_branch(overrides={})` —
is the *predicted* course of the network from the current step, which is the right
semantics: a coordinated action answers an upcoming contention, not a past one.

`Conflict` (`backend/app/core/conflict_detector.py:47`):

```python
kind: ConflictKind          # "blocked" | "malfunction" | "swap_attempt"
                            # | "deadlock_cycle" | "agent_done" | "overdue_arrival"
step: int
agents: List[int]           # involved agent handles
position: Optional[Tuple[int, int]]
info: Dict[str, Any]
```

Build a new endpoint, next to the existing HMI endpoints in
`backend/app/api/hmi.py` (see `get_impact` at `hmi.py:117` for the shape,
session lookup and error handling to copy):

```
GET /{session_id}/hmi/contentions
```

Returns a list of contention groups, most urgent (lowest `step`) first:

```json
[
  {
    "step": 14,
    "position": [2, 96],
    "kind": "blocked",
    "handles": [0, 1, 2]
  }
]
```

Rules:

- Keep only kinds that name **two or more** contending agents:
  `blocked`, `swap_attempt`, `deadlock_cycle`. Drop `malfunction`, `agent_done`
  and `overdue_arrival` — they are single-train events and are already served by
  `hmi/impact` and the notifications feed.
- Merge conflicts that share a `position` into one group, unioning `handles`.
- Cap the horizon: `run_branch(overrides={}, max_steps=…)` with a modest value
  (start at 50, the existing default) so one call stays cheap.
- Return `[]` — not an error — when the session has no conflicts ahead.
- Wrap the run in `try/except` and return `[]` on failure, the way `get_impact`
  does. A forecast failure must never break the panel.

**Cost:** `run_branch` forks and simulates. Do not call it per request without
protection — memoise the result per `(session_id, current_step)` so repeated
polls within one step are free. Do not touch the scenario-refresh throttling in
`scenario-panel`, and do not touch trajectory compression in
`session.store.ts _recordTrajectory` (CLAUDE.md guardrail).

**Tests:** add to `backend/tests/`. At minimum: a session with a known contention
returns a group whose `handles` are all real agent handles; a conflict-free
session returns `[]`; single-train kinds are filtered out.

---

## TASK 2 — Frontend: build the packages from those groups

### 2a. Fetch

Add the call to `api.service.ts` alongside the other `hmi/*` calls, and a signal
in `SessionStore` next to `impact()` — follow whatever polling/refresh pattern
`impact()` already uses. Do not invent a second mechanism.

### 2b. Derive the packages

Replace the *source* of packages, not the impact model.

In `action-packages.ts`, keep the `ActionPackage` interface, `TrainCategory` and
the category/weight lookups. Add a function that turns one contention group into
three packages:

```ts
buildPackages(handles: number[], nameOf: (h: number) => string, ctx): ActionPackage[]
```

The three cards must stay three, because the widget's whole interaction is
"compare coordinated orders and edit one". Give each a different, *stateable*
dispatch rationale — the operator has to be able to say why B differs from A:

- **A** — by service weight, long-distance first (the current `TRAIN_WEIGHT`
  table in `impact-prediction.ts:58` already encodes this ranking). `recommended: true`.
- **B** — by earliest scheduled arrival first.
- **C** — by current delay, most-delayed first.

Write the `rationale` string per package to match, in the register the existing
three use ("Clears the through-running services first, regional traffic follows.").
If two orderings come out identical for a given group, keep both cards and let
them show the same figures — do not silently drop a card, and do not fabricate a
difference.

Train names come from `TrainIdentityService.nameByHandle` — never from
`SERVICE_ROSTER` directly. That is what makes the chips real.

### 2c. Wire it into the component

`combined-actions.component.ts`:

- `packages` (line 165) and the `tradeoffPoints` loop (line 233) currently read
  the `ACTION_PACKAGES` constant. Both must read the derived signal instead.
- Tighten `bound` (line 208) to the real invariant: **every** train named by
  **every** package resolves through `handleFor()`. With derived packages this
  should always hold — keep the guard anyway so a future regression shows up as
  a disabled panel rather than as phantom chips.
- Leave `disrupted` (line 190) alone in behaviour: the panel still only offers
  packages when the network gives a reason. Extend its condition to also count a
  contention group, so the panel appears for a pure single-track conflict with no
  malfunction — which is exactly the PF–CH case.
- Update the provenance wording (line 214). The current text says the packages
  are "fixtures whose services are bound to this session's trains". After this
  change that is false: say the trains and the contention are real and the delay
  and energy figures are modelled. Keep the sentence one line, keep the tone.

### 2d. What happens to the numbers — read this carefully

`SEEDED` (`impact-prediction.ts:77`) keys on the exact order string, e.g.
`'IC_703>ICE_42>RE_18>S8_214'`. Derived orders will usually **not** match a
seeded key, so figures come from the positional model instead. That is expected
and acceptable for Stufe 1.

Therefore: **do not edit `impact-prediction.ts`.** Leave `SEEDED`, `TRAIN_WEIGHT`
and `TRAIN_RESTART_KWH` exactly as they are — the seeded entries still serve the
spec's acceptance walkthrough (§6) and `impact-prediction.spec.ts`. Removing them
breaks green tests for no gain.

Do not change `ImpactPredictionService` either. It is the seam Stufe 2 will use;
leave it untouched.

---

## Guardrails (CLAUDE.md — violating these fails the task)

- **No hardcoded colours.** No raw hex / `rgb()` / `rgba()` in SCSS or templates.
  Use Lyne semantic tokens (`--sbb-color-*`), the app tokens in `styles.scss`
  (`--app-*`, `--color-*`), or `light-dark(a, b)`. New colour ⇒ new token.
- **Do not build a solver.** No scheduler, no CBS, no PP, no optimiser. If you
  find yourself writing one, you have left the scope of this task.
- Keep mode semantics in the `InteractionMode` union — no parallel flags.
- Do not touch trajectory compression (`session.store.ts _recordTrajectory`), the
  scenario-refresh throttling in `scenario-panel`, or the
  `_recoverPolicyAndRetry*` fallbacks.
- Frontend stays Angular standalone + signals + SBB Lyne; backend stays FastAPI +
  Flatland. Prefer gating presentation in the frontend over reshaping payloads.
- Keep existing tests green (`backend/tests/`, the frontend `*.spec.ts`).

## Acceptance criteria

Checkable, in this order:

1. **The defect is gone.** Session on preset `pf-ch-wn-wal-conflict` (3 trains):
   every chip on every card names a train present in the Fahrplan, and no chip
   resolves to `handleFor() === null`.
2. **The 8-train case still works.** Guided Demo still shows three packages, and
   every existing frontend and backend test passes unchanged.
3. **Determinism holds** (spec §6, Q2 calibrated trust): the same order always
   yields the same figures — reset, re-apply the same edit, same numbers.
4. **No invented contention.** With a conflict-free network the panel keeps its
   current empty state ("Netz läuft nach Plan — keine koordinierte Aktion nötig.").
   Never synthesise a package to fill the panel.
5. **New coverage exists:** a backend test for the endpoint's filtering and
   grouping, and a frontend spec asserting a derived package contains only
   handles present in the session.

## Explicitly out of scope

These are separate flagged rows in the spec's §4 table. Do not start them, and do
not partially stub them:

- Real re-solve of a human priority order (PP/CBS via `AI4REALNET/flatland-blackbox`)
- `Apply` actually committing the order to the planner
- Decision-log entry per applied/modified package
- Measured energy KPI

If a decision inside this task seems to require one of them, stop and write the
question into the spec's §8 instead of building around it.

---

## Correction, 2026-08-27 — raised by GLM 5.2 during the first round

**The brief was wrong about the detector.** It cites
`ConflictDetectionCallbacks.get_conflicts()` (`conflict_detector.py:193`) as a
working conflict source. It is not: all six `_detect_*` methods are `pass`
(`conflict_detector.py:172-190`, marked "filled in Part 2/3"), so `get_conflicts()`
always returns `[]`. Building the endpoint literally as written would have
produced a permanently empty panel — the phantom chips gone only because nothing
renders at all.

**Resolution:** fill the stubs. "Do not write a new conflict detector" was aimed
at a *parallel* system; completing the existing one honours that. Scope is bound
to the three kinds the endpoint filters to — `_detect_blocked`, `_detect_swap`,
`_detect_deadlock_cycles`. `_detect_malfunctions`, `_detect_done` and
`_detect_overdue` stay stubs: this brief drops those kinds as single-train events
already served by `hmi/impact` and the notifications feed.

The scaffolding is present and must not be rebuilt: `blocked_threshold`
(default 3), `_stopped_streak`, `_blocked_emitted` (anti-flood), `_snapshots`.

**Do not treat `tests/test_conflict_detector.py` as the specification.** Verified
by running it: `test_blocked_threshold_emits_event` *skips*, and its skip message
blames Flatland when the real cause is the empty stub;
`test_blocked_emitted_only_once_per_streak` and
`test_agent_done_emitted_once_per_agent` pass vacuously, because "at most one
event" is trivially true of zero events. They describe the shape
(`info["consecutive_stops"]`, one event per streak), not the behaviour. Real
assertions have to be added.

`deadlocked_agents()` (`scenario_runner.py:61`) works, but catches only
face-to-face deadlocks — too narrow as the sole source. Useful as a test
cross-check: where it fires, `_detect_deadlock_cycles` must report too.

**Cost of the correction:** filling three detectors is bounded extra work inside
this task, not a new task. It is also the reason the task's premise held up —
the seam was right, the source behind it was hollow.
