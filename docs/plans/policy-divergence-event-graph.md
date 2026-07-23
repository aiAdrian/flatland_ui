# Task: Policy-Divergence Event Graph

**Status:** Phase 0 (exhaustive action-space size experiment) — see §0
**Date:** 2026-07-22
**Related:** `docs/plans/recommender-roadmap.md`, widget B1 (branch compare) in
`frontend/src/app/core/widget-catalog.ts`, AI4REALNET A3S/TraceRL
(`AI4REALNET/agent-as-a-service-trace-rl` — branching-trajectory tree
visualisation; convention: human-influenced steps = blue, AI-simulated = yellow).

---

## 0. Phase 0 — exhaustive action-space size experiment (current)

Decisions taken (2026-07-22):

- **Divergence is decided on resulting states, not on actions** (resolves P1).
  Two proposals that lead to the same successor state are the same branch —
  no action canonicalisation heuristics; compare state hashes after stepping.
- **Before rolling out policies at all, measure the worst case** (de-risks
  P2/P3): build the graph over **all possible actions** — branch at every
  SWITCH cell into every possible direction — on a test setup and measure how
  large it gets. Every policy-divergence graph is a subgraph of this one, so
  its size is a hard upper bound.

Implementation: `backend/app/core/action_event_graph.py`
(`ExhaustiveActionGraphBuilder` + `hard_deadlocked_agents`), exercised by
`backend/tests/test_action_event_graph.py` and runnable standalone:

```sh
cd backend && python -m app.core.action_event_graph --agents 3 --seed 42 --depth 60
```

Phase 0 semantics (differences vs. the policy graph in §1):

- Branch condition = an agent sits on a SWITCH cell at a cell-entry step →
  one child per possible exit direction; joint options are the cross product
  over all such agents. No STOP branching (`include_stop=False` flag exists),
  no departure-timing branching; all other agents implicitly `MOVE_FORWARD`.
- Children (and any new node) are deduplicated by a state hash over
  `(elapsed, per-agent pos/dir/state/malfunction/speed-counter)` — identical
  successor states merge into one node (the P1 rule), reconvergent branches
  merge into a DAG (P4).
- Deadlock events use `hard_deadlocked_agents` (mutual face-to-face pairs +
  convoys stuck behind them on single-transition cells) — **not**
  `scenario_runner.deadlocked_agents`, which also flags temporary
  follow-behind situations and would fire false events mid-rollout
  (post-mortem use is fine, mid-rollout it is not).
- Budgets `max_depth` / `max_nodes` / `max_wall_s`; truncation is counted and
  reported, never silent.

The measured node/edge counts on the test setups decide whether the full
policy-divergence graph (§1) needs aggressive pruning or none at all.

### Refinements after the first measurements (2026-07-22)

The first runs branched on *raw* per-step possibilities and exploded. Three
semantic fixes were added before the numbers below:

1. **Reasonable-exit filter** — at a switch, an exit only branches if the
   train's target is still reachable from it (finite `distance_map`) and the
   train has not already occupied that cell+direction on this branch (no
   loops). Reversing is impossible in Flatland, so "no driving backwards"
   reduces to the reachability check. If one reasonable exit remains, it is
   a *forced move*, not a branch point.
2. **Branch = decision outcome, not per-step action** — a train that chose an
   exit but is blocked carries a persistent *intent* (re-issued every step,
   no re-branching) until it actually leaves the decision cell. Pending
   intents are part of the node identity (state hash).
3. **Hard-deadlocked trains never branch** — their choice can never execute.
   Deadlock detection is a blocking-cycle fixpoint (`hard_deadlocked_agents`),
   not the loose face-to-face check.

The graph covers the **whole run** (root → all done / episode end); depth =
simulated time steps from the root, and the default cap is the episode's own
`max_episode_steps` (26-58 steps for the test envs below).

### Results (whole episode)

Small test env (25×25, 2 cities, seed 42, no malfunctions — the
`test_scenario_runner` pattern; episodes 26-58 steps):

| agents | budget | outcome |
| --- | --- | --- |
| 1 | any | **complete** — 91 nodes, 120 edges, 60 branch points, 30 merges, 1.1 s (episode = 26 steps) |
| 2 | 30 000 nodes | **complete** — 7 508 nodes, 11 356 edges, 3 849 merges, 971 loop-exits filtered, 145 s (episode = 54 steps) |
| 3 | 2 000 nodes | cap hit — >2 000 nodes, ~19 s; projected ≈ 91³ ≈ 7.5 × 10⁵ |
| 5 | 2 000 nodes | cap hit — >2 000 nodes, ~20 s; 75 deadlock futures found before the cap |

**Guided Demo Environment** (the UI's default study scenario:
`app.component.ts guidedDemoEnvOpts` — 36×24, 3 cities, 1 rail pair per
city, seed 42, malfunction rate 0.02, 400-step episode; run via
`--guided-demo`):

