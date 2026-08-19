# Director mode — implementation reference

Agent-facing reference for everything behind `interactionMode === 'director'`:
the decision-point planner (`backend/app/policies/goal_based_policies/`), the
session policy that drives it, the HTTP surface and the frontend widgets.

Conceptual walk-through with diagrams: `docs/director-mode-guide.html`.
Mode semantics across WP 3.1/3.3/3.4: `docs/reference/interaction-modes-brief.md`.
This file is the API/invariant reference — read it before changing planner code.

## Where to look

Line ranges for `sed -n 'A,Bp'` / `Read(offset, limit)`; re-derive after edits with
`grep -n '^##\+ ' docs/reference/director-mode.md`. §2 is the vocabulary the rest of
the file assumes; §3 is the bulk of the API surface.

| Lines | Section | Answers |
| --- | --- | --- |
| 50–79 | 0. Code map | which file owns what |
| 80–105 | 1. Runtime flow | mode switch → plan → drive → disturbance → apply |
| 106–232 | **2. Data structures** | every type, its fields, its invariants |
| 108–145 | · Infrastructure | `Cell`, `SwitchApproach`, `GraphNode`, `GraphEdge`, `DecisionPointGraph`, `Station` |
| 146–160 | · Schedules | `ScheduleEntry`, `TrainSchedule`, why they stay origin-anchored |
| 161–180 | · Search state | `Prefix`, `BranchOption`, `DecisionPoint`, `SearchLimits`, `SearchOutcome`, `DirectorPlan` |
| 181–204 | · Scoring | `DirectorWeights`, `CandidateScore`, `ScenarioContext`, the `breakdown` keys |
| 205–215 | · Safety | `SafetyParams`, `SafetyReport`, `OpposingMeet`, `ResourceLoad`, `CascadeEdge` |
| 216–232 | · Connections / rollout / re-planning | `PlannedConnection`, `RolloutResult`, `TrainProgress`, `ResidualPlan` |
| 233–540 | **3. Layer reference** | signatures + contracts, module by module |
| 235–260 | 3.1 `infrastructure_graph.py` | how the graph is built; node / wait-cell invariants |
| 261–267 | 3.2 `stations.py` | where stations come from (fixture / scene / hints / missions) |
| 268–291 | 3.3 `schedule.py` | planners + `SchedulePlayer` execution semantics |
| 292–334 | 3.4 `branching.py` | the action space: joint (hold × route) and atomic (wait-or-route) modes |
| 335–352 | 3.5 `ensemble.py` | the three utilities and the weighted sum |
| 353–371 | 3.6 `safety.py` | the four sub-scores and their formulas |
| 372–408 | 3.7 `search.py` | greedy / beam / mcts + the portfolio guarantee |
| 409–449 | 3.8 `replan.py` | capture → residual plan → splice → rollout gate |
| 450–486 | 3.9 `goal_directed_policy.py` | caches, re-plan lifecycle, threading, re-anchoring |
| 487–519 | 3.10 `dataset.py` | encoding, trajectory fields, the hard caps, the off-distribution guard |
| 520–540 | 3.11 Models | the three checkpoints, committed-awareness, the optional prior, env vars |
| 541–552 | 4. HTTP API | the five `/director*` endpoints and their payloads |
| 553–567 | 5. Frontend surface | store signals, widgets, mode gating |
| 568–609 | 6. Offline tooling | training / eval / trajectory / calibration CLIs, 3-net expert-iteration curriculum |
| 610–634 | **7. Invariants** | what must not break (read before editing the planner) |
| 635–658 | 8. Known limits | failure modes, incl. the re-plan latency window |
| 659–710 | 9. Recipes | runnable snippets for the common tasks |
| 711–729 | 10. Tests | which test file covers what |

---

## 0. Code map

| Path | Role |
| --- | --- |
| `backend/app/policies/goal_based_policies/infrastructure_graph.py` | Rail grid → decision-point graph (nodes, edges, ids) |
| `…/stations.py` | Where stations are, from missions / scene / ECML fixture |
| `…/schedule.py` | `ScheduleEntry`/`TrainSchedule`, shortest-path & avoidance planners, `SchedulePlayer` (execution) |
| `…/branching.py` | The action space: prefixes, decisions, options, completion, overlap predicate |
| `…/connections.py` | Planned transfers and whether a run kept them |
| `…/safety.py` | Static robustness measure (= the stability utility) |
| `…/rollout.py` | Ground-truth episode replay + delay buckets |
| `…/dataset.py` | Tensor encoding, timing helpers (`edge_time_windows`), baseline planners, sample generation |
| `…/evaluator.py`, `…/connection_model.py` | The two learned models (torch) |
| `…/priors.py` | Optional policy prior for MCTS expansion |
| `…/ensemble.py` | Three-axis scoring → one weighted number (`score_candidates`) |
| `…/search.py` | greedy / beam / mcts strategies, `director_plan`, `verify_plan`, weight sweep |
| `…/replan.py` | Mid-episode capture → residual plan → splice; rollout gate; `simulate_forward` |
| `…/visualization.py` | matplotlib renders + `build_demo_env` (figures, docs) |
| `…/eval_set.py`, `…/search_dataset.py`, `…/train_*.py`, `…/safety_calibration.py`, `…/block_training.py` | Offline: eval sets, dataset generation, training, calibration |
| `backend/app/policies/goal_directed_policy.py` | Session policy: caches, replan lifecycle, threading, HMI accessors |
| `backend/app/policies/registry.py` | Registers policy id `goal_directed` ("Director Planner") |
| `backend/app/api/sessions.py` | `/director*` endpoints |
| `frontend/src/app/features/director-directive/`, `…/director-weights/`, `…/goal-achievement/` | Director widgets |
| `frontend/src/app/core/session.store.ts`, `…/api.service.ts` | Mode state, plan-path overlay, typed client |

