# Plan — Proposal agents: a base algorithm with small agents on top

> **Status:** stage 1 in progress · started 2026-09-15 · owner: Daniel Boos
> **Related:** [colearning-monte-carlo-interviews-tour.md](colearning-monte-carlo-interviews-tour.md) ·
> [widget-b1-whatif-compare.md](widget-b1-whatif-compare.md) ·
> [recommender-roadmap.md](recommender-roadmap.md) ·
> [flatland-ecosystem-reuse-plan.md](flatland-ecosystem-reuse-plan.md)

## 1. Idea

The timetable is a skeleton — arrivals and intermediate stops — not a route. A
**base algorithm** (the TMS's main planner) plans routes that meet it. When a
disturbance breaks that plan, **small agents** propose local deviations: another
route, another priority into a single-track section, how long a train waits. The
**human** accepts one, takes their own, or rejects all. What was accepted or
overridden is recorded and, **later and offline**, improves the base algorithm.

This is the Co-Learning loop of the thesis (flow step 9, "input for the TMS
algorithm") and the consortium's own pattern: in
[`AI4REALNET/T3.4-with-HMI`](https://github.com/AI4REALNET/T3.4-with-HMI) the
controller stays the base decision layer and high-level decisions are injected at
runtime; [`AI4REALNET/Tokener`](https://github.com/AI4REALNET/Tokener) combines
CBS+PP planning with token-based interaction.

One surface for all of it: **Plan / KI / Mensch** — the plan as it would run on,
the agents' proposal, the human's choice — each with the same outcome figures.

## 2. Why in stages

A learning agent on the Walensee corridor (three trains, one conflict) would learn
next to nothing, and training infrastructure costs time the thesis does not have.
The interface, the display and the data capture can be right long before a trained
agent exists. So: first make the display honest, then put a planner behind the
proposal seam, then swap learning agents in behind the same seam.

## 3. Stages

### Stage 1 — Honest forecasts (≈ 1 day)

**Problem (measured 2026-09-15).** Plan-driven sessions (policy `plan`, e.g. the
Walensee scenarios) are forecast with a proxy: the plan policy is not registered for
branches (`supports_scenarios=False`, `PlanPolicy` needs the trainruns), so the map
forecast (`api/hmi.py _rollout_baseline`) and the what-if (`api/overrides.py
_policy_factory_for_session`) silently fall back to deadlock avoidance. For ICE_42
from step 30 the what-if "AI plan" stays on the lower track and never arrives, while
the real train switches tracks at column 95 and arrives at step 70; the "My plan"
branch with *Left* is identical. And the what-if delay counts only overdue steps
against very wide latest-arrival windows, so different routes read as "no
measurable change".

**Change.**
- A plan branch factory: branches of a plan-driven session roll out the session's
  own trainruns (`PlanPolicy`), in both the forecast and the what-if — the same move
  `director_replay_factory` makes for Director sessions.
- Branch outcomes carry the **arrival step** per train, and the what-if reports
  **delay against the plan** (planned arrival from the trainruns) next to the
  existing figures.
- The what-if widget shows arrival and delay vs. plan per branch.

**Affects the User Study 2 conditions** (same scenarios): their map forecast and
what-if become correct. Worth telling Adrian before the next study run.

**Done when:** for a plan session the forecast line and the what-if baseline of a
train follow the plan's route; a route choice that changes a train's arrival shows
a different arrival step; backend tests cover the plan factory and the arrival step.

**Status (2026-09-15): done in code.**
- `plan_branch_factory` / `planned_arrival_steps` in `policies/plan_policy.py`, used by
  `api/hmi.py _rollout_baseline` and `api/overrides.py _policy_factory_for_session`.
- `TrajectoryBranchRunner` records `arrival_step`; the what-if `train` block adds
  `arrival_step`, `planned_arrival`, `delay_vs_plan`, the response `baseline_source`,
  and the summary leads with the arrival difference.
- Widget B1 names the baseline "Timetable plan" in plan sessions and shows arrival and
  delay vs. plan per branch.
- Tests: `tests/test_plan_branch_forecast.py` (4) plus the updated agent-outcome keys in
  `test_scenario_runner.py`.
- Verified against the running backend on Walensee at step 32: the forecast baseline is
  `plan (current)` with all three trains arriving by step 70; the what-if baseline for
  ICE_42 follows the plan's track (row 0, col 95/96), arrives at step 70 (+7 vs. plan
  63), *Left* arrives at 71 — "arrives 1 step later". Not clicked through in the browser:
  selecting the train in the scaled preview pane did not register.

### Stage 2 — A proposal seam with a planner behind it (≈ 3–5 days)

- One interface for proposal agents, extending the existing pluggable
  `InterventionRecommender` (`core/recommenders/`, today `phase1_proximity`): per
  conflict it returns alternatives (route, priority, hold-until-clear), each already
  simulated.
- First agent, not learning: re-plan with PP/CBS from
  [`AI4REALNET/flatland-blackbox`](https://github.com/AI4REALNET/flatland-blackbox) —
  the canonical solver `Tokener` and `T3.4-with-HMI` vendor. Reuse, not a new solver.
- Widget B1 becomes **Plan / KI / Mensch** (plan grey, AI yellow, human blue per the
  A3S convention), options go beyond the next switch: hold until clear, priority,
  route.

### Stage 3 — Learning agents behind the same seam (open-ended)

- MARL policies as proposal agents: decision-point action masking and the KPI
  calculator from
  [`AI4REALNET/maze-flatland`](https://github.com/AI4REALNET/maze-flatland), baselines
  from `flatland-association/flatland-baselines`.
- Training data exists already: the decision log (accept / override, reason,
  response) and the operator model's confirmed learnings.
- Needs a scenario with more traffic and variants (e.g. Olten) to train on.
- Feeding accepted proposals back into the base algorithm stays offline and
  reviewed — the concept card in the tour debrief (step 9b).

## 4. Open questions

- Which base algorithm stands for "the TMS" in stage 2: the scripted plan replay,
  or PP re-planning from the timetable skeleton?
- Scope of an agent: per train, per conflict, per resource (single-track section)?
- What counts as the human's "own proposal" once options are routes, not actions?
- Evaluation: which KPIs decide between plan, AI and human (arrival delay,
  connections, stability — the operator model's value axes)?