| agents | budget | outcome |
| --- | --- | --- |
| 1 | 2 000 nodes | cap hit — even the **single-train** route tree exceeds 2 000 nodes (1 153 loop-exits filtered, 73 dead-end fallbacks, 67 distinct arrival timings, 35 s). ~10-15 switches per journey → thousands of loop-free route variants |
| 8 (UI default) | 2 000 nodes | cap hit at depth 39 of 400 — barely past departure; 193 deadlock futures already found, 20 s |

Findings:

1. **The per-train intuition holds only on small networks**: a single
   train's route tree is ~91 nodes on the 25×25 test env (≈ "2⁵ routes +
   stop/arrival events"), but on the Guided Demo network a single train
   already has >2 000 loop-free route variants — "≤5 switches per mission"
   describes *sensible* routes, not all loop-free ones; the number of simple
   paths grows exponentially with switches passed (~10-15 there).
2. **The explosion is the joint-state product, not loops**: the complete
   2-train graph has 7 508 nodes ≈ 91² — every combination of (train A's
   route prefix, train B's route prefix) at the same time step is a distinct
   global state. Loops/backwards were filtered (971 exits) and were *not*
   the cause. Exhaustive joint enumeration is therefore infeasible for ≥3
   trains (~91ᴺ), by combinatorics, not by implementation.
3. **Most exhaustive futures are junk**: with every train defaulting to
   MOVE_FORWARD there is no dispatching intelligence, so a large share of
   branches end in deadlock (120 deadlock events in the 2-train graph).
   Policies eliminate these futures; they don't create them.
4. **Consequence for §1**: the holistic full-run view must come from the
   policy-divergence graph — branching only where policies *actually
   disagree* keeps the branch count near the per-train scale (a handful of
   genuine decision moments per train) instead of the joint product. The
   exhaustive builder stays as the measuring stick and stress-test harness;
   its machinery (fork, state-hash dedup, intents, event nodes, budgets) is
   reused as-is.
5. **Cost is fork-dominated**: ~3 forks/node, ~10-30 ms/node (persister
   tempfile round-trip). First lever if needed: in-memory serialization.

### Memory & capacity (measured, guided-demo env, 2 000-node builds)

- **The finished graph is cheap**: ~600-670 B/node serialized (2 000 nodes
  ≈ 1.2 MB JSON, ~7.5 MB retained in-process incl. overhead). Even a
  100 000-node graph would be ~60 MB payload — the graph itself never
  constrains size.
- **Frontier state is cheap**: env blobs are only 7-9 KB (+ visited sets
  per open node).
- **The build *process* was the problem — two Flatland pitfalls, both fixed
  in the builder and both relevant to any code that forks many envs (incl.
  `TrajectoryBranchRunner` in production):**
  1. Flatland decorates instance methods with global `@lru_cache`
     (`RailGridTransitionMap`, maxsize 4 000 000; also distance-map walkers
     etc.). Keys include `self`, so the caches pin every forked env forever —
     entries of dead envs can never be hits. With malfunctions enabled each
     pinned env drags a ~4 MB pre-drawn rand-array
     (`ParamMalfunctionGen.generate_rand_numbers`). A naive 2 000-node build
     retained **5.2 GB**; after sweeping all flatland `cache_clear`s every
     20 expansions + explicit `gc.collect()` (RailEnv is a reference cycle):
     **7.5 MB retained, ~0.9 GB peak** (malfunction env) / ~0.6 GB peak
     (no malfunctions — remaining peak is legitimate warm cache between
     sweeps).
  2. `RailEnv.__init__` has a single shared default `GlobalObsForRailEnv`
     instance (mutable default argument) that keeps the last env alive —
     harmless (1 env) but surprising.
- **The binding constraint is CPU time, not memory**: ~20-30 ms/node →
  ~5 s interactive budget ≈ 200-400 nodes; ~1 min background build ≈ 2-3 k;
  a few minutes offline ≈ 10-20 k. Memory would allow far larger graphs
  than time does. (Frontend note: >2-5 k SVG nodes also gets sluggish —
  collapse/level-of-detail needed beyond that.)

---

## 0b. Phase 1 — the policy-divergence graph (built)

`backend/app/core/policy_divergence_graph.py`
(`PolicyDivergenceGraphBuilder`), tests in
`backend/tests/test_policy_divergence_graph.py`, runnable standalone:

```sh
cd backend && python -m app.core.policy_divergence_graph --guided-demo
```

Semantics as built:

- All participating policies run in **lockstep on one shared state**;
  while they agree the world advances and no node is created.
- **Divergence is decided on resulting states**: differing proposals are
  stepped on probe forks and grouped by state hash. Two policies that
  express the same physical move differently never branch.
- **A persistent disagreement is ONE decision, not one per step.** This
  was the decisive correction (see below): a branch tracks the set of
  trains under unresolved dispute, and only a *newly* disputed train
  creates another node. While a dispute persists, the policy that owns
  the branch drives. `new_disputes_only=False` (CLI `--literal`) restores
  the naive per-step rule for comparison.
- `random` is excluded from the default participant set (nondeterministic
  → irreproducible graph, P2).

### Why the literal rule failed

The first run on the Guided Demo env branched at *every step*: DLA
proposes `STOP_MOVING` for a held train while ShortestPath proposes
`MOVE_FORWARD`, and that disagreement recurs every step for as long as
the train is held — 1 584 divergences, 2 000-node cap hit, only step 185
of 400 reached. The disagreement is a single dispatching decision
("hold T3 or run it"), not 150 of them. With the new-dispute rule the
same run produced ~1 000 nodes and reached the end of the episode.

### Measured: Guided Demo env, DLA vs. ShortestPath, whole run

Budget 4 000 nodes / 240 s. "whole-run" = every branch reached the
episode end or an all-done state; nothing cut by a budget.

| trains | nodes | divergences | falseDiv | ongoing | sec | whole run? |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 1 | 0 | 7 | 0 | 0.1 | ✅ |
| 3 | 4 | 0 | 57 | 0 | 0.6 | ✅ |
| 4 | 5 | 0 | 70 | 0 | 0.7 | ✅ |
| 5 | 1 462 | 521 | 7 140 | 8 172 | 147 | ✅ |
| 6 | 595 | 219 | 4 741 | 1 941 | 63 | ✅ |
| 8 (UI default) | 4 000 (cap) | 1 908 | 11 038 | 6 572 | 187 | ❌ |

Findings:

1. **The whole-run graph is fully buildable up to ~6 trains** in about a
   minute. The UI's 8-train default overflows a 4 000-node budget and
   needs either a larger budget, a horizon shorter than the full 400
   steps, or a coarser divergence rule.
2. **At 2-4 trains the two policies never disagree at all** — the graph
   is a single chain. That is a real answer, not a failure: on
   low-traffic instances there is nothing to decide, and the graph says
   so. Decision moments only appear once the network is contended.
3. **Both guards carry the load.** Without them the same runs explode:
   comparing states rather than actions absorbed 7-11 k would-be
   branches, and the new-dispute rule another 2-8 k. Both counters are
   reported in the stats so the pruning is visible, never silent.
4. Node count is not monotone in train count (6 trains → 595 nodes,
   5 → 1 462) because each agent count generates a different line/
   timetable, so contention differs per instance.

Sample output — the operator-facing payload is exactly the disagreement:

```text
divergence @step 34: deadlock_avoidance → T3:STOP_MOVING, T5:STOP_MOVING, T7:MOVE_LEFT
divergence @step 34: shortest_path      → T3:MOVE_FORWARD, T5:MOVE_FORWARD, T7:MOVE_FORWARD
```

### Routing decisions vs. timing differences (`decision_cells_only`, default on)

Observation from using the widget: almost no divergence is a route choice
at a switch. Of 85 forks on a 6-train run, **0** were pure
route-choice-at-a-switch, 5 pure hold-vs-run, 80 a mix — because DLA's
real disagreement with ShortestPath is *when to wait*, not *which way to
go*. (No policy can change a train's speed; `speed` is fixed at env
generation and the Guided Demo is uniform 1.0. Trains separating is DLA
holding one while SP runs it.)

DLA re-evaluates its hold every step, including mid-section where a train
is already committed — it cannot re-route there, so a disagreement is a
*timing* difference, not a routing decision. `decision_cells_only`
therefore branches only when a disputed train is still at a choice point;
mid-section, the world keeps following the policy that owns it.

**Where a decision belongs depends on which decision it is** — the two
are not interchangeable, and conflating them was a bug:

- **Hold vs. run → the MERGING cell, one field *before* the switch.**
  That is the last place a train can wait without fouling anything.
  Holding a train *on* a switch blocks the junction for every other
  train: an operating error, not an option worth branching on.
- **Which way → on the SWITCH**, since that is where the exit direction
  is actually chosen.
- Mid-section: neither — the train is committed.

Encoded in `is_hold_point` / `_at_decision_point` (keyed on whether STOP
is among the proposed actions) and locked by
`test_hold_point_is_the_cell_before_a_switch_not_the_switch`. Treating
SWITCH as a valid *hold* point made "standing on a switch" the single most
common stopped state in the graph (105 occurrences at 6 trains); with the
rule corrected it drops to 15, and those remaining are ShortestPath trains
*blocked by congestion*, not held by choice.

**A hold point is any cell whose *next* cell is a junction another train
may need.** There are two such approaches to the same junction, and they
classify differently — missing either one guts the graph:

- **Converging side → `MERGING`** (37 cell/heading pairs on the Guided
  Demo network). Your direction through the next cell has a single exit,
  but another direction into it has several (`opp_dir_options > 1`) —
  i.e. a train approaching from the other side has an alternative route.
  Stopping here leaves the junction free so that train can route around;
  entering it takes the alternative away and can deadlock both.
  Example: cell (7,16) heading East → junction (7,17): 1 exit for East,
  2 exits for West.
- **Diverging side → the next cell is a `SWITCH`** (51 pairs, disjoint
  from the above). Here *you* have the options. Stopping still matters
  for the same reason: the junction cell stays free for everyone else.
  These cells classify as **FORWARD_ONLY**, *not* MERGING — the MERGING
  test requires the next cell to have one exit for your heading, and a
  switch has several.

In turnout terms a switch has three connection points: one **facing**
(split) entry and two **trailing** (funneled) entries. The trailing
approaches are the `MERGING` cells; the facing approach is the
"next cell is a SWITCH" case.

**Both count as hold points here — a deliberate decision (2026-07-22).**
The strict turnout rule says you only wait before a trailing point,
because at a facing point you should pick a route instead of waiting.
That is true whenever a safe route exists — but entering a contested
single-track section *is* a facing-point choice, so when every onward
route is unsafe, waiting short of the switch is the only option. Both
approaches then share one principle: do not occupy a junction another
train may need.

The measurement that decided it: across a whole 8-train run the shipped
DLA issues **20 STOP actions — 18 at facing approaches, 1 mid-section,
1 on the junction, and none at all at a trailing approach.** Counting
only trailing holds therefore discards every hold DLA actually makes and
collapses the 8-train graph to 21 nodes of route choices. `is_hold_point`
accepts both approaches and rejects standing *on* the junction.

Worth revisiting if DLA is ever fixed to hold at proper trailing points:
the strict rule would then become viable, and the graph would show
genuine wait-decisions rather than "I could not pick a route" stops.

| trains | all disputes | routing only | whole run |
| --- | --- | --- | --- |
| 6 | 562 (49 s) | **230** (27 s) | ✅ both |
| 8 | 4 000 cap, 371 truncated | **752** (54 s) | ❌ → ✅ |

The gate skips very few forks outright (3 at 8 trains) but each skipped
fork removes a whole subtree, so the effect is ~5x: it is the difference
between a complete 8-train whole-run graph and one that never finishes.
Toggleable in the widget header and via `?decision_cells_only=false`.

**Are mid-section holds load-bearing? Measured: no.** Running the shipped
DLA against a DLA whose mid-section STOPs are suppressed (holds allowed
only at SWITCH/MERGING cells), on the Guided Demo env:

| trains | DLA as shipped | mid-section STOPs suppressed |
| --- | --- | --- |
| 5 | 5 arrived, 0 deadlocks, 120 steps | 5 arrived, 0 deadlocks, **116** steps (192 stops removed) |
| 6 | 6 arrived, 0 deadlocks, 87 steps | 6 arrived, 0 deadlocks, **83** steps (159 removed) |
| 8 | 8 arrived, 0 deadlocks, 113 steps | 8 arrived, 0 deadlocks, **112** steps (369 removed) |

720 mid-section stops removed across the three runs, zero deadlocks
caused, every run *finished sooner*. This matches the physical argument:
once both trains have entered a single-track section head-on the deadlock
is already determined, and Flatland trains cannot reverse — so the last
point where a hold changes the outcome is the section entry. **DLA's
every-step re-check is redundant for deadlock avoidance and costs
delay** (see "Follow-up" below).

An earlier version of this section claimed the gate loses real deadlock
futures. That conflated *coverage* with *causality* and is retracted. The
gate does explore fewer futures — 34 → 19 distinct deadlock situations at
5 trains — but the missing ones are not deadlocks that a mid-section hold
avoids. They are deadlocks reachable only in *hybrid timing worlds* (take
DLA's hold at one step and ShortestPath's at another): extra ways to cause
trouble by stopping a train mid-section for no reason, not extra ways out.
Each policy's own native behaviour, mid-section holds included, is still
fully explored inside its own branch.

Limits of this evidence: three instances on one network topology, and it
does not cover *involuntary* mid-section stops — a malfunction is exactly
that, so malfunction-shifted timing futures remain reachable by failure
even though they are not reachable by choice. That is a robustness
question, separate from the decision graph.

**Soundness trap found while building this.** The first cut resolved every
non-decision dispute by "the branch owner drives" — but the root has no
owner, so it fell back to the first-listed policy and silently showed that
policy's world: DLA first → 0 deadlock futures, ShortestPath first → 13,
from the same env. The root must branch instead of guessing. Locked by
`test_result_does_not_depend_on_participant_order`.

### Follow-up: DLA is over-conservative (not yet changed)

The measurement above is a finding about the *policy*, not the graph:
`DeadLockAvoidancePolicy` re-evaluates its hold every step, including
mid-section where the train is already committed and the hold cannot
change the routing outcome. Suppressing those holds was strictly better
on every instance tested (same arrivals, same zero deadlocks, fewer
steps).

Gating this inside the policy — only run the can-move check when the
agent is at a SWITCH/MERGING cell — would make DLA both faster and less
delay-prone. **Deliberately not done here:** DLA is the default baseline
for the live simulation, every forecast branch, and `ScenarioBuilder`, so
changing it shifts behaviour repo-wide and needs its own change with the
existing `backend/tests/test_deadlock_avoidance_policy.py` re-validated
and a wider instance sweep than the three runs above.

### Deadlock branches are dead ends (`prune_deadlocks`, default on)

A hard-deadlocked train can never reach its target, so no plan downstream
of that state is usable — there is nothing to look for past it. Expansion
therefore stops at the deadlock. The node stays in the graph, still marked
`event: "deadlock"` with its `deadlocked` handles, so the outcome remains
visible; it is simply terminal and has no outgoing edges. Reported as
`pruned_deadlock_branches` and shown in the widget header as "N dead
ends", so the pruning is never silent. Invariants locked by
`test_deadlock_branches_are_not_expanded`.

Measured with every other rule in place (complete whole-run graphs, no
truncation):

| trains | nodes | divergences | dead ends pruned | time |
| --- | --- | --- | --- | --- |
| 5 | 843 | 316 | 140 | 78 s |
| 6 | 230 | 83 | 31 | 28 s |
| 8 | 752 | 295 | 124 | 55 s |

Default budgets are 800 nodes / 60 s, sized so a complete 8-train
whole-run graph fits without truncation.

### Known limitation

A dispute is keyed by the *set of trains* involved, not by the actions
proposed. If the policies keep disagreeing about the same train but the
nature of the disagreement changes (STOP-vs-GO becoming LEFT-vs-RIGHT),
no new node is created. Keying on (handle, proposed actions) would catch
it at the cost of more branching — worth revisiting if such cases show up
in practice.

### Two Flatland pitfalls fixed along the way

Both live in `action_event_graph.py` and are shared by both builders;
both also apply to any code that forks envs (incl.
`TrajectoryBranchRunner`):

1. **`shared_distance_map()`** — `RailEnvPersister.set_full_state` calls
   `distance_map._compute()` on *every* load, bypassing Flatland's own
   "don't compute the distance map if it was loaded" guard in
   `AbstractDistanceMap.get()`. That BFS was **63 % of build time**. The
   map depends only on rail layout + targets, so it is computed once and
   shared by every fork — verified to produce byte-identical graphs, ~2x
   faster. (Process-global patch → a build must stay single-threaded.)
2. **`_clear_flatland_method_caches()`** — see §0 memory notes.

### Repo bug found: the "fixed seed 42" demo env is not reproducible

`env_factory._build_once` seeds the rail and line *generators* but never
passes `random_seed` to `RailEnv` itself, so the env's own RNG (schedule,
targets, malfunction draws) differs on every call. Two envs built with
seed 42 have **different agent targets** (4 573 differing distance-map
entries) — the guided demo is only identical *within* one session
because the same env object is reused across the three modes, not across
sessions. `app.component.ts` guidedDemoEnvOpts calls it a "fixed seed 42"
environment; that claim does not hold for a study replay.
`_build_guided_demo_env` re-resets with an explicit seed to keep
measurements comparable. **Worth fixing separately in `env_factory`.**