Nothing in `goal_based_policies` imports torch at package import time — `__init__.py`
deliberately re-exports only the torch-free half.

---

## 1. Runtime flow

1. **Mode switch.** `SessionStore.setInteractionMode('director')` stores the previous
   policy in `_policyBeforeDirector` and switches the session policy to `goal_directed`;
   leaving Director restores it and pauses. `optionPresentation` becomes `'none'`
   (no per-decision prompts), `aiInControl` becomes true.
2. **Directive.** `director-directive` (KPI priorities + policy) and `director-weights`
   (the three dials) are set; "Start autonomous run" calls `store.play(...)`.
3. **First step.** `GoalDirectedPolicy.reset(env)` runs once per env:
   `build_decision_point_graph(env)` → `_plan(env, graph)` → caches
   `_PLAYERS[env]`, `_SCHEDULES[env]`, `_PLAN_INFO[env]` (weak-keyed by env).
4. **Planning** (`_plan`): with checkpoints → `director_plan(...)`; on any exception or
   missing checkpoints → `plan_all_lines` + `plan_avoiding_overlaps`, recorded as
   `source: "avoidance (no models)"`; unroutable → `source: "unroutable"`, no player.
5. **Driving.** Every `act_for_handle` calls `_maybe_replan(env)` (idempotent per step)
   then `player.act(handle)`.
6. **Disturbance.** `_maybe_replan` sees a fresh malfunction (`new_malfunctions`,
   ≥ `MIN_MALFUNCTION_STEPS`, outside `REPLAN_COOLDOWN`) or a dirty weights flag →
   `_start_replan_job`: capture state now, search on a daemon thread, **current plan
   keeps driving**.
7. **Application.** When the thread finishes, `_finish_replan` re-anchors the result to
   a *fresh* capture, optionally runs `rollout_gate`, and splices per-train tails into
   the live player. The event is appended to `_PLAN_INFO[env]["replans"]`.

---

## 2. Data structures

### Infrastructure

```python
Cell = Tuple[int, int]                      # (row, col)

@dataclass(frozen=True)
class SwitchApproach:
    switch_cell: Cell
    heading: int          # move direction from the wait cell INTO the switch

@dataclass
class GraphNode:
    cell: Cell
    node_id: int          # = row * env.width + col  (pure function of the cell)
    kinds: Set[str]       # ⊆ {"station", "switch_decision"}
    station_index / station_id / station_name: Optional[...]
    approaches: List[SwitchApproach]

@dataclass(frozen=True)
class GraphEdge:
    from_cell, to_cell: Cell
    out_direction, in_direction: int
    path: Tuple[Cell, ...]            # inclusive, contiguous on the rails
    # properties: length, travel_time (== length), moves, actions(entry_heading)

@dataclass
class DecisionPointGraph:
    nodes: Dict[Cell, GraphNode]
    edges: List[GraphEdge]
    switch_cells: Dict[Cell, List[int]]     # context only, NOT nodes
    stations: List[Station]
    # edges_from(cell), node_id(cell), cell_of(node_id),
    # edges_have_alternative_route() -> List[bool], to_dict()
```

`Station(id, name, stop_cells, center, source)` — `source ∈ {"missions",
"ecml_fixture", "scene"}`.

### Schedules

```python
@dataclass(frozen=True)
class ScheduleEntry:  node_id: int;  wait: int = 0

@dataclass
class TrainSchedule:  handle: int;  entries: List[ScheduleEntry]
    # to_flat_list() / from_flat_list() -> [node_id, wait, node_id, wait, …]
    # total_wait
```

A schedule is **absolute and full-horizon**: it always starts at the train's origin
node, even mid-episode (re-planning pins the past rather than re-basing).

### Search state

```python
Prefix = Tuple[ScheduleEntry, ...]          # per train, the committed head

@dataclass(frozen=True)
class BranchOption:  wait: int; edge: GraphEdge; prefix: Prefix
@dataclass(frozen=True)
class DecisionPoint:  handle: int; node_id: int; time: float; options: Tuple[BranchOption, ...]

@dataclass(frozen=True)
class SearchLimits:
    k_routes = 3; wait_menu = WAIT_MENU; max_decisions = 64
    beam_width = 4; simulations = 32; c_puct = 1.4

@dataclass class SearchOutcome:  schedules; score; trace; decisions; stuck
@dataclass class DirectorPlan:   schedules; source; score; considered; trace; decisions; stuck
                                 # source ∈ {"search","lines","avoidance"}; to_dict()
```

### Scoring

```python
@dataclass(frozen=True)
class DirectorWeights:  punctuality=1.0; connections=1.0; stability=1.0
    # non-negative, sum > 0; normalized() -> shares summing to 1

@dataclass(frozen=True)
class CandidateScore:
    punctuality; connections; stability; weighted
    safety_report: SafetyReport
    breakdown: Dict[str, object]        # JSON-able; the HMI "why"

@dataclass class ScenarioContext:   # per-scenario, candidate-independent
    env; graph; stations; connections; pseudo_outcomes
    local_nodes; alternatives; layout
    # ScenarioContext.build(env, graph, layout=0)
```

