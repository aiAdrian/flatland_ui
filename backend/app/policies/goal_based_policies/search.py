"""Model-guided schedule construction: greedy, beam and MCTS strategies.

The Director's planner. Greedy — the runtime default — walks decisions
chronologically
(`next_decision`): every option at the current choice node is completed
into a full candidate plan (`complete_from`), the candidates are scored by
the weighted ensemble, and the best branch is committed. Options free of
planned overlaps are preferred; when every option collides on paper — the
completions are conflict-blind, so late collisions are common — the score
decides alone rather than pruning the search into a corner.

`director_plan` adds the portfolio guarantee on top: the searched plan
competes against the two baseline planners (`plan_all_lines`,
`plan_avoiding_overlaps`) under the same weighted score, so by its own
judgment the Director never returns a plan worse than what already
existed. Ties prefer the search, whose trace explains itself.

The trace records, per decision, every option with its three utilities and
weighted score, which were considered (overlap-free) and which was chosen
— the raw material for the Director HMI's "why this route" view and for
the policy prior (`priors.py`).

Nothing here steps the env: scoring is models + static safety. Ground
truth comes from `verify_plan`, which *does* run the episode and therefore
wants a freshly built env.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from flatland.envs.rail_env import RailEnv

from app.policies.goal_based_policies.branching import (
    WAIT_MENU,
    complete_from,
    has_planned_overlap,
    initial_prefixes,
    next_decision,
)
from app.policies.goal_based_policies.connections import (
    evaluate_connections,
    observed_times,
    planned_connections,
    station_watch_cells,
)
from app.policies.goal_based_policies.dataset import (
    plan_all_lines,
)
from app.policies.goal_based_policies.ensemble import (
    CandidateScore,
    DirectorWeights,
    ScenarioContext,
    score_candidates,
)
from app.policies.goal_based_policies.infrastructure_graph import (
    DecisionPointGraph,
    build_decision_point_graph,
)
from app.policies.goal_based_policies.rollout import run_schedules
from app.policies.goal_based_policies.safety import SafetyParams, assess_safety
from app.policies.goal_based_policies.schedule import (
    TrainSchedule,
    plan_avoiding_overlaps,
    plan_line,
)


@dataclass(frozen=True)
class SearchLimits:
    k_routes: int = 3
    wait_menu: Tuple[int, ...] = WAIT_MENU
    max_decisions: int = 64
    beam_width: int = 4        # beam strategy: states kept per step
    simulations: int = 32      # mcts strategy: simulations per decision
    c_puct: float = 1.4        # mcts strategy: exploration constant


@dataclass
class SearchOutcome:
    schedules: List[TrainSchedule]
    score: CandidateScore
    trace: List[Dict[str, object]]
    decisions: int
    stuck: Tuple[int, ...]


@dataclass
class DirectorPlan:
    """What the Director commits: the winning plan, where it came from,
    and the evidence."""
    schedules: List[TrainSchedule]
    source: str                      # "search" | "lines" | "avoidance"
    score: CandidateScore
    considered: Dict[str, float]     # weighted score per portfolio entry
    trace: List[Dict[str, object]]
    decisions: int
    stuck: Tuple[int, ...] = ()

    def to_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "weighted": self.score.weighted,
            "utilities": {
                "punctuality": self.score.punctuality,
                "connections": self.score.connections,
                "stability": self.score.stability,
            },
            "considered": dict(self.considered),
            "decisions": self.decisions,
            "stuck": list(self.stuck),
            "schedules": {
                s.handle: s.to_flat_list() for s in self.schedules
            },
            "trace": self.trace,
        }


def _fallback(
    env: RailEnv, graph: DecisionPointGraph, handle: int, prefix
) -> TrainSchedule:
    """A full schedule for this train, whatever it takes: its completion,
    else the baseline line plan, else the bare prefix (which the safety
    measure will flag as unplayable rather than crash on)."""
    completed = complete_from(env, graph, handle, prefix)
    if completed is not None:
        return completed
    line = plan_line(graph, env, handle)
    if line is not None:
        return line
    return TrainSchedule(handle=handle, entries=list(prefix))


@dataclass
class _Expansion:
    """Every viable option of one decision, completed and scored."""
    decision: object
    options: List[object]                    # BranchOption per candidate
    candidates: List[List[TrainSchedule]]    # full plan per option
    scores: List[CandidateScore]
    clean: List[bool]
    considered: Set[int]                     # clean subset, or all if none


def _expand_and_score(
    env: RailEnv,
    graph: DecisionPointGraph,
    context: ScenarioContext,
    weights: DirectorWeights,
    evaluator,
    connection_model,
    safety_params: SafetyParams,
    prefixes: Dict[int, object],
    decision,
    order: List[int],
) -> Optional[_Expansion]:
    """Complete and score every option of `decision` against the other
    trains' completions — the step every strategy shares. None when all
    branches are dead ends."""
    others = {
        handle: _fallback(env, graph, handle, prefixes[handle])
        for handle in order if handle != decision.handle
    }
    candidates: List[List[TrainSchedule]] = []
    options = []
    for option in decision.options:
        mine = complete_from(env, graph, decision.handle, option.prefix)
        if mine is None:
            continue
        candidates.append([
            mine if handle == decision.handle else others[handle]
            for handle in order
        ])
        options.append(option)
    if not candidates:
        return None
    clean = [
        not has_planned_overlap(env, graph, candidate)
        for candidate in candidates
    ]
    considered = (
        {i for i, ok in enumerate(clean) if ok}
        if any(clean) else set(range(len(candidates)))
    )
    scores = score_candidates(
        context, candidates, weights, evaluator, connection_model,
        safety_params,
    )
    return _Expansion(
        decision=decision, options=options, candidates=candidates,
        scores=scores, clean=clean, considered=considered,
    )


def greedy_search(
    env: RailEnv,
    graph: DecisionPointGraph,
    context: ScenarioContext,
    weights: DirectorWeights,
    evaluator,
    connection_model,
    safety_params: SafetyParams = SafetyParams(),
    limits: SearchLimits = SearchLimits(),
    prior=None,  # every strategy shares a signature; greedy scores all
    #              options anyway, so a prior has nothing to focus
    seeds: Optional[Dict[int, object]] = None,
) -> SearchOutcome:
    """One greedy pass over all decisions. Deterministic: the models run
    in eval mode, ties keep the first (cheapest-route, shortest-hold)
    option, and the decision order is fixed by `next_decision`.

    `seeds` replaces the origin-only starting prefixes — the residual
    re-planner (`replan.py`) hands in each train's pinned progress so the
    search decides only what is still open.
    """
    prefixes = dict(seeds) if seeds is not None else initial_prefixes(env, graph)
    order = sorted(prefixes)
    stuck: Set[int] = set()
    trace: List[Dict[str, object]] = []
    decisions = 0

    while decisions < limits.max_decisions:
        open_prefixes = {
            handle: prefix for handle, prefix in prefixes.items()
            if handle not in stuck
        }
        decision = next_decision(
            env, graph, open_prefixes, limits.k_routes, limits.wait_menu
        )
        if decision is None:
            break

        expansion = _expand_and_score(
            env, graph, context, weights, evaluator, connection_model,
            safety_params, prefixes, decision, order,
        )
        if expansion is None:
            # Every branch is a dead end; the train keeps its prefix and
            # its completion fallback — nothing left to decide for it.
            stuck.add(decision.handle)
            trace.append({
                "handle": decision.handle, "node_id": decision.node_id,
                "time": decision.time, "stuck": True, "options": [],
            })
            continue

        options, scores = expansion.options, expansion.scores
        clean, considered = expansion.clean, expansion.considered
        chosen = max(sorted(considered), key=lambda i: scores[i].weighted)
        prefixes[decision.handle] = options[chosen].prefix
        trace.append({
            "handle": decision.handle,
            "node_id": decision.node_id,
            "time": decision.time,
            "chosen": chosen,
            "options": [
                {
                    "wait": option.wait,
                    "to_node": graph.node_id(option.edge.to_cell),
                    "clean": clean[i],
                    "considered": i in considered,
                    "weighted": scores[i].weighted,
                    "utilities": scores[i].breakdown["utilities"],
                }
                for i, option in enumerate(options)
            ],
        })
        decisions += 1

    final = [_fallback(env, graph, handle, prefixes[handle]) for handle in order]
    score = score_candidates(
        context, [final], weights, evaluator, connection_model, safety_params
    )[0]
    return SearchOutcome(
        schedules=final,
        score=score,
        trace=trace,
        decisions=decisions,
        stuck=tuple(sorted(stuck)),
    )


def _state_key(prefixes: Dict[int, object], stuck) -> str:
    return json.dumps([
        [handle, [[e.node_id, e.wait] for e in prefixes[handle]],
         handle in stuck]
        for handle in sorted(prefixes)
    ])


@dataclass
class _BeamState:
    prefixes: Dict[int, object]
    stuck: frozenset
    score: CandidateScore          # of this state's full completion
    schedules: List[TrainSchedule]


def _completed_state(
    env, graph, context, weights, evaluator, connection_model,
    safety_params, prefixes, stuck,
) -> _BeamState:
    order = sorted(prefixes)
    schedules = [_fallback(env, graph, h, prefixes[h]) for h in order]
    score = score_candidates(
        context, [schedules], weights, evaluator, connection_model,
        safety_params,
    )[0]
    return _BeamState(
        prefixes=prefixes, stuck=frozenset(stuck), score=score,
        schedules=schedules,
    )


def beam_search(
    env: RailEnv,
    graph: DecisionPointGraph,
    context: ScenarioContext,
    weights: DirectorWeights,
    evaluator,
    connection_model,
    safety_params: SafetyParams = SafetyParams(),
    limits: SearchLimits = SearchLimits(),
    prior=None,  # shared signature; the beam scores every successor too
    seeds: Optional[Dict[int, object]] = None,
) -> SearchOutcome:
    """Top-`beam_width` partial plans instead of one.

    Each step advances every beam state by its own next decision and
    keeps the globally best successors by completed-plan score — so a
    branch that looks mediocre for one decision but pays off later can
    survive where greedy commits early. Same clean-option preference as
    greedy, per expansion. Deterministic: pool order is beam order ×
    option order, dedup and ties keep the first.

    The trace is step-level (pool size, surviving scores) rather than
    per-decision: a beam has no single decision path until it ends.
    """
    starting = dict(seeds) if seeds is not None else initial_prefixes(env, graph)
    order = sorted(starting)
    start = _completed_state(
        env, graph, context, weights, evaluator, connection_model,
        safety_params, starting, frozenset(),
    )
    beam: List[_BeamState] = [start]
    finished: List[_BeamState] = []
    trace: List[Dict[str, object]] = []

    for step in range(limits.max_decisions):
        pool: List[_BeamState] = []
        progressed = False
        for state in beam:
            open_prefixes = {
                h: p for h, p in state.prefixes.items()
                if h not in state.stuck
            }
            decision = next_decision(
                env, graph, open_prefixes, limits.k_routes, limits.wait_menu
            )
            if decision is None:
                finished.append(state)
                continue
            progressed = True
            expansion = _expand_and_score(
                env, graph, context, weights, evaluator, connection_model,
                safety_params, state.prefixes, decision, order,
            )
            if expansion is None:
                pool.append(_BeamState(
                    prefixes=state.prefixes,
                    stuck=state.stuck | {decision.handle},
                    score=state.score, schedules=state.schedules,
                ))
                continue
            for i in sorted(expansion.considered):
                prefixes = dict(state.prefixes)
                prefixes[decision.handle] = expansion.options[i].prefix
                pool.append(_BeamState(
                    prefixes=prefixes, stuck=state.stuck,
                    score=expansion.scores[i],
                    schedules=expansion.candidates[i],
                ))
        if not progressed:
            break
        seen = set()
        survivors: List[_BeamState] = []
        for state in sorted(pool, key=lambda s: -s.score.weighted):
            key = _state_key(state.prefixes, state.stuck)
            if key in seen:
                continue
            seen.add(key)
            survivors.append(state)
            if len(survivors) == limits.beam_width:
                break
        beam = survivors
        trace.append({
            "step": step,
            "expanded": len(pool),
            "beam": [round(s.score.weighted, 6) for s in beam],
            "finished": len(finished),
        })
        if not beam:
            break

    finalists = finished + beam
    best = max(finalists, key=lambda s: s.score.weighted)
    return SearchOutcome(
        schedules=best.schedules,
        score=best.score,
        trace=trace,
        decisions=len(trace),
        stuck=tuple(sorted(best.stuck)),
    )


class _MctsNode:
    """One search state: expanded lazily into its decision's options."""

    def __init__(self, prefixes: Dict[int, object], stuck: frozenset):
        self.prefixes = prefixes
        self.stuck = stuck
        self.expansion: Optional[_Expansion] = None
        self.terminal: Optional[_BeamState] = None
        self.children: Dict[int, "_MctsNode"] = {}
        self.visits: Dict[int, int] = {}
        self.values: Dict[int, float] = {}
        self.priors: Optional[Dict[int, float]] = None

    def expand(self, env, graph, context, weights, evaluator,
               connection_model, safety_params, limits, order) -> None:
        stuck = set(self.stuck)
        while True:
            open_prefixes = {
                h: p for h, p in self.prefixes.items() if h not in stuck
            }
            decision = next_decision(
                env, graph, open_prefixes, limits.k_routes, limits.wait_menu
            )
            if decision is None:
                self.terminal = _completed_state(
                    env, graph, context, weights, evaluator,
                    connection_model, safety_params, self.prefixes, stuck,
                )
                return
            expansion = _expand_and_score(
                env, graph, context, weights, evaluator, connection_model,
                safety_params, self.prefixes, decision, order,
            )
            if expansion is not None:
                self.stuck = frozenset(stuck)
                self.expansion = expansion
                return
            stuck.add(decision.handle)


