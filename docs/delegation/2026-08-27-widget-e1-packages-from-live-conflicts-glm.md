# Delegation record — Widget E1: packages from live conflicts

**Date:** 2026-08-27 · **Delegated to:** GLM 5.2 (open-weight, selected in Claude)
· **Review + build + verify:** Claude (Fable 5) · **Branch:** `explore_db`

Status: archive artifact. The brief was handed verbatim to the building agent.
The live spec is `docs/plans/widget-e1-combined-actions.md` — update that (not
this file) as the feature lands. Kept to reflect on the delegation later:
what was asked vs. what was built, and the AI-usage pattern (a brief built on
a premise the codebase contradicted, and the decision that resolved it).

Scope decision baked in: **Stufe 1 only** — packages derived from live
conflicts, impact figures still from the deterministic model. The real PP/CBS
re-solve stays out (see "Explicitly out of scope" in the brief).

---

## The brief (verbatim)

> Widget E1 — packages from live conflicts — delegated work brief
> Status: Delegated 2026-08-27 to GLM 5.2 (open-weight, selected in Claude) in
> a parallel session. Kept as an archive artifact to reflect on the delegation
> later (what was asked vs. what was built) and on AI-usage patterns.
>
> Why now: the PF–CH scenarios (3 trains) exposed a defect the 8-train demo hid
> — the action cards name trains the session does not contain. See "The defect"
> below.
>
> Scope decision baked in: this is Stufe 1 only — packages derived from live
> conflicts, impact figures still from the deterministic model. The real PP/CBS
> re-solve stays out (see "Explicitly out of scope").
>
> This is the verbatim brief handed to the building agent. The live spec is
> widget-e1-combined-actions.md; update that (not this file) as the feature lands.

### Task: Derive Combined Actions packages from the session's real conflicts

You are working in the Flatland Dispatcher repo (AI4REALNET), branch explore_db.
Frontend: Angular standalone + signals + SBB Lyne. Backend: FastAPI + Flatland-RL.

Read first: CLAUDE.md, then docs/plans/widget-e1-combined-actions.md (especially
§4's flagged table and §8's open questions — this task turns one flagged row
green and deliberately leaves the others alone).

#### The defect

Load the scenario preset pf-ch-wn-wal-conflict (3 trains: handles 0, 1, 2). The
Combined Actions panel shows three cards whose chips read:

```
A: IC_703, ICE_42, RE_18, S8_214
B: EC_91,  IC_703, RB_51,  ICE_42
C: IR_227, RE_18,  TGV_12, S8_214
```

Only IC_703, ICE_42, RE_18 exist. The other five are phantoms.

Two hardcoded lists produce this:

- SERVICE_ROSTER — frontend/src/app/core/train-identity.service.ts:26 — eight
  authored names; the i-th train by handle gets the i-th name. Three trains ⇒
  five names stay unassigned.
- ACTION_PACKAGES — frontend/src/app/core/combined-actions/action-packages.ts:35
  — three authored packages that reference names across the whole roster,
  independent of the session.

The existing guard does not catch it: bound at
frontend/src/app/features/combined-actions/combined-actions.component.ts:208 is
`Object.keys(handleByTrain()).length > 0` — "is there any train", not "does
every referenced train exist". `handleFor(train)` (same file, ~line 218)
returns null for the phantoms, so the map/ZWL overlay silently cannot point at
them.

The 8-train Guided Demo assigns the whole roster, so every chip resolves and
the defect is invisible there. Do not treat this as a regression from the PF–CH
scenarios — it is a fixture limitation they exposed.

#### The goal

Packages are built from the trains actually contending in this session, so
every chip resolves to a real handle. Impact figures keep coming from the
existing deterministic model.

**TASK 1 — Backend: expose the conflicts ahead**

Reuse the existing trajectory machinery. Do not write a new conflict detector.

TrajectoryBranchRunner (backend/app/core/scenario_runner.py:183) already forks
the env, runs forward and collects conflicts through
ConflictDetectionCallbacks. run_branch() (scenario_runner.py:206) returns a
BranchResult (scenario_runner.py:139) whose conflicts: List[Conflict] field is
exactly what this task needs. A no-override run — run_branch(overrides={}) —
is the predicted course of the network from the current step, which is the
right semantics: a coordinated action answers an upcoming contention, not a
past one.

Conflict (backend/app/core/conflict_detector.py:47):

```
kind: ConflictKind          # "blocked" | "malfunction" | "swap_attempt"
                            # | "deadlock_cycle" | "agent_done" | "overdue_arrival"
step: int
agents: List[int]           # involved agent handles
position: Optional[Tuple[int, int]]
info: Dict[str, Any]
```