Confirmed sound: **forking is deterministic** — same blob + same actions
→ identical state hash across repeated forks, malfunctions included
(closes P7). The divergence test rests on this.

---

## 1. Goal

Give the operator an at-a-glance answer to *"what would each available policy
do from here, and where do their plans actually differ?"* — as an **event
graph** over simulated futures, instead of N independent parallel rollouts
(which is what `ScenarioBuilder` produces today).

### Semantics (as specified)

1. **Root node** = the current env state (the "start situation").
2. From a node, run **all participating policies in lockstep on the same
   state**: at each step, ask every policy for its joint action
   (`act_many` over all handles) *without* stepping yet.
3. **Consensus** — all policies propose the same joint action → apply it once,
   advance the shared state, and keep going. No node is created; we are not
   interested in states where everyone agrees.
4. **Divergence** — at least one policy proposes a different joint action →
   this is an event:
   - Group the policies by identical proposed joint action
     (e.g. `{DLA, ShortestPath}` vs `{ForwardOnly}` → 2 groups).
   - For each group: fork the state, apply that group's joint action → one
     **new child node** per group, connected to the parent, annotated with
     *which policies* produced it and *which agents' actions differed*.
   - Recurse: on **each** child node, again roll out **all** policies
     (per the task statement — not just the group that created the branch;
     see Problem P5 for the consequence of this choice).