def _node_priors(node: "_MctsNode", choices, prior, n_waits: int
                 ) -> Dict[int, float]:
    """Per-option prior mass over the considered choices, cached on the
    node. Uniform without a model; with one, the learned distribution is
    renormalised over the considered subset."""
    if node.priors is None:
        if prior is None:
            node.priors = {i: 1.0 / len(choices) for i in choices}
        else:
            exp = node.expansion
            raw = prior.probabilities(
                [{"wait": option.wait, "clean": exp.clean[i]}
                 for i, option in enumerate(exp.options)],
                n_waits=n_waits,
            )
            mass = sum(raw[i] for i in choices) or 1.0
            node.priors = {i: raw[i] / mass for i in choices}
    return node.priors


def mcts_search(
    env: RailEnv,
    graph: DecisionPointGraph,
    context: ScenarioContext,
    weights: DirectorWeights,
    evaluator,
    connection_model,
    safety_params: SafetyParams = SafetyParams(),
    limits: SearchLimits = SearchLimits(),
    prior=None,
    seeds: Optional[Dict[int, object]] = None,
) -> SearchOutcome:
    """PUCT tree search with the value ensemble at the leaves, no
    rollouts — the completion score *is* the leaf value, exactly as in
    the other strategies. `prior` (a `priors.BranchPrior`, optional)
    replaces the uniform expansion prior with the learned one; the value
    ensemble stays in charge of judging what got expanded.

    AlphaZero-shaped control flow: `simulations` simulations per root
    decision, then the most-visited option is committed and the root
    advances. Deterministic: no randomness anywhere; unvisited options
    start from their leaf score (first-play urgency), ties keep the
    lowest index. Each simulation expands at most one node, and an
    expansion scores all of a node's options in one batch. The trace
    records visit counts and mean values per option — the training
    signal for the future policy prior.
    """
    import math

    prefixes = dict(seeds) if seeds is not None else initial_prefixes(env, graph)
    order = sorted(prefixes)
    stuck: frozenset = frozenset()
    trace: List[Dict[str, object]] = []
    decisions = 0

    while decisions < limits.max_decisions:
        root = _MctsNode(prefixes, stuck)
        root.expand(env, graph, context, weights, evaluator,
                    connection_model, safety_params, limits, order)
        if root.terminal is not None:
            break

        for _ in range(limits.simulations):
            node, path = root, []
            while True:
                if node.terminal is not None:
                    value = node.terminal.score.weighted
                    break
                if node.expansion is None:
                    node.expand(env, graph, context, weights, evaluator,
                                connection_model, safety_params, limits,
                                order)
                    if node.terminal is not None:
                        value = node.terminal.score.weighted
                    else:
                        value = max(
                            node.expansion.scores[i].weighted
                            for i in node.expansion.considered
                        )
                    break
                exp = node.expansion
                total = sum(node.visits.values()) + 1
                choices = sorted(exp.considered)
                priors = _node_priors(
                    node, choices, prior, len(limits.wait_menu))

                def puct(i):
                    n = node.visits.get(i, 0)
                    q = (node.values[i] / n if n
                         else exp.scores[i].weighted)
                    return q + limits.c_puct * priors[i] * math.sqrt(total) / (1 + n)

                best = max(choices, key=puct)
                path.append((node, best))
                child = node.children.get(best)
                if child is None:
                    child_prefixes = dict(node.prefixes)
                    child_prefixes[exp.decision.handle] = (
                        exp.options[best].prefix)
                    child = _MctsNode(child_prefixes, node.stuck)
                    node.children[best] = child
                node = child
            for parent, action in path:
                parent.visits[action] = parent.visits.get(action, 0) + 1
                parent.values[action] = (
                    parent.values.get(action, 0.0) + value)

        exp = root.expansion
        choices = sorted(exp.considered)
        chosen = max(choices, key=lambda i: (
            root.visits.get(i, 0),
            root.values.get(i, 0.0) / max(root.visits.get(i, 1), 1),
            -i,
        ))
        trace.append({
            "handle": exp.decision.handle,
            "node_id": exp.decision.node_id,
            "time": exp.decision.time,
            "chosen": chosen,
            "options": [
                {
                    "wait": option.wait,
                    "to_node": graph.node_id(option.edge.to_cell),
                    "clean": exp.clean[i],
                    "considered": i in exp.considered,
                    "weighted": exp.scores[i].weighted,
                    "visits": root.visits.get(i, 0),
                    "mean_value": (
                        root.values.get(i, 0.0)
                        / max(root.visits.get(i, 1), 1)),
                    "utilities": exp.scores[i].breakdown["utilities"],
                }
                for i, option in enumerate(exp.options)
            ],
        })
        prefixes = dict(prefixes)
        prefixes[exp.decision.handle] = exp.options[chosen].prefix
        stuck = root.stuck
        decisions += 1

    final = [_fallback(env, graph, handle, prefixes[handle])
             for handle in order]
    score = score_candidates(
        context, [final], weights, evaluator, connection_model, safety_params
    )[0]
    return SearchOutcome(
        schedules=final, score=score, trace=trace, decisions=decisions,
        stuck=tuple(sorted(stuck)),
    )