`breakdown` keys: `all_arrived_probability`, `delay_bucket_probabilities` (6),
`kept_ratio`, `connection_probabilities`, `safety{safety,slack_score,deadlock_score,
track_score,cascade_score}`, `utilities{punctuality,connections,stability}`,
`weights{…}` (normalised).

### Safety

`SafetyParams` (all free parameters in one frozen dataclass) ·
`PlanTimeline(handle, windows, node_visits, playable, planned_arrival, latest_arrival)` ·
`TrainSafety(handle, slack, fragility, reach)` ·
`OpposingMeet(first, second, cells, gap, has_alternative, fragility)` ·
`ResourceLoad(cells, trains, peak, has_alternative)` ·
`CascadeEdge(from_handle, to_handle, headway)` ·
`SafetyReport(safety, slack_score, deadlock_score, track_score, cascade_score, trains,
meets, loads, cascade_edges, largest_component, unplayable, params)` + `to_dict()`.

### Connections / rollout / re-planning

```python
StationCall(handle, station_id, cell, stop_index, time, from_departure)
PlannedConnection(station_id, feeder, connector, planned_gap)   # .pair
ConnectionOutcome(connection, kept, reason, feeder_time, connector_time)  # .observed_gap
ConnectionReport(outcomes)   # .total .kept .kept_ratio .served .reasons .to_dict()

RolloutResult(all_arrived, total_delay, max_delay, arrivals, delays, steps, occupancy)  # .bucket

TrainProgress(handle, status, seed, continue_entries, pin_wait, serve_base, tail_anchor)
    # status ∈ {"pending","running","done","off_plan"}; tail_anchor 1 = on node, 2 = mid-edge
ResidualPlan(schedules, tails, source, score, considered, trace, decisions, step, reason)  # .event()
```

---

## 3. Layer reference

### 3.1 `infrastructure_graph.py` — the world model

`build_decision_point_graph(env, stations=None, extra_station_cells=None,
scenario_preset_id=None, infrastructure_scene=None) -> DecisionPointGraph`

Invariants (all enforced by tests):

- **Nodes = stations ∪ switch wait cells.** A switch tile is *never* a node.
- **A wait cell is never a switch cell.** `find_switch_decision_cells` back-walks
  through switch clusters to the first plain-rail tile of each feeding branch; the
  recorded `heading` is that cell's next move toward the cluster.
- Wait cells are **directional**: they matter only for the headings whose next move
  enters their switch. Stations stop trains in every direction.
- A wait cell is created for **funneled (trailing/merging)** approaches: an in-heading
  with exactly one exit that it shares with another in-heading.
- **Edges are whole track runs** between two nodes, crossing any number of switch tiles.
  Facing choices therefore attach to the last upstream node, not to the switch.
- `node_id = row * env.width + col` — stable across train sets and scenarios (node-id
  embeddings must mean the same thing on the same infrastructure).
- Parallel edges between the same node pair exist; consumers disambiguate by
  `(travel_time, out_direction)` — **the same tie-break everywhere** (`_walk`,
  `_schedule_edges`, `SchedulePlayer._locate`, `simulate_occupancy`, `future_path`).

Helpers: `find_switch_cells`, `find_switch_decision_cells`, `station_cells_from_env`,
`move_direction`, `action_for_move`, `DIRECTIONS`/`DIR_TO_DELTA`/`OPPOSITE`/`LEFT_OF`/`RIGHT_OF`.

### 3.2 `stations.py`

`resolve_stations(env, scenario_preset_id=None, infrastructure_scene=None,
include_agent_missions=True)` → ECML fixture (preset id contains "ecml") → scene →
rail-generator city hints → agent missions as fallback/top-up. Naming (`S1`, `S2`, …)
is sorted by `(row, col)` to line up with the frontend station layer.

### 3.3 `schedule.py` — planning primitives and execution

| Function | Contract |
| --- | --- |
| `plan_shortest_path_states(graph, env, start_cell, start_heading, target_cell)` | Dijkstra over `(node, orientation)`; returns `[(cell, heading), …]` or None |
| `plan_shortest_path(...)` | Same, as a `TrainSchedule` with no waits |
| `line_stops(env, handle)` | The train's waypoints (origin … terminus). `agent.target` is only the *last* one |
| `plan_line(graph, env, handle, dwell=1)` | Chained shortest path over all stops; `dwell=1` at intermediate stops (Flatland counts a stop as served only with arrival *and* departure) |
| `simulate_occupancy(env, graph, schedule, waits)` | `[(cell, in, out, node_index)]` under open-loop replay |
| `plan_avoiding_overlaps(env, graph, schedules, safety=1, max_total_wait=60, max_iterations=400)` | Prioritised planning: hold later trains at the last node before a reserved cell |

`SchedulePlayer(graph, env, schedules=())`:

- `act(handle)` — **open-loop**. Stands (`STOP_MOVING`) while `wait > waited`; otherwise
  drives the edge with `action_for_move`; consumes an entry on arrival at the next node
  and re-decides; `DO_NOTHING` when off-plan or on the final node. It **never inspects
  occupancy** — there is no reactive shield in this layer.
- `locate(handle) -> (edge, index_in_path) | None` — matched by cell **and heading**.
- `remaining` / `waited` / `set_schedule` / `snapshot` / `restore` — snapshot+restore is
  how forks continue the live plan.
- `future_path(handle) -> [{step,row,col}]` — the drawable remainder from the train's
  actual position, malfunction and unserved dwell folded into `step`. Empty for done /
  off-plan trains (no highlight beats a wrong one).

### 3.4 `branching.py` — the action space