5. **Additional (non-branching) event nodes** on the consensus path:
   - a train reaches its target (agent enters `DONE`),
   - a deadlock occurs (`deadlocked_agents(env)` grows).
   These create a chain node (single child) so arrivals/deadlocks are visible
   as events in the graph even when no divergence happens.
6. **Termination** of a branch: all agents done, horizon reached, episode's
   `max_steps` reached, or global node/depth budget exhausted (§7 P3).

### Node / edge data model (proposal)

```text
GraphNode:
  id: str                    # stable hash, see P4 (state dedup)
  step: int                  # env._elapsed_steps at this node
  event: "root" | "divergence" | "arrival" | "deadlock" | "terminal"
  agents: {handle: {pos, dir, state}}       # same shape as
                                            # ScenarioBuilder._capture_env_state
  arrived: [handle], deadlocked: [handle]   # cumulative at this node
  # transient, backend-only: pickled env blob or path for re-expansion

GraphEdge:
  from_id / to_id: str
  policy_ids: [str]          # policies whose proposed action produced this child
  steps: int                 # consensus steps compressed into this edge
  action_diff: {handle: {policy_id: action}}   # only agents that differed
                                               # (only for divergence edges)
```

The `action_diff` is the actual payload the operator cares about: *"at step
37, DLA stops train 2 while ShortestPath sends it left"*.