STRATEGIES = {
    "greedy": greedy_search,
    "beam": beam_search,
    "mcts": mcts_search,
}


def director_plan(
    env: RailEnv,
    graph: DecisionPointGraph,
    weights: DirectorWeights,
    evaluator,
    connection_model,
    safety_params: SafetyParams = SafetyParams(),
    limits: SearchLimits = SearchLimits(),
    context: Optional[ScenarioContext] = None,
    strategy: str = "greedy",
    prior=None,
) -> DirectorPlan:
    """Search, then hold the result against the baseline planners under
    the same weighted score. See the module docstring."""
    if strategy not in STRATEGIES:
        raise ValueError(
            f"unknown strategy '{strategy}'; one of {sorted(STRATEGIES)}")
    if context is None:
        context = ScenarioContext.build(env, graph)
    outcome = STRATEGIES[strategy](
        env, graph, context, weights, evaluator, connection_model,
        safety_params, limits, prior=prior,
    )
    portfolio: Dict[str, Tuple[List[TrainSchedule], CandidateScore]] = {
        "search": (outcome.schedules, outcome.score),
    }
    base = plan_all_lines(env, graph)
    if base is not None:
        avoided = plan_avoiding_overlaps(env, graph, base)
        scored = score_candidates(
            context, [base, avoided], weights, evaluator, connection_model,
            safety_params,
        )
        portfolio["lines"] = (base, scored[0])
        portfolio["avoidance"] = (avoided, scored[1])

    source = "search"
    for name in ("lines", "avoidance"):
        if name in portfolio and (
            portfolio[name][1].weighted > portfolio[source][1].weighted
        ):
            source = name
    schedules, score = portfolio[source]
    return DirectorPlan(
        schedules=schedules,
        source=source,
        score=score,
        considered={
            name: entry[1].weighted for name, entry in portfolio.items()
        },
        trace=outcome.trace,
        decisions=outcome.decisions,
        stuck=outcome.stuck,
    )


