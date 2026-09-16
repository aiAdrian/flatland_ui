# Plan — Proposal agents: a base algorithm with small agents on top

> **Status:** stage 1 done · stage 2a/2c backend built, 2b (widget) next · started 2026-09-15 · owner: Daniel Boos
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

**Design decisions (2026-09-15, after reading the sources).**
- **Solver: vendor, don't install.** `flatland-blackbox` is MIT (© 2025 Marius
  Captari, portions © 2019 Ashwin Bose). Its solvers need only `networkx`, but its
  `utils.py` imports `flatland.graphs` at module load, which Flatland 4.2.6 no longer
  has, and the package pins `flatland-rl==4.0.3` and pulls `torch`. So `solvers/pp.py`
  and the pure graph helpers it uses are copied into `backend/app/planners/blackbox/`
  with the licence notice, unchanged apart from imports; the blackbox PP tests come
  along.
- **Graph from the env: our own.** `T3.4-with-HMI`'s `state_extraction.py` does this
  but the repo carries no licence, so it is a reference, not a source. Enumerating
  Flatland transitions into a `(row, col, dir)` digraph is a few lines on our side.
- **Follow a replan with `PlanPolicy`.** A PP result is `(node, time)` per train;
  turned into a `TrainrunDict` it is exactly what `PlanPolicy` already executes. No
  plan follower to port, and the branch runner then scores Plan and AI proposal with
  the same figures as the human's choice (stage 1).
- **Replanning mid-run.** Trains start from their current cell and direction at the
  current step; arrived trains are left out; the malfunctioning train's cell is
  reserved for its remaining down time before planning.
- **Known limit:** PP routes straight to the target. The Walensee trains' intermediate
  calls, if any, are not honoured by the replan in this first cut.

**Sub-steps.**
- **2a** Backend: vendored PP + env graph + mid-run replan → proposals endpoint
  returning *Plan* (plan continuation) and *KI* (PP replan) per conflict, each
  simulated. Tests.
  **Status (2026-09-15): built.** `app/planners/blackbox/` (PP + helpers, MIT notice),
  `app/planners/replan.py` (`build_rail_digraph`, `replan_from_state`),
  `GET /session/{id}/proposals?handle=&action=` in `api/overrides.py` (variants
  `plan` / `ai` / `human`, each with train outcome, system KPIs, trajectories).
  Tests: `test_blackbox_pp.py` (ported upstream cases), `test_replan_proposals.py`.
  A replan on Walensee takes ~50 ms.
  **Finding — in the probed cases PP's default order reproduces the plan.** Tour
  incident (step 29/30), the never-experienced head-on case (35/38) and the study
  disturbance (19/22): the replan's arrivals equal the plan's. The plan is already a
  good solution there, so an "AI proposal" in default order says "keep the plan".
  **The priority order is where proposals differ.** Study disturbance at step 19:
  W1 first gets W1 in one step earlier but makes E1 or E2 arrive at 79 instead of
  63/64 — a real trade-off. In the single-track head-on cases W1 first has no
  collision-free plan at all. So the agent should offer *several* ranked orders
  (2c), not one replan.
- **2b** Frontend: widget B1 as Plan / KI / Mensch.
  **Status (2026-09-16): built.** A separate panel type `proposal-compare`
  (`features/proposal-compare/`, catalogue B1b, Co-Learning only) rather than a
  rewrite of `whatif-compare`: that widget is what the User Study 2 conditions
  show, and its framing (my plan vs. the AI's) is not this one's. The interview
  preset uses the new panel; the study presets are untouched.
  - Three columns for the selected train — Plan (neutral grey), KI (yellow, with
    its priority order in train names), Mensch (blue, the chosen option) — each
    with arrival vs. plan and trains arrived. Further AI orders behind a toggle.
  - Options: Halten, Halten bis frei, Weiterfahren, Umleiten. The backend's own
    sentence is shown when it refuses one (no reroute here).
  - The map overlay keeps the A3S colours: the operator's course blue against the
    AI's yellow once an option is picked, the AI against the plan before that.
  - "Übernehmen" goes through `TrainActionService` with a new `proposals` origin,
    so the decision log keeps the widget it came from. `Halten bis frei` commits
    as a hold and says that the release is the operator's, because the timed
    release lives in the simulated variant only.
  - Verified live on the tour session at step 52 with ICE_42: plan and KI both
    arrive at 70 (+7), order IC_703 → ICE_42 → RE_18, verdict "die KI würde hier
    beim Plan bleiben"; Halten bis frei adds the third column and the caveat.
    Note: at step 52 the malfunction is long over, so that option is free there —
    the telling case is the decision moment (the backend test: 72 vs. never).
- **2c** Options beyond the next switch: hold until clear, priority into the section.
  **Status (2026-09-15): backend built** (done before 2b, so the widget gets its final
  payload once).
  - `replan_orders(env)` in `planners/replan.py`: PP over priority orders (all orders
    up to four trains, else each train once in front), infeasible orders dropped,
    identical plans reported once.
  - `/proposals` ranks the orders by `score` (summed arrival delay vs. plan, +1000 per
    train not arriving): best is `ai`, the next ones `ai_alternatives` (`ai-2`, …),
    each with its `priority`. `ai_matches_plan` says when the best replan keeps every
    arrival of the plan.
  - Human side takes `option` = `hold` | `hold_until_clear` | `proceed` | `reroute`
    (or a raw `action`); `hold_until_clear` releases the hold after the impact
    analysis' `clears_in_steps` via the new `release_at` of `run_branch`.
  - Walensee tour, step 30, ICE_42: plan = ai `[0,1,2]` arrival 70 (+7), score 26;
    ai-2 `[0,2,1]` arrival 85 (+22), score 40; hold → never arrives (1/3);
    hold until clear → 72 (+9), 3/3; proceed = plan; reroute → none available.
  - Tests: `test_replan_proposals.py` (release ends a hold, distinct orders, ranked
    orders and hold-until-clear arriving).
  - Open: route alternatives beyond the impact analysis' first switch.

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
