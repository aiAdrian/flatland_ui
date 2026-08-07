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
| 233–505 | **3. Layer reference** | signatures + contracts, module by module |
| 235–260 | 3.1 `infrastructure_graph.py` | how the graph is built; node / wait-cell invariants |
| 261–267 | 3.2 `stations.py` | where stations come from (fixture / scene / hints / missions) |
| 268–291 | 3.3 `schedule.py` | planners + `SchedulePlayer` execution semantics |
| 292–321 | 3.4 `branching.py` | the action space: hold menu × route options |
| 322–339 | 3.5 `ensemble.py` | the three utilities and the weighted sum |
| 340–358 | 3.6 `safety.py` | the four sub-scores and their formulas |
| 359–395 | 3.7 `search.py` | greedy / beam / mcts + the portfolio guarantee |
| 396–436 | 3.8 `replan.py` | capture → residual plan → splice → rollout gate |
| 437–473 | 3.9 `goal_directed_policy.py` | caches, re-plan lifecycle, threading, re-anchoring |
| 474–491 | 3.10 `dataset.py` | encoding, timing helpers, the hard caps |
| 492–505 | 3.11 Models | the two checkpoints, the optional prior, env vars |
| 506–520 | 4. HTTP API | the seven `/director*` endpoints and their payloads |
| 521–569 | 5. Frontend surface | the A/B/C presets, store signals, widgets, mode gating |
| 550–569 | · 5.1 | the three kinds of number a tile shows, and which one wins |
| 570–590 | 6. Offline tooling | training / eval / dataset / calibration CLIs |
| 591–615 | **7. Invariants** | what must not break (read before editing the planner) |
| 616–636 | 8. Known limits | failure modes, incl. the re-plan latency window |
| 637–688 | 9. Recipes | runnable snippets for the common tasks |
| 689–706 | 10. Tests | which test file covers what |

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
WAIT_MENU = (0, 1, 3, 5, 10)   # extra hold ON TOP of the entry's existing dwell
DWELL = 1
```

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

**Hard caps** (raise `ValueError`, never truncate):
`MAX_TRAINS = 8`, `MAX_SCHEDULE_NODES = 64`, `MAX_NODES = 96`, `MAX_EDGES = 256`,
`MAX_CONNECTIONS = 96`. Consequence at runtime: a session with 9+ trains or a network
with 97+ decision points cannot be scored — `GoalDirectedPolicy._plan` swallows the error
and degrades to `"avoidance (no models)"`.

### 3.11 Models

- `ScheduleEvaluator` (`evaluator.py`) — graph encoder + schedule encoder →
  `predict(*inputs)` = `{all_arrived_probability, delay_bucket_probabilities, …}`.
- `ConnectionTransformer` (`connection_model.py`) — per-transfer survival →
  `{kept_ratio, connection_probability}`.
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

| `GET /session/{id}/director/strategies` | The A/B/C tiles: one plan per focus preset (§5), each on its own fork. `{step, available, reason, current, strategies:[{id, ident, focus, weights, plan:{source, weighted, utilities, reported, changed}, paths, divergence}]}`. Cached on `_strategy_cache_key` (step + weights + source + replan count) — three plans cost ~16–20 s. **Before step 0 the options are planned with `director_plan`** (so they get the portfolio guarantee, like the driving plan); mid-episode with `residual_plan` (the past must stay pinned). `reported` is `search._reported(breakdown)`: `keptRatio`, `connectionCount`, the four safety sub-scores. `divergence` is per train what the option changes against the driving plan — `reroute` (deviating stretch + branch cell) or `hold` (same cells, later) |
| `GET /session/{id}/director/activity` | Supervisory feed (~1 KB, vs ~172 KB for `/director` with the full trace): `{disruptions, replans, decided, planned, workload:{decisions, replans}, next:{step, inSteps, handle}}`. The trace holds *planned* times, so history and plan are reported apart |

`_invalidate_scenario_forecasts(session_id)` is called whenever the committed plan changed.

## 5. Frontend surface

The supervisory decision the HMI asks of the human is **which objective** the plan should
pursue, so the dial surface is three presets (A/B/C), each answered by a real plan:

| Preset | Weights (p/c/s) | Wins on |
| --- | --- | --- |
| A · Verspätung minimieren | 5 / 2 / 2 | punctuality |
| B · Anschlüsse halten | 2 / 5 / 2 | connections |
| C · Stabilität maximieren | 2 / 2 / 5 | stability |

No axis is ever zeroed and each preset weights its own axis strictly highest: the choice is
a statement about values, not a quality ranking. `DIRECTOR_STRATEGY_PRESETS` in
`app/api/sessions.py` is the single source; `test_director_strategies_api.py` asserts both
properties.

| File | Role |
| --- | --- |
| `core/session.store.ts` | `interactionMode`, `aiInControl` (= director), `optionPresentation === 'none'`, `_policyBeforeDirector`; overlay state `directorPlanPaths` / `directorPlanHover` / `directorPreviewPaths` / `directorPreviewDivergence` / `directorPreviewIsCommitted` / `directorPreviewIsFullPlan` / `directorHoverHandle`; `directorNextDecision`, `directorAiWorkload`, `directorFocusOutlook`; `shiftEnded` + `shiftReviewOpen` |
| `core/api.service.ts` | `getDirectorState`, `setDirectorWeights`, `getDirectorStrategies`, `getDirectorActivity`, `verifyDirectorPlan`, `replanDirectorNow`, `whatIfDirector` + all `Director*` interfaces |
| `features/strategy-options/` | **The A/B/C tiles** — per-axis bars as deltas against the driving plan, `reported` figures instead of the raw utilities, "Auf Karte" (divergence overlay), "Übernehmen" (`setDirectorWeights(…, plan=true)`), "Nachspielen" (`whatIfDirector`, ~7 s) |
| `features/director-directive/` | One-line state bar: aggregate fleet numbers, run control, "Schicht beenden" |
| `features/strategy-forecast/` | Rule-based projection of the selected focus's per-axis deltas (labelled as such — not a simulation) |
| `features/ai-activity/` | What the planner did and will do next, from `/director/activity` |
| `features/strategy-reflection/` | Asks *why* after a focus is committed (reason chips + free text, yes/once/no); the only preference evidence Director produces |
| `features/shift-review/` | Schichtabschluss as its own screen: balance, ≤3 reflection moments with the scoring trace, `verifyDirectorPlan` as ground truth, and saving the operator profile |
| `features/flatland-map/` | Draws `directorPlanPaths` on hover; a previewed option as **branch marks** (one per rerouted train) plus hold marks, its route only for the train under the pointer; red ring + tooltip on a disrupted train |
| `core/layout/panel-mode-availability.ts` | `director-directive` is director-only. Director deliberately does **not** show Situation Summary, Agents, Director Weights, Scenario, Agent Inspector, Goal Achievement or Recommendations — see the mode's own docs |

### 5.1 Why the tiles show three different kinds of number

1. **Model utilities** (the bars) — `CandidateScore.utilities`, cheap, computed for all three
   options at once. Two are unfit as displayed values, so `reported` replaces/annotates them
   (§3.5, §3.6): `kept_ratio` for connections, the limiting safety sub-score for stability.
2. **Rule-based projection** (the forecast strip) — a template over the per-axis deltas. No
   simulation; the strip says so.
3. **Simulated outcome** ("Nachspielen", `/director/whatif`) — two forks from the same RNG
   state, both played to the end, ~7 s. This is the one that decides when they disagree:
   §3.8 says residual plans are scored optimistically. Measured on the demo environment, the
   focus the models scored *worst* (0.44 vs 0.75) was the only one that improved the outcome
   (delay 442 → 324, arrivals 1 → 3, transfers 6 → 8), and in another session A/B/C had
   nearly identical bars (92/28/0 vs 91/28/0) while the replay separated them by 728 delay.
   The tile names the contradiction when it occurs.

`verifyDirectorPlan` costs ~0.1 s (open-loop replay, no model calls), which is why the shift
review fetches it outright. It replays the **final committed** origin-anchored schedules from
step 0 (invariant 5), so it answers "what does this plan achieve on this episode", not "this
is how the shift went".

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
```