def verify_plan(
    env: RailEnv,
    graph: DecisionPointGraph,
    stations: Sequence,
    schedules: Sequence[TrainSchedule],
    safety_params: SafetyParams = SafetyParams(),
) -> Dict[str, object]:
    """Ground truth for a plan: one full episode. Steps `env` to its end —
    hand in a freshly built env, not one another rollout already used."""
    connections = planned_connections(env, stations)
    result = run_schedules(
        env, graph, schedules, watch_cells=station_watch_cells(stations)
    )
    report = evaluate_connections(
        connections, observed_times(stations, result.occupancy)
    )
    safety = assess_safety(env, graph, schedules, params=safety_params)
    return {
        "total_delay": int(result.total_delay),
        "all_arrived": bool(result.all_arrived),
        "bucket": int(result.bucket),
        "connections_total": int(report.total),
        "connections_kept": int(report.kept),
        "kept_ratio": float(report.kept_ratio),
        "safety": float(safety.safety),
        "steps": int(result.steps),
    }


# The sweep's fixed weight settings: three corners and the balanced middle.
SWEEP_WEIGHTS = {
    "punctuality": DirectorWeights(1, 0, 0),
    "connections": DirectorWeights(0, 1, 0),
    "stability": DirectorWeights(0, 0, 1),
    "balanced": DirectorWeights(1, 1, 1),
}


