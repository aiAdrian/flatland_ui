# Widget E1 — the contention payload grows a conflict window — delegated work brief

> **Status:** Written 2026-08-27, **not yet delegated**. Hold it until the Stufe-1
> job ([`widget-e1-live-conflicts-prompt.md`](widget-e1-live-conflicts-prompt.md),
> delegated to GLM 5.2) has landed and been reviewed — this brief builds directly
> on the endpoint that job creates and is meaningless before it exists.
>
> Kept as an archive artifact to reflect on the delegation later (what was asked
> vs. what was built) and on AI-usage patterns.
>
> **Why it exists:** we are keeping *two* Combined Actions variants side by side
> as separate panel types, because comparing interface variants is what this
> playground is for. The second variant models a conflict as a queue and needs
> quantities the Stufe-1 payload does not carry. This brief adds them — to the
> same endpoint, from data the same forward run already produces.
>
> **Decision to make inside this task:** the forecast horizon (see "The horizon
> decision" below). It is written up in the spec's §8. Do not settle it silently.

---

## Task: Extend `/hmi/contentions` with a per-train conflict window

You are working in the Flatland Dispatcher repo (AI4REALNET), branch `explore_db`.
Backend: FastAPI + Flatland-RL. Frontend: Angular standalone + signals + SBB Lyne.

**Read first:** `CLAUDE.md`, then `docs/plans/widget-e1-combined-actions.md`
(§4's flagged table, §8's open questions — the last bullet is this task's
decision), then `docs/plans/widget-e1-live-conflicts-prompt.md` (the preceding
task, whose endpoint you are extending).

### Where this starts

The preceding task built:

```
GET /{session_id}/hmi/contentions
→ [ { "step": 14, "position": [2, 96], "kind": "blocked", "handles": [0, 1, 2] } ]
```

It is served from a no-override forward run —
`TrajectoryBranchRunner.run_branch(overrides={})`
(`backend/app/core/scenario_runner.py:206`) — memoised per
`(session_id, current_step)`.

That payload identifies the *window*: who contends, where, when, why. A second
Combined Actions variant needs the *quantities* inside it, because it computes
outcomes from a single-server queue rather than from a weight table:

```
delay_k = max(0, entryDelay_k + Σ headway_before_k − slack_k)
```

Its `ConflictWindow` / `TrainFacts` shape lives in
`frontend/src/app/core/combined-actions/model.ts` on branch
`roman/director-strategies-shift-review` — read it before designing the payload,
and match its field names so the adapter stays trivial.

### Missing today

| Needed | Status |
|---|---|
| `location`, `reason`, `horizonMinutes` | derivable from `position`, `kind`, `step` |
| per-train `agentHandle`, `service` | have (`handles` + `TrainIdentityService`) |
| per-train `entryDelay` | **missing** |
| per-train `headway` | **missing** |
| per-train `slack` | **missing** |
| `baselineOrder` | **missing** |

---

## TASK 1 — Derive the four missing quantities

**Everything below comes from data the existing forward run already produces.
Do not add a second simulation pass, and do not write a new detector.**

`BranchResult` (`backend/app/core/scenario_runner.py:139`) returns `snapshots`
alongside `conflicts`. A snapshot is one step
(`backend/app/core/conflict_detector.py:151`):

```python
{"step": 14, "agents": {0: {"pos": (2, 96), "dir": 1, "state": "MOVING", "malfunction": 0}, …}}
```

Derive, per contention group:

- **`baselineOrder`** — the order in which the group's handles first occupy (or
  pass) the contended `position` across the snapshot sequence. This is the
  passing order the timetable produces when nobody intervenes, which is exactly
  what the queue model re-slots against.
- **`headway`** (per train) — how many steps that handle occupies the window.
  Count consecutive snapshots where its `pos` is the contended cell or, better,
  within the window you define. State your window definition in a docstring;
  a single cell is acceptable for a first cut if you say so.
- **`entryDelay`** (per train) — the train's delay on entering the window. Reuse
  the existing formula rather than inventing one: `serializer.py:118-128`
  (`delay = elapsed − latest_arrival` when overdue and state != DONE, else 0).
  `BranchResult.agent_outcomes` already carries a per-handle `delay` — check
  whether it answers this directly before computing anything.
- **`slack`** (per train) — the buffer the train can absorb before it is late.
  `earliest_departure` and `latest_arrival` are on the agent
  (`serializer.py:111-112`); slack is the room between the run's arrival step and
  `latest_arrival`. If an agent carries per-waypoint timetables
  (`waypoints_earliest_departure` / `waypoints_latest_arrival`,
  `serializer.py:155-156`), prefer the waypoint nearest the contended position —
  and say in the docstring which you used.

Where a quantity genuinely cannot be derived for a train (no timetable, agent
never reaches the window inside the horizon), emit `null` for that field and a
short `unavailable_reason` on the train entry. **Never emit a plausible-looking
zero for something you did not compute** — a fabricated zero is worse than a
missing field, because nothing downstream can tell it apart from a real one.

## TASK 2 — Shape the payload

Extend the existing response; do not add a second endpoint.