---

## 2. What exists and can be reused

| Piece | Where | Reuse |
| --- | --- | --- |
| Deterministic env forking | `backend/app/core/scenario_runner.py` `_fork_env()` (L306-326, `RailEnvPersister.save → load_new` + `_elapsed_steps` restore) | Extract into a free function `fork_env(env)`; the graph needs to fork from **arbitrary node states**, not only the session's base env |
| Deadlock event detection | `scenario_runner.py` `deadlocked_agents()` (L61-87) | Use as-is for the deadlock event nodes. Do **not** use `ConflictDetectionCallbacks` KPIs — all its detectors are stubs (`conflict_detector.py` L173-189) and return zeros |
| Arrival detection | `TrainState.DONE` check, as in `_count_done()` (L359-364) | As-is (diff the DONE set between steps) |
| Uniform policy interface | `app/policies/base.py` — `act_many(handles, observations)` + lifecycle hooks (`reset`, `start_step`, `end_step`) | This is the key enabler: every policy can be *queried* for its joint action without stepping the env. Observations use the same FullEnv-style fallback as `run_branch` (L259: `{h: env}`) |
| Policy roster + factories | `app/policies/registry.py` — `scenario_policy_factories()` filters on `supports_scenarios` | Participating set = `deadlock_avoidance`, `shortest_path`, `random` today. See P2 (random) and §5 (maybe widen the flag set for this feature) |
| Snapshot shape for the frontend | `scenario_builder.py` `_capture_env_state()` (L206-220) | Same `{step, agents:{h:{pos,dir}}}` shape for node payloads, so map-overlay code can be shared |
| Result caching pattern | `app/core/scenario_cache.py` (keyed on step/override-hash/kpi-hash) | Same pattern: the graph is a pure function of (env state, overrides, participant set, horizon) — cache per session, invalidate on step/override change |
| API + adapter pattern | `app/api/hmi.py` (`/hmi/scenarios` L113-253), `app/core/hmi_scenario_adapter.py` | Template for the new `/hmi/policy-graph` endpoint |
| Frontend panel plumbing | `features/*` + `panel-plugin-host.component.*` registration + `widget-catalog.ts` entry | Same registration flow as `whatif-compare` / `risk-uncertainty` |
| Map path overlay | `flatland-map.component.ts` L369-509 (dashed forecast paths from scenario trajectories) | Optional: clicking a graph node/edge overlays that branch's trajectory on the map |
| Operator overrides in branches | `ScenarioBuilder.generate_scenarios()` L130-136 pulls `override_manager.get_all(session)` and applies them to every branch | Do the same: committed overrides apply uniformly to all graph branches (they're facts of the world, not a policy choice) |

**Cross-reference (per repo policy — reuse, don't reinvent):**
`AI4REALNET/agent-as-a-service-trace-rl` already implements a
restore/simulate-forward service plus a Dash **tree visualisation of branching
trajectories**. Our branching driver is *policy divergence* rather than *human
override*, so the graph construction itself is new, but the visual language
(tree of futures, colour convention blue = human-influenced / yellow =
AI-simulated) should be aligned before designing the widget. All nodes in this
graph are AI-simulated (yellow family); if the graph is later extended with
override branches (natural fit with `whatif-compare`), those get the blue family.

---

## 3. What needs to be adapted

1. **`_fork_env` generalised** — currently a private method bound to
   `TrajectoryBranchRunner._base_env`. Promote to a module-level
   `fork_env(env) -> RailEnv` (keeping the `_elapsed_steps` fix) so the graph
   builder can fork from any node. `TrajectoryBranchRunner` then calls the
   shared helper — no behaviour change, existing tests must stay green.
2. **Policy registry** — either reuse `supports_scenarios` for graph
   participation or add a separate `supports_divergence_graph` flag.
   Recommendation: new flag, so we can *include* `forward_only` (its divergence
   from DLA/SP is exactly the kind of signal the graph shows) and *exclude*
   `random` (P2) without disturbing the existing scenario panel.
3. **`hmi.py`** — new endpoint; same session/cache/error handling shape as
   `/hmi/scenarios`.
4. **`widget-catalog.ts` + panel host** — register the new widget.

Nothing in the "do not touch" list (trajectory compression, scenario-refresh
throttling, `_recoverPolicyAndRetry*`) is affected; the graph is additive.

---

## 4. What needs to be created

### Backend

**`backend/app/core/policy_divergence_graph.py`** — the core module:

```python
@dataclass
class DivergenceGraph:          # nodes, edges, to_dict()
class DivergenceGraphBuilder:
    def __init__(self, base_env, participants: list[tuple[str, PolicyBranchFactory]],
                 overrides: dict, limits: GraphLimits): ...
    def build(self) -> DivergenceGraph
```

Core loop per node (lockstep consensus rollout):

```text
env = fork(node_state); policies = fresh instance per participant, reset(env)
for step in range(remaining_horizon):
    proposals = {pid: canonicalize(policy.act_many(handles, {h: env}), env)}
    groups = group_by_identical_proposal(proposals)
    if len(groups) == 1:
        env.step(the_common_action); advance all policies' lifecycle hooks
        if new arrivals / new deadlocks → emit chain event node
    else:
        for each group: child_env = fork(env); child_env.step(group_action)
        → emit divergence child nodes (dedup by state hash, P4), enqueue
        break
```

Non-obvious pieces inside:

- **`canonicalize(actions, env)`** — effective-action normalisation so that
  *cosmetically* different actions don't count as divergence (P1). Minimum
  viable rule set: drop agents that cannot act this step (off-map & not ready
  to depart, malfunctioning, `DONE`); on cells with a single transition map
  `MOVE_LEFT/RIGHT/FORWARD` to one canonical MOVE; treat `DO_NOTHING` for a
  moving agent as `MOVE_FORWARD` and for a stopped agent as `STOP_MOVING`
  (mirroring Flatland's own action masking).
- **Lockstep policy state** — DLA recomputes per-step internal maps in
  `start_step/end_step`; drive every participant's hooks every consensus step
  even though only one joint action is applied to the env. Fresh policy
  instances per node expansion (same reason `TrajectoryBranchRunner` takes a
  *factory*, `scenario_runner.py` L190-193).
- **Budget enforcement** — `GraphLimits(max_depth, max_nodes, max_wall_ms)`;
  on exhaustion mark open branches with `event: "terminal"` +
  `truncated: true` so the UI shows honestly that the future was cut off
  (repo rule: no silent caps).

**`backend/app/api/hmi.py`** — `GET /session/{sid}/hmi/policy-graph`
(query: `horizon`, `max_nodes`), returning `DivergenceGraph.to_dict()`, cached
per `(step, override_hash, participants, horizon)` via the `scenario_cache`
pattern. Compute on demand (poll-friendly), never inside the play loop.

**`backend/tests/test_policy_divergence_graph.py`** — at minimum:

- consensus-only episode → root + arrival/terminal chain, no divergence nodes;
- constructed divergence (e.g. DLA stops where SP proceeds at a conflict) →
  2 children with correct `policy_ids` and `action_diff`;
- canonicalisation: single-transition cells produce no false divergence
  (regression test: SP emits `MOVE_FORWARD` on `num_transitions <= 1`,
  `shortest_path_policy.py` L51-53, while another policy may emit an
  equivalent turn action);
- deadlock event node appears when `deadlocked_agents` grows;
- node/depth budget respected, `truncated` flagged;
- determinism: building twice from the same state yields the identical graph.

### Frontend

**`frontend/src/app/features/policy-divergence-graph/`** — new standalone
component (signals, SBB Lyne, registered in the panel host + widget catalog):

- **Layout:** layered DAG with **x = simulation step** — every node already
  has a step index, so no generic graph-layout library is needed; layout is
  "Marey-like": columns by step, rows by branch. Custom SVG, consistent with
  how `marey-chart` and `flatland-map` already hand-roll SVG.
- **Node rendering:** event glyph (divergence ◆ / arrival ● / deadlock ✕ /
  truncated ▷), tooltip with `action_diff` in plain language
  ("DLA: stop T2 — Shortest Path: T2 left at switch (12,34)").
- **Edge labels:** policy chips (labels from `/policies` metadata).
- **Colours:** semantic tokens only (no hex); agent colours via
  `AgentColorService`; A3S convention — all-AI branches in the yellow family,
  reserving blue for future human-override branches.
- **Interaction (first cut):** click node → overlay that branch's positions
  on the map (reuse the existing forecast-overlay input of `flatland-map`).

---

## 5. Suggested order of work

1. Extract `fork_env` helper; keep `scenario_runner` tests green.
2. `DivergenceGraphBuilder` with consensus rollout + divergence branching,
   *without* canonicalisation (raw action-dict equality) — get the machinery
   correct first.
3. Add canonicalisation + state-hash dedup; measure how much the graph shrinks
   (this validates P1 empirically).
4. Backend endpoint + cache + tests.
5. Frontend widget (static render first, then map-overlay interaction).
6. Registry flag / participant configuration UI (checkbox per policy).

---

## 6. Problems / risks

- **P1 — Raw action inequality ≠ real divergence.** *(Resolved, see §0.)*
  Policies express the same physical move differently: on a single-transition
  cell SP always returns `MOVE_FORWARD` (`shortest_path_policy.py` L51-53)
  while another policy may return the equivalent turn action; actions for
  off-map, malfunctioning or done agents are masked by the env and irrelevant.
  **Decision: compare the states the proposals produce, not the actions** —
  step each distinct proposal on a fork and merge children with identical
  state hashes. No canonicalisation heuristics needed.
- **P2 — `RandomPolicy` poisons the graph.** It is nondeterministic and
  disagrees with everything almost every step → immediate explosion, and the
  graph is not reproducible. *(Being quantified by the Phase 0 experiment,
  §0 — the exhaustive graph is the worst case any policy set can produce.)*
- **P3 — Combinatorial explosion.** Worst case the graph branches at every
  step into up to `#participants` children; with re-running *all* policies on
  every child (per spec), divergence right after a branch point is common.
  Mitigations: canonicalisation (P1), state-dedup/DAG-merge (P4), and hard
  budgets `max_depth` / `max_nodes` / wall-clock, with truncation surfaced in
  the UI. Realistic default: 3 policies, horizon ≈ 60-80 steps,
  `max_nodes ≈ 50`.
- **P4 — Tree vs DAG.** Different branches can reconverge to the same physical
  state (e.g. one policy stops a train two steps earlier, then both worlds look
  identical again). A state hash over
  `(elapsed % k, agent positions/dirs/states, malfunction counters)` lets us
  merge nodes and show *reconvergence* — arguably as interesting to the
  operator as divergence. Costs a design decision in the UI (DAG layout is
  slightly harder than tree layout). First cut may keep a tree and only flag
  "state identical to node N".
- **P5 — Branch semantics (per-spec choice).** Because *all* policies are
  re-run on every child, a path through the graph does **not** correspond to
  "policy X's trajectory"; it corresponds to "the world in which, at each
  divergence, X's proposal was taken". That is what was asked for, but the UI
  must label edges (not paths) with policies to avoid reading a branch as a
  single policy's plan. The alternative semantics (each branch continues only
  with its own group) would yield exactly the `ScenarioBuilder` parallel
  rollouts, just compressed — i.e. strictly less information. Sticking with
  the spec; flagging it so the choice is explicit.
- **P6 — Fork cost.** `RailEnvPersister.save/load_new` round-trips through a
  temp file (~tens of ms each); each divergence event needs one fork per
  child + one blob per frontier node for later re-expansion. With P3's budgets
  this stays in the hundreds-of-ms to low-seconds range — acceptable for an
  on-demand, cached endpoint, but the graph must **never** be rebuilt inside
  the play tick. If it becomes a bottleneck: keep serialized state as in-memory
  bytes (`RailEnvPersister` can target a path on a tmpfs / `io.BytesIO` shim)
  instead of touching disk.
- **P7 — Env stochasticity across forks.** Divergence comparison is only sound
  if two forks stepped with the same actions reach the same state — i.e. the
  malfunction generator's RNG state must survive the persister round-trip. The
  existing scenario system already assumes fork determinism ("clone an env
  deterministically", `scenario_runner.py` L23-25), but consensus rollouts here
  are longer-lived; verify with a regression test (same state + same actions →
  identical hash) before trusting the graph. If RNG state does *not* survive,
  all children must at least share one common post-fork seed policy so
  branches stay comparable with each other.
- **P8 — Zeroed conflict KPIs.** `ConflictDetectionCallbacks` is stubbed
  (detectors are `pass`, `conflict_detector.py` L173-189). The graph must rely
  only on the working primitives: `deadlocked_agents()` and `TrainState.DONE`.
  If node scoring is added later, `score_branch`'s delay/deadlock-cycle terms
  are currently dead — don't present scores as richer than they are.
- **P9 — Per-agent policies don't exist.** Policy is global per session
  (guardrail in `CLAUDE.md`); the graph compares *fleet-wide* policies. The
  `action_diff` is per-agent, which is fine, but "what if only train 3 used
  SP" is out of scope.

---

## 7. Open questions

1. **Participant set:** default to `deadlock_avoidance` + `shortest_path` +
   `forward_only` (deterministic, meaningfully different), `random` opt-in
   with seed? (§3.2, P2)
2. **Horizon default:** fixed (e.g. 80 steps, like `impact_analysis`) or
   remaining episode (like `/hmi/scenarios`)? Fixed is recommended given P3/P6.
3. **Reconvergence merging (P4):** tree with "reconverges with N" annotation
   (cheaper, first cut) or true DAG rendering?
4. Should clicking a divergence node offer a direct bridge to the existing
   `whatif-compare` widget (pre-filled with the differing action) so the
   operator can act on what the graph shows?