`block_training.py` provides checkpoint/resume block training used by both trainers
(`--max-blocks`, `--checkpoint`, `--fresh`).

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
- **Encoding caps** (§3.10) silently push large sessions onto the model-free fallback.
- **Station resolution in the policy path** uses `build_decision_point_graph(env)` /
  `resolve_stations(env)` *without* the session's `scenario_preset_id` /
  `infrastructure_scene` — presets with a station fixture are not honoured there.
- `WAIT_MENU` granularity (0/1/3/5/10) is unvalidated; tune on the sweep.
- **The connections dial is the weakest lever.** Sweep, 12 scenarios of
  `TRAINING_MIX`, seed 42, greedy, every row verified by a full episode
  (`python -m app.policies.goal_based_policies.search --scenarios 12 --seed 42 …`):

  | weights | mean delay | arrived rate | mean kept ratio | mean safety |
  | --- | --- | --- | --- | --- |
  | lines (baseline) | 62.9 | 0.50 | **0.753** | 0.258 |
  | avoidance (baseline) | 74.7 | 0.08 | 0.604 | 0.184 |
  | punctuality (1,0,0) | **55.7** | 0.58 | 0.601 | 0.221 |
  | connections (0,1,0) | 70.6 | 0.50 | 0.736 | 0.280 |
  | stability (0,0,1) | 60.1 | 0.50 | 0.660 | **0.379** |
  | balanced (1,1,1) | 58.7 | 0.58 | 0.712 | 0.374 |

  Punctuality and stability each win on their own axis, so those two dials do
  steer ground truth. Connections does **not**: 0.736 kept is below the
  conflict-blind `lines` baseline at 0.753, while it pays 15 delay. Consistent
  with §3.5 — the connection utility saturates and stops discriminating. Caveats:
  extreme weights (the HMI presets never zero an axis), n = 12, `TRAINING_MIX`
  rather than a demo layout. Consequence for the HMI: a "hold more connections"
  promise on the B tile is not yet backed by ground truth; re-run the sweep with
  the preset ratios before claiming it.
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
| `test_goal_directed_policy.py` | registration, weights, degradation without checkpoints, cache survival across policy rebuilds, malfunction-triggered re-plan |
| `test_director_weights_api.py`, `test_director_replan_api.py` | HTTP contracts, forecast invalidation, what-if isolation, director-mode play |
| `test_director_strategies_api.py` | the A/B/C presets (no dominated option, no zeroed axis), the planner used per phase (`director_plan` at t=0, `residual_plan` after), caching and its invalidation, degradation without models |
| `test_director_divergence.py` | `_divergence`: reroute vs hold, the deviating stretch and its branch cell, "changes nothing" |
| `test_director_activity_api.py` | the supervisory feed: history vs plan kept apart, workload, next decision |
| `test_operator_model.py`, `test_operator_api.py`, `test_operator_loop.py` | the operator model: evidence gate, value profile, confirmed learnings, cross-session carry-over and its file persistence |

Frontend specs live next to their components (`ng test`, 200 specs): `strategy-options` (tile
figures, divergence gating, simulated outcome, learned-preference badge), `shift-review`
(balance, moments, ground truth, saving), `core/shift-review.spec.ts`,
`core/reflection-moments.spec.ts`, `core/strategy-forecast.spec.ts`.

Run a subset: `cd backend && python -m pytest tests/test_goal_based_search.py -q`.