```json
[
  {
    "step": 14,
    "position": [2, 96],
    "location": "WN",
    "kind": "blocked",
    "reason": "blocked",
    "horizonMinutes": 50,
    "handles": [0, 1, 2],
    "baselineOrder": [1, 0, 2],
    "trains": [
      { "agentHandle": 1, "entryDelay": 3, "headway": 4, "slack": 6 },
      { "agentHandle": 0, "entryDelay": 0, "headway": 3, "slack": 2 },
      { "agentHandle": 2, "entryDelay": 7, "headway": 3, "slack": 0,
        "unavailable_reason": null }
    ]
  }
]
```

Rules:

- `handles` stays, unchanged, so the Stufe-1 consumer keeps working untouched.
  This must be a purely **additive** change — the first variant's packages must
  render identically before and after, and its tests must pass unmodified.
- `location`: a station name where one is known (the scene carries named
  stations — see `stations_from_scene` / `station_aware_env.py`), else the cell
  as a string. Never invent a name.
- **Service names stay in the frontend.** Return `agentHandle`, never `IC_703`.
  The name mapping is `TrainIdentityService.nameByHandle` and it is authored, not
  scenario data (see the E1 spec §8). The backend must not learn about service
  names.
- Times are in **steps** at the API boundary. `MINUTES_PER_STEP = 1` is the
  demo's step↔minute convention and it lives in the frontend, in one place. Do
  not convert server-side.

## TASK 3 — The horizon decision

**This is the part to think about, not to code around.**

Three surfaces will forecast the same contention over three different spans:

- this endpoint — `run_branch(max_steps=50)`, inherited from the Stufe-1 brief
- the second Combined Actions variant — its own `horizonMinutes` per window
- Learning Moments (`backend/app/core/learning_moments.py`, branch
  `roman/director-strategies-shift-review`) — **to the end of the episode**, at a
  measured 3–4 s per branch

So the same conflict can show different numbers in two panels on one screen, for
a reason the operator cannot see. That is a direct hit on Q2 (calibrated trust).

What to do in this task:

1. Make the horizon **one named parameter**, defined in one place, not a literal
   repeated at three call sites. Name it so it reads the same wherever it
   surfaces.
2. Return it in the payload (`horizonMinutes` above) so any panel can state what
   it forecast over. A panel showing a forecast figure must be *able* to say the
   span; whether it does is a UI decision, not yours.
3. **Do not** change Learning Moments' episode-end horizon in this task — it is
   on another branch and is a separate product decision. Write what you found
   into the E1 spec's §8 instead (the last bullet there is already about this).

If choosing a default forces a product judgement — e.g. whether the horizon is
pinned repo-wide or set per scenario — pick the smaller, reversible option (one
constant, changeable in one place), state the choice in the docstring, and note
the open question in §8. Do not build a configuration system for it.

---

## Guardrails (CLAUDE.md — violating these fails the task)

- **Additive only.** The Stufe-1 consumer and its tests must keep working with
  no edits. If you find yourself changing the first variant's code, stop.
- **No second simulation pass.** One `run_branch` per `(session_id, step)`,
  memoised as the preceding task established. Forking and stepping is the
  expensive thing here; doubling it to fill a payload is not acceptable.
- **Do not build a solver.** No scheduler, no CBS, no PP, no optimiser.
- Keep `InteractionMode` as the single mode flag — three values, no fourth. The
  second Combined Actions variant is a **panel type**, not a mode.
- **No hardcoded colours** in any frontend file you touch. Lyne semantic tokens
  (`--sbb-color-*`) or the app tokens in `styles.scss`.
- Do not touch trajectory compression (`session.store.ts _recordTrajectory`), the
  scenario-refresh throttling in `scenario-panel`, or the
  `_recoverPolicyAndRetry*` fallbacks.
- Keep existing tests green (`backend/tests/`, frontend `*.spec.ts`).

## Acceptance criteria

1. **Additive proven, not assumed:** the first Combined Actions variant renders
   the same packages with the same figures before and after this change, and its
   tests pass unmodified.
2. On preset `pf-ch-wn-wal-conflict`, a contention group comes back with a
   `baselineOrder` that is a permutation of its `handles`, and per-train
   `entryDelay` / `headway` / `slack` that are either numbers or explicit `null`
   with a reason — no silent zeros.
3. **Determinism:** the same session at the same step returns byte-identical
   payloads across repeated calls. (The memoisation should make this trivially
   true; assert it anyway, because a non-deterministic forecast is the failure
   this whole widget family cannot survive.)
4. The horizon appears exactly once as a named constant, is returned in the
   payload, and its value is stated in a docstring with the reasoning.
5. New backend tests cover: `baselineOrder` derivation from a known snapshot
   sequence, `slack` when a timetable is present and when it is absent, and the
   `null` + reason path.

## Explicitly out of scope

- Consuming this payload in either Combined Actions variant (that is the port,
  a separate task)
- Porting `roman/director-strategies-shift-review` — the panel-type split, the
  `problem-overview` / `learning-moment` registration, the layout presets
- Real re-solve of a human priority order (PP/CBS via `flatland-blackbox`)
- `Apply` committing an order to the planner; decision-log entries
- Changing Learning Moments' horizon

If a decision inside this task seems to require one of these, stop and write the
question into the E1 spec's §8 instead of building around it.