```python
WAIT_MENU = (0, 1, 3, 5, 10)        # joint mode: extra hold ON TOP of the entry's dwell
ATOMIC_WAIT_MENU = (1, 2, 4, 8)     # atomic mode: pure-wait durations
DWELL = 1
```

Two action vocabularies, selected by `SearchLimits.action_mode` (`"joint"` default):
**joint** — each option commits hold × route at once (`WAIT_MENU` × routes).
**atomic** — an option is *either* a route (leave now, `wait=0`) *or* a pure wait
(`BranchOption.edge is None`; the same node re-decides after the wait, at a planned
time advanced by the hold). Waits compose across re-decisions, so holds are unbounded
below the train's deadline (`latest_arrival` bounds the chain and terminates it), and
the route is chosen *after* the wait, against the other trains' decisions made in the
meantime. Fewer options per decision (routes + waits, not their product) — measured
~1.5–2× faster per decision budget. Traces carry `"action": "route"|"wait"`; traces
and `BranchPrior` checkpoints are action-space-dependent, so datasets from one mode
are stale for the other.

- `initial_prefixes(env, graph)` → `{handle: (ScheduleEntry(origin, 0),)}`. The origin is
  itself a decision (a departure hold is legitimate). Raises if an origin is not a node.
- `route_options(env, graph, handle, prefix, k=3)` → ≤ k feasible edges, **one per distinct
  target node**, ranked by `edge.travel_time + shortest-path-to-next-stop`. Empty when the
  prefix is complete, unresolvable, or ≥ `MAX_SCHEDULE_NODES`.
- `next_decision(env, graph, prefixes, k_routes=3, wait_menu=WAIT_MENU) -> DecisionPoint | None`
  — the **earliest** open decision across all trains (ties by handle). Options are
  `wait_menu × routes` in wait-major order, so **index 0 = shortest hold + cheapest route**;
  every tie-break in the search resolves to that.
- **Every node a train reaches is a decision.** Where the route is forced the decision is
  hold-only (menu × 1 edge). There is no "advance through forced nodes" shortcut — a train
  must be able to stand in front of a merge to let an opposing train clear.
- `complete_from(env, graph, handle, prefix) -> TrainSchedule | None` — the completion
  policy: naive chained shortest path per remaining leg, `DWELL` at intermediate stops.
  With a bare origin prefix it reproduces `plan_line` entry for entry. None = dead branch
  (unroutable leg or > `MAX_SCHEDULE_NODES` entries).
- `has_planned_overlap(env, graph, schedules, safety=1)` — do two plans claim a cell at
  overlapping times under open-loop replay. Used to prune before model calls.
- `arrival_time`, `is_complete` — prefix-level timing/termination predicates.

Deliberate non-reuse: the completion is *not* Tokener PP/CBS; see the module docstring
for the rationale before changing it.

### 3.5 `ensemble.py` — the value function

```python
score_candidates(context, candidates, weights, evaluator, connection_model,
                 safety_params=SafetyParams(), device="cpu", batch_size=64)
    -> List[CandidateScore]
```

- `U_punct = 0.5·P(all arrive) + 0.5·Σ p_b·BUCKET_UTILITIES[b]`,
  `BUCKET_UTILITIES = (1.0, 0.8, 0.6, 0.4, 0.2, 0.0)`, `ARRIVAL_BLEND = 0.5`.
- `U_conn = geometric mean` of per-transfer kept probabilities (clamped to `[1e-4, 1]`,
  `1.0` when there are no transfers). The transformer's arithmetic mean survives as
  `kept_ratio` — **report it, don't optimise it** (it saturates and stops discriminating).
- `U_stab = SafetyReport.safety` — computed, not predicted.
- `weighted = Σ normalized_weight · utility` (a plain weighted sum, so sliders behave
  predictably; veto semantics live inside the safety product).
- Batched; everything candidate-independent lives in `ScenarioContext`.

### 3.6 `safety.py` — the stability axis

`assess_safety(env, graph, schedules, params=SafetyParams(), alternatives=None) -> SafetyReport`
(pass `corridor_alternatives(graph)` when scoring many plans on one network).

`safety = slack · deadlock · track · cascade`, each in `[0,1]`, all read from the
*planned* timeline (`edge_time_windows`), never a rollout:

| Component | Formula | Meaning |
| --- | --- | --- |
| slack | `Π (1 − p_disturb·exp(−slack_i/τ_slack))` | per-train buffer to `latest_arrival` |
| deadlock | `Π (1 − q_deadlock·w·exp(−gap/τ_deadlock))` | opposing meets on a shared stretch; `w = alt_discount` if reroutable |
| track | `Π (1 − q_track·w·(peak−1)/(n−1))` | trains one `window`-long blockage catches per shared stretch |
| cascade | `1 − q_cascade·mean_reach/(n−1)` | how far a `delta`-minute disturbance propagates along couplings |

Works on shared **cells**, never shared edges (directional wait cells mean the two
directions over one track are different edges — grouping by edge finds no opposing
traffic at all). Unplayable plans are flagged (`unplayable`), not scored.

### 3.7 `search.py` — the strategies

All three share the signature
`(env, graph, context, weights, evaluator, connection_model, safety_params, limits,
prior=None, seeds=None) -> SearchOutcome` and are registered in `STRATEGIES`
(`"greedy" | "beam" | "mcts"`). `seeds` replaces `initial_prefixes` — that is how
re-planning reuses them.

`_expand_and_score` is the shared core: complete every option of one decision into a
**full multi-train candidate** (other trains get `_fallback` completions of their current
prefixes), mark `clean` via `has_planned_overlap`, `considered = clean subset if any else all`,
batch-score. Returns None when all branches are dead ends → the train is marked `stuck`.