def sweep(
    scenarios: int,
    seed: int,
    mix_name: str,
    evaluator,
    connection_model,
    limits: SearchLimits = SearchLimits(),
    strategy: str = "greedy",
    verbose: bool = True,
) -> Dict[str, object]:
    """The acceptance experiment: do the dials steer ground truth?

    Held-out scenarios, the two baseline planners, and one Director plan
    per weight setting — every plan verified by a full episode on a
    freshly built env. Aggregates are paired (same scenarios in every
    row), so "wins vs lines" counts scenarios strictly better than the
    conflict-blind baseline on that setting's own axis.
    """
    import random

    from app.policies.goal_based_policies.dataset import (
        Layout, build_layout_env,
    )
    from app.policies.goal_based_policies.eval_set import mixes_by_name
    from app.policies.goal_based_policies.stations import resolve_stations

    mix = mixes_by_name([mix_name])[0]
    rng = random.Random(seed)
    rows: List[Dict[str, object]] = []
    attempts = 0
    while len(rows) < scenarios and attempts < scenarios * 6:
        attempts += 1
        layout = Layout(
            index=attempts, seed=rng.randint(*mix.seed_range),
            size=rng.choice(mix.sizes), cities=rng.choice(mix.cities),
            line_length=mix.line_length,
        )
        trains = rng.randint(mix.min_trains, mix.max_trains)
        try:
            env = build_layout_env(layout, trains)
            graph = build_decision_point_graph(env)
            base = plan_all_lines(env, graph)
        except Exception:
            continue
        if base is None:
            continue
        context = ScenarioContext.build(env, graph)

        plans: Dict[str, Tuple[List[TrainSchedule], Optional[str]]] = {
            "lines": (base, None),
            "avoidance": (plan_avoiding_overlaps(env, graph, base), None),
        }
        predicted: Dict[str, float] = {}
        for name, weights in SWEEP_WEIGHTS.items():
            plan = director_plan(
                env, graph, weights, evaluator, connection_model,
                limits=limits, context=context, strategy=strategy,
            )
            plans[name] = (plan.schedules, plan.source)
            predicted[name] = plan.score.weighted

        # One rollout per distinct plan; identical plans share it.
        verified_by_key: Dict[str, Dict[str, object]] = {}
        row: Dict[str, object] = {
            "layout_seed": layout.seed, "size": layout.size,
            "trains": trains,
        }
        for name, (schedules, source) in plans.items():
            key = json.dumps([s.to_flat_list() for s in schedules])
            if key not in verified_by_key:
                fresh = build_layout_env(layout, trains)
                fresh_graph = build_decision_point_graph(fresh)
                verified_by_key[key] = verify_plan(
                    fresh, fresh_graph, resolve_stations(fresh), schedules,
                )
            row[name] = dict(verified_by_key[key])
            if source is not None:
                row[name]["source"] = source
                row[name]["predicted"] = predicted[name]
        rows.append(row)
        if verbose:
            done = row["balanced"]
            print(f"  scenario {len(rows)}/{scenarios}: size {layout.size} "
                  f"trains {trains}, balanced delay {done['total_delay']} "
                  f"kept {done['kept_ratio']:.2f} safety {done['safety']:.2f}")

    settings = ["lines", "avoidance", *SWEEP_WEIGHTS]
    axis = {
        "punctuality": ("total_delay", min), "connections": ("kept_ratio", max),
        "stability": ("safety", max), "balanced": ("total_delay", min),
    }
    summary: Dict[str, Dict[str, float]] = {}
    for name in settings:
        entries = [row[name] for row in rows]
        summary[name] = {
            "mean_delay": sum(e["total_delay"] for e in entries) / len(entries),
            "arrived_rate": sum(e["all_arrived"] for e in entries) / len(entries),
            "mean_kept_ratio": sum(e["kept_ratio"] for e in entries) / len(entries),
            "mean_safety": sum(e["safety"] for e in entries) / len(entries),
        }
        if name in axis:
            metric, better = axis[name]
            summary[name]["wins_vs_lines"] = sum(
                1 for row in rows
                if better(row[name][metric], row["lines"][metric])
                == row[name][metric]
                and row[name][metric] != row["lines"][metric]
            )
        if name in SWEEP_WEIGHTS:
            sources = [row[name].get("source") for row in rows]
            summary[name]["source_search"] = sources.count("search")
    return {"rows": rows, "summary": summary, "scenarios": len(rows)}