Build a new endpoint, next to the existing HMI endpoints in
backend/app/api/hmi.py (see get_impact at hmi.py:117 for the shape, session
lookup and error handling to copy):

`GET /{session_id}/hmi/contentions`

Returns a list of contention groups, most urgent (lowest step) first:

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
- Keep only kinds that name two or more contending agents: blocked,
  swap_attempt, deadlock_cycle. Drop malfunction, agent_done and
  overdue_arrival — they are single-train events and are already served by
  hmi/impact and the notifications feed.
- Merge conflicts that share a position into one group, unioning handles.
- Cap the horizon: run_branch(overrides={}, max_steps=…) with a modest value
  (start at 50, the existing default) so one call stays cheap.
- Return [] — not an error — when the session has no conflicts ahead.
- Wrap the run in try/except and return [] on failure, the way get_impact
  does. A forecast failure must never break the panel.
- Cost: run_branch forks and simulates. Do not call it per request without
  protection — memoise the result per (session_id, current_step) so repeated
  polls within one step are free. Do not touch the scenario-refresh throttling
  in scenario-panel, and do not touch trajectory compression in
  session.store.ts _recordTrajectory (CLAUDE.md guardrail).

Tests: add to backend/tests/. At minimum: a session with a known contention
returns a group whose handles are all real agent handles; a conflict-free
session returns []; single-train kinds are filtered out.

**TASK 2 — Frontend: build the packages from those groups**