- **greedy** (runtime default): one chronological pass, commit `argmax weighted` over
  `sorted(considered)`. Per-decision trace.
- **beam**: `beam_width` partial plans, each advanced by its own next decision, survivors
  by completed-plan score, dedup on `_state_key`. Step-level trace.
- **mcts**: AlphaZero-shaped. `simulations` per root decision, PUCT with `c_puct`, leaf
  value = best option's completion score (no rollouts), first-play urgency = the option's
  own leaf score, commit **most-visited**, ties by mean value then lowest index. Optional
  `prior` (`priors.BranchPrior`) renormalised over the considered subset. Trace carries
  `visits` and `mean_value` — the training signal for the prior.

`director_plan(...) -> DirectorPlan` adds the **portfolio guarantee**: the searched plan
competes with `plan_all_lines` and `plan_avoiding_overlaps` under the same weighted score;
ties prefer the search (it can explain itself). Never returns a plan worse than the
baselines *by its own judgment*.

`verify_plan(env, graph, stations, schedules, safety_params)` — ground truth: runs a whole
episode (`run_schedules`) and reports delay/arrival/connections/safety. **Hand it a fresh
env**; it steps the one it is given.

`sweep(...)` + `SWEEP_WEIGHTS` — the acceptance experiment ("do the dials steer ground
truth?"). CLI: `python -m app.policies.goal_based_policies.search`.

Nothing in this module steps the env except `verify_plan`.

### 3.8 `replan.py` — mid-episode

```python
capture_progress(env, graph, player, schedules, now=None) -> Dict[int, TrainProgress]
residual_plan(env, graph, weights, evaluator, connection_model, player, schedules,
              reason="", safety_params, limits, strategy="greedy", context=None,
              now=None, progress=None) -> ResidualPlan
splice_entries(progress, final) -> List[ScheduleEntry] | None
apply_residual_plan(player, plan) -> None
rollout_gate(env, player, plan) -> {"commit": bool, "keep": {...}, "switch": {...}}
simulate_forward(env, player, watch_cells=None) -> Dict[str, object]
new_malfunctions(env, known, now=None, min_steps=MIN_MALFUNCTION_STEPS) -> [(handle, end_step)]
```

Design: the residual problem is expressed in the language the models already speak —
a full-horizon schedule from the origin with everything up to the train's position
**pinned**, and reality's delay folded into a virtual wait at the frontier node. No
re-training, no new input scheme. Consequences:

- Past occupancies keep their *nominal* times, so the overlap pruner may see phantom
  overlaps between two pinned pasts; the clean-preference degrades to score-only.
- The models rank residual plans optimistically → recovery is committed on **simulated**
  outcomes (`rollout_gate`), not scores. Measured: 18/20 chose "research", 3 wins vs
  3 losses, one catastrophic, and the predicted margin does not separate them.
- Mid-episode **ties keep the current plan** (churn must pay for itself), unlike t=0.
- `progress=` lets capture (must be atomic with the step loop) be separated from the
  search (immutable facts only → safe on a thread).
- `splice_entries` returns None when the chosen schedule does not extend the captured
  seed — the tail would otherwise teleport the plan out from under the train.

`rollout_gate` forks the env twice from the same RNG state, so both branches see the same
future malfunction stream: better = more arrivals, or equal arrivals with strictly less
delay. Ties keep the current plan.

`simulate_forward` is the A3S *restore → simulate-forward → report* contract in-process
(the consortium service needs Redis + its own processes; the seam is kept narrow so it
can replace this).

CLI benchmark (`does reacting beat continuing?`):
`python -m app.policies.goal_based_policies.replan --evaluator … --connection-model …`.

### 3.9 `goal_directed_policy.py` — the session policy

State is **per env, weak-keyed** (session APIs rebuild `Policy` objects on every request,
so nothing may live on the instance): `_PLAYERS`, `_SCHEDULES`, `_PLAN_INFO`,
`_ENV_WEIGHTS`, `_REPLAN_STATE`; `_MODELS` is process-wide and lazily loaded.

| Symbol | Contract |
| --- | --- |
| `set_director_weights(p,c,s)` / `director_weights()` | process default for envs planned from now on |
| `set_env_weights(env,p,c,s)` | before step 0: drop the cached plan; mid-episode: set `weights_dirty` (→ residual re-plan, ungated) |
| `env_weights(env)` | this env's dials, falling back to the process default |
| `plan_info(env)` | provenance dict: `source`, `weighted`, `utilities`, `weights`, `decisions`, `trace`, `replans` |
| `plan_schedules(env)` | the committed full schedules (what verification replays) |
| `plan_player(env)` | the live `SchedulePlayer` |
| `plan_paths(env)` | `{handle: future_path}` for the map overlay |
| `replan_now(env, reason="manual", gate=True)` | synchronous residual re-plan; supersedes any in-flight job; returns the event or None |
| `loaded_models()` | `(evaluator, connection_model)` or None |
| `director_replay_factory(env)` | zero-arg factory producing `DirectorPlanReplayPolicy` — model-free replay of the committed plan on forks (scenario forecasts, override what-ifs) |
| `REPLAN_COOLDOWN = 10` | steps to sit out after a re-plan; weight changes bypass it |

Re-plan lifecycle (`_maybe_replan`, once per env step):

```text
job in flight?  → thread alive: return (committed plan keeps driving)
                → finished: clear job, set cooldown, _finish_replan(plan, gate)
no job          → weights_dirty  → reason "weights change", gate=False
                → past cooldown and new_malfunctions() → reason "malfunction on train H until t=E"
                → _start_replan_job(reason, gate): capture now, search on daemon thread
```

`_finish_replan` **re-anchors**: it discards `plan.tails` (anchored to the capture the
search started from) and recomputes them against a *fresh* capture, per train. A train
that already drove past a point where the new plan diverged keeps its current plan; if all
trains diverged the re-plan is dropped (`committed = False`). This is the fix for the
frozen-trains bug — applying stale tails leaves `SchedulePlayer._locate` unable to match
and the train holds forever. The gate then judges the re-anchored splice.

### 3.10 `dataset.py` — encoding and timing (also used at inference)

`edge_time_windows(env, graph, schedule, start_heading=None) -> [(edge, enter, exit)]` —
open-loop planned timing; the single source of truth for "when is the train where" in
safety, branching and re-planning. `edge.path` gives contiguous cells (`_walk` returns
node cells only — use `edge_time_windows` when you need to draw).

`plan_all_lines(env, graph, dwell=1)`, `plan_all_trains(env, graph)`,
`build_layout_env(layout, number_of_agents)`, `Layout`, `ScenarioMix`, `TRAINING_MIX`,
`EVAL_MIXES`, `encode_graph`, `encode_sample`, `encode_connections`, `stack_samples`,
`Sample`, `generate_samples[_parallel][_report]`, `save_samples`/`load_samples`.

**Trajectory fields** (`Sample.committed`, `Sample.final_safety`): per-train committed
fraction (1.0 = plan executed as written; <1 = tail is naive completion under continued
planning) and the stability label (`assess_safety(final plan).safety`, −1 = unlabelled).
`stack_samples` appends committed as index **18**; absent reads as fully committed.
Committed-aware models (`evaluator.expects_committed`, config `train_scalars` >
`TRAIN_SCALARS`) get the column appended to their train-scalar row; legacy checkpoints
see exactly the row they were trained on.

**Hard caps** (raise `ValueError`, never truncate), sized for the largest curriculum
bucket (200×200, 8 cities, 50 trains — see `curriculum.py`):
`MAX_TRAINS = 56`, `MAX_SCHEDULE_NODES = 64`, `MAX_NODES = 160`, `MAX_EDGES = 384`,
`MAX_CONNECTIONS = 2048`. Samples are trimmed in RAM (`trim_sample`) and re-padded per
batch (`stack_samples`), so small scenarios do not pay for the headroom. `CROWD_SCALE`
stays a literal `8.0` — it is a normalisation constant the shipped checkpoints were
trained with, **not** the train cap; re-deriving it from `MAX_TRAINS` would rescale
their input distribution. Since the caps no longer stop off-distribution scoring,
`GoalDirectedPolicy` guards explicitly: sessions with more trains than
`MODEL_TRAINED_MAX_TRAINS` (env `GOAL_DIRECTED_MODEL_MAX_TRAINS`, default 8 =
`TRAINING_MIX.max_trains`) use `"avoidance (no models)"`; bump it when curriculum
checkpoints ship.

### 3.11 Models

- `ScheduleEvaluator` (`evaluator.py`) — graph encoder + schedule encoder →
  `predict(*inputs)` = `{all_arrived_probability, delay_bucket_probabilities, …}`.
- `ConnectionTransformer` (`connection_model.py`) — per-transfer survival →
  `{kept_ratio, connection_probability}`.
- `StabilityEvaluator` (`evaluator.py`) — the third net: predicts the *final* plan's
  safety from a partially committed state; trained with the computed measure
  (`assess_safety` of the trajectory's final plan) as the label. When installed
  (`GOAL_DIRECTED_STABILITY_MODEL`, default `models/goal_directed/stability.ckpt`),
  `score_candidates` uses its prediction as the stability utility; the computed
  measure stays in the breakdown as evidence and remains the labeller. Missing →
  computed measure everywhere (purely additive).
- `BranchPrior` (`priors.py`, 5 features, tiny MLP) — optional MCTS expansion prior;
  trained from search traces.
- Loaded from `GOAL_DIRECTED_EVALUATOR` / `GOAL_DIRECTED_CONNECTION_MODEL`, defaulting to
  `backend/models/goal_directed/{evaluator,connection}.ckpt`. Missing → model-free
  fallback everywhere, never an error.

---

## 4. HTTP API (`backend/app/api/sessions.py`)

| Endpoint | Body / result |
| --- | --- |
| `GET /session/{id}/director` | `{weights, plan: DirectorPlanInfo\|null, paths}` |
| `POST /session/{id}/director/weights` | `{punctuality, connections, stability, plan?: bool}` → `{weights, replanned, plan, paths}`. `plan:true` plans **synchronously** (from scratch before step 0, residual + ungated mid-episode) |
| `POST /session/{id}/director/verify` | Replays the committed plan on a pristine persister clone (`reset(regenerate_rail=False, regenerate_schedule=False)`) → `{predicted, verified}`. Live session untouched |
| `POST /session/{id}/director/replan` | Manual residual re-plan (gated) → `{event, plan, paths}`; 400 without a committed plan or models |
| `POST /session/{id}/director/whatif` | Candidate weights → two forks (continue vs re-plan), both simulated to the end → `{continue, replan}` with delay/arrivals/connections. Same RNG stream; live session untouched |

`_invalidate_scenario_forecasts(session_id)` is called whenever the committed plan changed.

## 5. Frontend surface

| File | Role |
| --- | --- |
| `core/session.store.ts` | `interactionMode`, `aiInControl` (= director), `optionPresentation === 'none'`, `_policyBeforeDirector` (auto-switch to/from `goal_directed`), `directorPlanPaths`, `directorPlanHover` |
| `core/api.service.ts` | `getDirectorState`, `setDirectorWeights`, `verifyDirectorPlan`, `replanDirectorNow`, `whatIfDirector` + all `Director*` interfaces (mirror of the payloads above) |
| `features/director-directive/` | Pre-run directive: KPI priorities + policy + "Start autonomous run" |
| `features/director-weights/` | The three dials (0–5 discrete points → weight ratio), scorecard (source/utilities), trace, re-plan list, verify + what-if buttons; polls director state; sets `directorPlanPaths` |
| `features/goal-achievement/` | Supervisory KPI panel (arrived %, mean delay vs target) |
| `features/flatland-map/` | Draws `directorPlanPaths` while `directorPlanHover` is true |
| `core/layout/panel-mode-availability.ts` | `goal-achievement`, `director-directive`, `director-weights` are director-only; `scenario` is co-learning + director |

Dials are discrete on purpose: small continuous nudges barely move a normalised weight
ratio, so every click must be a change the planner can respond to.

## 6. Offline tooling

```bash
# from backend/
python -m app.policies.goal_based_policies.train_evaluator        --samples … --out evaluator.ckpt
python -m app.policies.goal_based_policies.train_connection_model --samples … --out connection.ckpt
python -m app.policies.goal_based_policies.eval_set               --dataset eval.npz --per-mix 500 --evaluator … --connection-model …
python -m app.policies.goal_based_policies.search_dataset         --count … --evaluator … --connection-model … --out … [--traces-out …]
python -m app.policies.goal_based_policies.priors                 traces.jsonl --out prior.ckpt
python -m app.policies.goal_based_policies.search                 --scenarios … --evaluator … --connection-model …   # weight sweep
python -m app.policies.goal_based_policies.replan                 --scenarios … --evaluator … --connection-model …   # react-vs-continue
python -m app.policies.goal_based_policies.safety_calibration     --scenarios … --out …
python -m app.policies.goal_based_policies.train_stability_model  --dataset-cache traj.npz --out stability.ckpt
python -m app.policies.goal_based_policies.curriculum             run|compare   # 3-net expert-iteration curriculum
```

`block_training.py` provides checkpoint/resume block training used by both trainers
(`--max-blocks`, `--checkpoint`, `--fresh`).

**Curriculum** (`curriculum.py`) — three-net expert iteration on **trajectory
labels** (AlphaZero-style): 5 size buckets (`b0-small` 30–35/2–5 trains … `b4-huge`
150–200/28–50 trains), each carving train/test/eval layout-seed ranges above
`EVAL_SEED_RANGE`, provably disjoint from each other, the shipped training range and
the hard-eval set. Per stage: greedy **trajectory self-play**
(`search_dataset.generate_trajectory_samples_report`, `--action-mode` default atomic)
plans `--train-count` scenarios with the previous stage's nets; *every committed
decision* becomes a sample labelled with the final plan's executed outcome
(punctuality/delay, per-transfer survival) and with `assess_safety(final plan)` as the
stability target — ~20–40 samples per scenario instead of 1. All **three** nets
(evaluator, connection transformer, stability — separate targets, shared states,
committed-aware) retrain on the cumulative data, warm-started per stage; stage 0
*plans* with the shipped pair but *trains fresh* (the shipped input row has no
committed column). Promotion is the closed-loop gate (measured outcomes vs the
model-free fallback + `--margin`); near-constant self-play outcomes are refused at
admission. The **eval ranges are read by no training decision**; `compare` re-plans
them closed-loop with model sets (pairs or triples with `--stability-model`) plus the
fallback. Self-play caches + checkpoints live in the run's `--out-dir`.

**Training data is action-space dependent.** Search datasets and priors generated before
a change to `WAIT_MENU`/`branching` semantics are stale; evaluator/connection checkpoints
are not (they score schedules, not decisions).

## 7. Invariants — do not break

1. **Determinism.** Every strategy, the trace, the portfolio choice and the re-plan are
   deterministic: models in eval mode, no randomness, ties keep the lowest option index
   (= shortest hold, cheapest route). Tests assert that a repeat run produces an identical
   trace (JSON, sorted keys) and identical schedules. Any wall-clock or thread-order
   dependence in a planning decision breaks the HMI's reproducibility for study
   participants.
2. **The `(travel_time, out_direction)` tie-break** for parallel edges must stay identical
   in `_walk`, `_schedule_edges`, `_locate`, `simulate_occupancy`, `future_path` — a
   schedule stores node ids, so every consumer must resolve the same edges out of them.
3. **Wait cells are never switch cells**; switch tiles are never nodes.
4. **Every node is a decision** (hold-only where the route is forced).
5. **Schedules stay absolute** (origin-anchored, full horizon) — re-planning pins, it does
   not re-base. The models were trained on that encoding.
6. **Never apply a tail computed against a stale capture.** Re-anchor (`_finish_replan`).
7. **Never touch the live env from the re-plan thread.** Capture first; the search may read
   only immutable facts; anything simulated runs on a `deepcopy`.
8. `SchedulePlayer.act` is open-loop by design; the safety measure exists precisely to
   penalise plans that would need a reactive net.
9. Degrade, never break: missing models / unroutable / cap exceeded → a recorded fallback
   `source`, and a train the planner could not route holds rather than guesses.
10. Weights are **global per session**, three axes, non-negative, normalised at scoring
    time. Per-agent policy/weights do not exist (backend change, see the brief).

## 8. Known limits & failure modes

- **Re-plan latency window.** While the background search runs the pre-disturbance plan
  keeps driving open-loop, so trains can commit into track the broken train now blocks;
  Flatland stalls them rather than colliding, but a head-to-head commitment on single
  track is unrecoverable (the schedule vocabulary has no reverse). The longer the search,
  the more trains drive past a divergence point and get dropped by the re-anchor —
  latency can silently cancel the fix.
- **No reactive shield** anywhere in the execution path.
- **Whole-plan recompute.** A disturbance re-decides for *every* train from its frontier;
  no tree, scores or structure is reused between re-plans (the decision-point graph *is*
  cached — it is not rebuilt).
- **Cost model.** Planning cost ≈ decisions × routes × |WAIT_MENU| model calls; each leaf
  completes all trains to the horizon. `SearchLimits.max_decisions` is the blunt knob.
- **Off-distribution guard** (§3.10): sessions with more trains than
  `MODEL_TRAINED_MAX_TRAINS` (default 8) use the model-free fallback — the caps are
  curriculum-sized now and no longer enforce this by accident. The models are confidently
  wrong far outside training (measured: P(all arrive)=1.0 while ~0/50 trains arrive).
- **Station resolution in the policy path** uses `build_decision_point_graph(env)` /
  `resolve_stations(env)` *without* the session's `scenario_preset_id` /
  `infrastructure_scene` — presets with a station fixture are not honoured there.
- `WAIT_MENU` granularity (0/1/3/5/10) is unvalidated; tune on the sweep.
- Phantom overlaps between two pinned pasts in residual plans (see §3.8).

## 9. Recipes

```python
# Plan from scratch and drive
graph = build_decision_point_graph(env)
plan  = director_plan(env, graph, DirectorWeights(1, 1, 1), evaluator, connection_model,
                      strategy="greedy")            # .schedules .source .score .trace
player = SchedulePlayer(graph, env, plan.schedules)
env.step(player.act_many(sorted(s.handle for s in plan.schedules)))

# Score arbitrary candidate plans (batched, one scenario)
context = ScenarioContext.build(env, graph)
scores  = score_candidates(context, [plan_a, plan_b], DirectorWeights(2, 1, 1),
                           evaluator, connection_model)
scores[0].breakdown["utilities"], scores[0].weighted

# Static robustness only (no models needed)
report = assess_safety(env, graph, schedules, alternatives=corridor_alternatives(graph))

# Mid-episode: re-plan and apply safely
progress = capture_progress(env, graph, player, schedules)        # atomic with the step loop
rp       = residual_plan(env, graph, weights, evaluator, connection_model,
                         player=player, schedules=schedules, progress=progress)
fresh    = capture_progress(env, graph, player, schedules)        # re-anchor before applying
for h, sched in {s.handle: s for s in rp.schedules}.items():
    tail = splice_entries(fresh[h], sched)
    if tail is not None:
        player.set_schedule(TrainSchedule(handle=h, entries=tail))

# What-if on a fork (live session untouched)
fork = copy.deepcopy(env)
fp   = SchedulePlayer(graph, fork); fp.restore(player.snapshot())
outcome = simulate_forward(fork, fp,
                           watch_cells=station_watch_cells(resolve_stations(env)))

# Ground truth for a plan (needs a FRESH env)
verify_plan(fresh_env, build_decision_point_graph(fresh_env),
            resolve_stations(fresh_env), schedules)

# Figures / repro env
env = build_demo_env(seed=11, width=26, height=26, number_of_agents=2,
                     line_length=4, flexible_terminus=True)
render_decision_point_graph_on_flatland(env, graph, ...)
```

Models in tests are constructed untrained and tiny (no checkpoints needed):

```python
evaluator        = ScheduleEvaluator(hidden=16, rounds=1, trunk_layers=1, sequence_layers=1)
connection_model = ConnectionTransformer(hidden=16, rounds=1, layers=1, heads=2, dropout=0.0)
```

## 10. Tests

| File | Covers |
| --- | --- |
| `test_goal_based_infrastructure_graph.py` | node/wait-cell placement, funneled approaches, ids |
| `test_goal_based_schedule.py` | planners, occupancy, player playback |
| `test_goal_based_branching.py` | prefixes, route options, hold menu at forced nodes, chronological determinism, overlap predicate |
| `test_goal_based_safety.py`, `…_safety_calibration.py` | sub-scores and their calibration study |
| `test_goal_based_connections.py`, `…_connection_model.py`, `…_evaluator.py` | transfers and the two models |
| `test_goal_based_ensemble.py` | utilities, weighting, breakdown |
| `test_goal_based_search.py` | determinism, trace, decision budget, portfolio guarantee, beam/mcts, prior, `verify_plan` |
| `test_goal_based_replan.py` | capture/splice/re-anchor, stale-plan safety, rollout gate, `simulate_forward`, future paths |
| `test_goal_based_search_dataset.py`, `…_priors.py`, `…_eval_set.py` | offline pipelines |
| `test_goal_based_padding.py` | trim/re-pad losslessness, batch-composition independence |
| `test_goal_based_curriculum.py` | bucket seed disjointness, admission, gates, stage loop, eval compare |
| `test_goal_directed_policy.py` | registration, weights, degradation without checkpoints, cache survival across policy rebuilds, malfunction-triggered re-plan |
| `test_director_weights_api.py`, `test_director_replan_api.py` | HTTP contracts, forecast invalidation, what-if isolation, director-mode play |

Run a subset: `cd backend && python -m pytest tests/test_goal_based_search.py -q`.