def _print_sweep(payload: Dict[str, object]) -> None:
    header = (f"{'plan':<13}{'delay':>8}{'arrived':>9}{'kept':>7}"
              f"{'safety':>8}{'wins':>6}{'search':>8}")
    print(header)
    print("-" * len(header))
    for name, stats in payload["summary"].items():
        wins = stats.get("wins_vs_lines")
        search = stats.get("source_search")
        print(f"{name:<13}{stats['mean_delay']:>8.1f}"
              f"{stats['arrived_rate']:>9.2f}{stats['mean_kept_ratio']:>7.2f}"
              f"{stats['mean_safety']:>8.3f}"
              f"{'' if wins is None else wins:>6}"
              f"{'' if search is None else search:>8}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    from app.policies.goal_based_policies.connection_model import (
        ConnectionTransformer,
    )
    from app.policies.goal_based_policies.evaluator import ScheduleEvaluator

    parser = argparse.ArgumentParser(description=sweep.__doc__)
    parser.add_argument("--scenarios", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--mix", default="control")
    parser.add_argument("--evaluator", required=True)
    parser.add_argument("--connection-model", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--k-routes", type=int, default=3)
    parser.add_argument("--max-decisions", type=int, default=64)
    parser.add_argument("--strategy", default="greedy",
                        choices=sorted(STRATEGIES))
    parser.add_argument("--beam-width", type=int, default=4)
    parser.add_argument("--simulations", type=int, default=32)
    args = parser.parse_args(argv)

    payload = sweep(
        scenarios=args.scenarios,
        seed=args.seed,
        mix_name=args.mix,
        evaluator=ScheduleEvaluator.load(args.evaluator),
        connection_model=ConnectionTransformer.load(args.connection_model),
        limits=SearchLimits(
            k_routes=args.k_routes, max_decisions=args.max_decisions,
            beam_width=args.beam_width, simulations=args.simulations),
        strategy=args.strategy,
    )
    _print_sweep(payload)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print(f"written: {args.out}")
    return 0


__all__ = [
    "DirectorPlan",
    "SWEEP_WEIGHTS",
    "SearchLimits",
    "SearchOutcome",
    "beam_search",
    "director_plan",
    "greedy_search",
    "mcts_search",
    "sweep",
    "verify_plan",
]


if __name__ == "__main__":
    raise SystemExit(main())