2a. Fetch — Add the call to api.service.ts alongside the other hmi/* calls, and
a signal in SessionStore next to impact() — follow whatever polling/refresh
pattern impact() already uses. Do not invent a second mechanism.

2b. Derive the packages — Replace the source of packages, not the impact model.

In action-packages.ts, keep the ActionPackage interface, TrainCategory and the
category/weight lookups. Add a function that turns one contention group into
three packages:

`buildPackages(handles: number[], nameOf: (h: number) => string, ctx): ActionPackage[]`

The three cards must stay three, because the widget's whole interaction is
"compare coordinated orders and edit one". Give each a different, stateable
dispatch rationale — the operator has to be able to say why B differs from A:

- A — by service weight, long-distance first (the current TRAIN_WEIGHT table in
  impact-prediction.ts:58 already encodes this ranking). recommended: true.
- B — by earliest scheduled arrival first.
- C — by current delay, most-delayed first.

Write the rationale string per package to match, in the register the existing
three use ("Clears the through-running services first, regional traffic
followes."). If two orderings come out identical for a given group, keep both
cards and let them show the same figures — do not silently drop a card, and do
not fabricate a difference.

Train names come from TrainIdentityService.nameByHandle — never from
SERVICE_ROSTER directly. That is what makes the chips real.

2c. Wire it into the component — combined-actions.component.ts:

- packages (line 165) and the tradeoffPoints loop (line 233) currently read
  the ACTION_PACKAGES constant. Both must read the derived signal instead.
- Tighten bound (line 208) to the real invariant: every train named by every
  package resolves through handleFor(). With derived packages this should
  always hold — keep the guard anyway so a future regression shows up as a
  disabled panel rather than as phantom chips.
- Leave disrupted (line 190) alone in behaviour: the panel still only offers
  packages when the network gives a reason. Extend its condition to also count
  a contention group, so the panel appears for a pure single-track conflict
  with no malfunction — which is exactly the PF–CH case.
- Update the provenance wording (line 214). The current text says the packages
  are "fixtures whose services are bound to this session's trains". After this
  change that is false: say the trains and the contention are real and the
  delay and energy figures are modelled. Keep the sentence one line, keep the
  tone.

2d. What happens to the numbers — read this carefully

SEEDED (impact-prediction.ts:77) keys on the exact order string, e.g.
'IC_703>ICE_42>RE_18>S8_214'. Derived orders will usually not match a seeded
key, so figures come from the positional model instead. That is expected and
acceptable for Stufe 1.

Therefore: do not edit impact-prediction.ts. Leave SEEDED, TRAIN_WEIGHT and
TRAIN_RESTART_KWH exactly as they are — the seeded entries still serve the
spec's acceptance walkthrough (§6) and impact-prediction.spec.ts. Removing
them breaks green tests for no gain.

Do not change ImpactPredictionService either. It is the seam Stufe 2 will use;
leave it untouched.

#### Guardrails (CLAUDE.md — violating these fails the task)

- No hardcoded colours. No raw hex / rgb() / rgba() in SCSS or templates. Use
  Lyne semantic tokens (--sbb-color-*), the app tokens in styles.scss (--app-*,
  --color-*), or light-dark(a, b). New colour ⇒ new token.
- Do not build a solver. No scheduler, no CBS, no PP, no optimiser. If you find
  yourself writing one, you have left the scope of this task.
- Keep mode semantics in the InteractionMode union — no parallel flags.
- Do not touch trajectory compression (session.store.ts _recordTrajectory), the
  scenario-refresh throttling in scenario-panel, or the _recoverPolicyAndRetry*
  fallbacks.
- Frontend stays Angular standalone + signals + SBB Lyne; backend stays
  FastAPI + Flatland. Prefer gating presentation in the frontend over
  reshaping payloads.
- Keep existing tests green (backend/tests/, the frontend *.spec.ts).

#### Acceptance criteria

Checkable, in this order:

1. The defect is gone. Session on preset pf-ch-wn-wal-conflict (3 trains):
   every chip on every card names a train present in the Fahrplan, and no chip
   resolves to handleFor() === null.
2. The 8-train case still works. Guided Demo still shows three packages, and
   every existing frontend and backend test passes unchanged.
3. Determinism holds (spec §6, Q2 calibrated trust): the same order always
   yields the same figures — reset, re-apply the same edit, same numbers.
4. No invented contention. With a conflict-free network the panel keeps its
   current empty state ("Netz läuft nach Plan — keine koordinierte Aktion
   nötig."). Never synthesise a package to fill the panel.
5. New coverage exists: a backend test for the endpoint's filtering and
   grouping, and a frontend spec asserting a derived package contains only
   handles present in the session.

#### Explicitly out of scope

These are separate flagged rows in the spec's §4 table. Do not start them, and
do not partially stub them:

- Real re-solve of a human priority order (PP/CBS via AI4REALNET/flatland-blackbox)
- Apply actually committing the order to the planner
- Decision-log entry per applied/modified package
- Measured energy KPI

If a decision inside this task seems to require one of them, stop and write the
question into the spec's §8 instead of building around it.

---

## What actually happened (review + build, 2026-08-27)

Recorded so the "what I asked for" vs. "what got built" diff is explicit, and
so the AI-usage pattern — a brief built on a premise the code contradicted —
is visible later.

### The premise that didn't hold

Task 1 said: *"Reuse the existing trajectory machinery … `run_branch()` returns
a `BranchResult` whose `conflicts` field is exactly what this task needs."*

It did not. `ConflictDetectionCallbacks`'s six `_detect_*` methods were empty
`pass` stubs (the class docstring said "filled in Part 2/3" — never done; the
detector had been stubbed since its introduction at `ccd1420`). Verified
empirically: `run_branch(overrides={}, max_steps=50)` returned `conflicts: []`
on every scenario. The existing detector tests stayed green only *vacuously*
— `test_agent_done…` passed because `[]→0==0`, and `test_blocked_threshold…`
*skipped* whenever no event fired. So an endpoint built literally per the brief
would always return `[]`, the widget would never show packages, and the
"defect fix" would be vacuous (the panel just never appears).

This surfaced only by running the code, not by reading the brief or the tests.
A delegate that built to spec without probing would have shipped a no-op.

### The resolution (user decision, three refinements)

The user chose to **complete the existing detector** rather than build around
the stub, with three refinements:

1. Fill only `_detect_blocked`, `_detect_swap`, `_detect_deadlock_cycles` —
   the three kinds the endpoint filters on. The other three stay no-ops.
2. Use the existing scaffold (`blocked_threshold`, `_stopped_streak`,
   `_blocked_emitted`, `_snapshots`); only the bodies were missing.
3. The tests were not a specification — one skipped, two passed empty. Real
   assertions were added.

### A second premise gap the refinement did not anticipate

Filling `_detect_blocked` with the obvious "the train in the next cell is the
blocker" produced single-handle events on PF–CH: the three trains freeze ~25
cells apart on the shared Wal single-track and never become face-to-face
within the 50-step forecast. The endpoint's 2+-handles rule would have dropped
all three → the widget still empty. The blocker set was therefore widened to
**path-overlap contenders** (remaining shortest path via the distance-map
gradient), still driven by the streak scaffold. This is detection, not a
solver — it is not on the brief's out-of-scope list, and it is the only thing
that achieves the brief's stated goal on PF–CH. Recorded in spec §8.

### Deviations from the brief's letter (all noted in the live spec / PR)

- **Group by shared handle, not by position.** The brief said "merge conflicts
  that share a position"; with multi-agent events at different positions that
  would emit duplicate groups, so the endpoint merges by handle-connected
  components (union-find). Same intent (one group per contention), correct
  generalisation.
- **Presentation cap to 4 trains.** On the 15-agent Guided-Demo net a
  contention group can name all 15 (broad mainline path overlap). A 15-chip
  package breaks the panel and is not the interaction the widget supports.
  The frontend caps to the 4 most-delayed trains — real handles from the
  contention, no phantoms introduced. PF–CH (3 trains) is under the cap.

### Result

All five acceptance criteria met. Full backend suite: 402 passed, 0 failed.
Frontend: 23/23 combined-actions specs pass; `ng build` clean. Spec §4 row
"Packages derived from live conflicts" marked green; §8 carries the design
notes. Nothing on the out-of-scope list was touched.

---

## Follow-up tasks (2026-08-28)

Three follow-ups the same delegation spawned, recorded for the same
asked-vs-built diff.

### Follow-up 3 — surface the forecast horizon (landed)

The spec's §8 flagged the horizon as "not yet one decision": the contentions
endpoint caps `run_branch` at 50 steps while other surfaces use other spans,
so the same conflict could show different numbers for an invisible reason — a
direct Q2 (calibrated trust) hit. Resolved by **surfacing each surface's own
horizon on its panel, in one shared unit** — not by pinning one repo-wide
constant (that would have erased strategy-forecast's load-shrinking
`horizonMinutes`, which is a reliability statement, not a budget). The endpoint
now returns `horizonSteps` (always present, even with no contention); the
panel renders it in minutes via the existing `MINUTES_PER_STEP = 1`
(`combined-actions-preview.ts:26`) — the single step↔minute meeting point, no
second constant. The **budget vs reliability** distinction is written into §8
so "pinned vs per scenario" stays a later, cheap, one-line call once Learning
Moments actually coexists on `explore_db`.

### Follow-up 1+2 — the four quantities + additive payload (landed)

Derive `baselineOrder`, `headway`, `entryDelay`, `slack` per handle — all from
the one forecast `result` (no second `run_branch`). Key decisions, each a place
the brief's first framing would have produced a worse answer:

- **The window is the path-overlap, not the conflict position.** `_contenders`
  already computed the pairwise path-overlap to decide contention and threw it
  away; carried it onto the event as `info["contended_cells"]` instead. The
  window must be the same path-overlap that defined the contention, else a
  group and its window are built by different criteria and a train can land in
  a group whose window it never enters. `baselineOrder`/`headway` measure
  against that union. (The first three window-definition options — conflict
  cell, conflict cell + predecessor, conflict cell's row — were rejected: on
  PF–CH the trains freeze ~25 cells apart and never reach the same cell in the
  50-step horizon, so all three would have made nearly every handle null. A
  path-overlap window is non-empty precisely for the contending trains.)
- **`entryDelay` is reused, not re-derived.** `BranchResult.agent_outcomes[h]["delay"]`
  already computes the exact `serializer.py:118-128` formula (`elapsed - latest`
  when overdue, else 0). The brief's "check whether agent_outcomes already
  answers it" check: it does — read directly, nothing new invented.
- **`slack` at the waypoint nearest the contended cell.** With waypoint
  timetables (pf-ch-corridor-stops has them; pf-ch-wn-wal-conflict does not),
  slack is measured at the stop closest to where the contention bites, not at
  the journey end. Manhattan distance on the grid; documented in the docstring.
- **No silent zeros.** A quantity not derivable in the horizon is `null` +
  `unavailable_reason` (e.g. `never_enters_window`, `no_latest_arrival`,
  `no_waypoints`). A fabricated zero is worse than a missing field.
- **Additive payload, `handles` unchanged.** The four quantities ride in a
  `perHandle` block alongside `window` and `location`; `handles` stays a flat
  int list so the existing Combined Actions variant keeps working. `location`
  is a station name where the window overlaps one (from the infrastructure
  scene), else the cell — never invented. Train names stay frontend: handles
  returned as `agentHandle`, never a service name. Times in steps at the API
  boundary; the frontend converts.

The `_group_contentions` two-pass fix (union everything, then key by the
settled root — a root found mid-union goes stale) was already on disk from a
parallel edit and was preserved, not overwritten.

Verified on pf-ch-corridor-stops (the only preset whose trains carry
intermediate stops, against which slack is measurable): 58 touched/core
backend tests pass; the null-path, the slack-reason variety, the entryDelay↔
serializer equivalence, and the additive-`handles` contract all pinned by
new tests in `test_hmi_contentions_derivation.py`.