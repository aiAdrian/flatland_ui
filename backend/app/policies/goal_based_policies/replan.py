"""Mid-episode re-planning for the Director.

The residual problem is deliberately expressed in the language the value
models already speak: a full-horizon schedule from each train's origin,
in which everything up to the train's current position is *pinned* and
reality's delay is folded into a virtual wait at the train's frontier
node. State-conditioning happens through the existing encoding — pinned
prefixes and waits are ordinary schedule features the models were
trained on — so the installed checkpoints stay valid and no re-training
or new input scheme is needed. The trade-offs of that choice:

- Past occupancies keep their *nominal* times, not their actual ones.
  Harmless for the future (past windows cannot conflict with future
  ones), but the overlap pruner may see phantom overlaps between two
  pinned pasts; the search's clean-preference already degrades softly to
  score-only in that case.
- The models rank residual plans optimistically, so recovery re-plans
  are committed on simulated outcomes, not scores — see `rollout_gate`
  for the measured rationale.

Capture (`capture_progress`) reads the live `SchedulePlayer`: per train,
the entries already consumed, where it stands on the current edge, the
wait already served, and the remaining malfunction time. From that it
builds, per train:

- a *seed prefix* the search continues from — executed nodes plus the
  frontier node, whose wait is set so that the nominal departure time
  from the frontier equals the earliest the train can actually leave;
- the *continue candidate* — seed plus the rest of the committed plan —
  the do-nothing baseline every re-plan must beat;
- the splice bookkeeping (`pin_wait`, `serve_base`, `tail_anchor`) that
  turns a chosen absolute schedule back into player entries: the player
  serves `serve_base` (dwell still owed, malfunction remaining) plus
  whatever extra hold the search added on top of the pin.

`residual_plan` runs the ordinary search strategies from those seeds
(`seeds=` parameter) and holds the result against the continue
candidate under the same weighted score — mid-episode, ties keep the
current plan: churn needs to pay for itself.

What-if / simulate-forward: `simulate_forward` drives a forked env from
its current state to the episode end under a player and reports absolute
outcomes. Together with `capture_progress`/`residual_plan` on the fork
this is the A3S restore → simulate-forward → report contract
(`agent-as-a-service-trace-rl`) implemented in-process — an explicit
decision: the consortium service needs Redis plus
its own processes, while this repo's verify endpoint already forks envs;
the seam (fork, re-plan, roll forward, report) is kept narrow so the
service can replace it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from flatland.envs.rail_env import RailEnv
from flatland.envs.step_utils.states import TrainState

from app.policies.goal_based_policies.dataset import edge_time_windows
from app.policies.goal_based_policies.ensemble import (
    CandidateScore,
    DirectorWeights,
    ScenarioContext,
    score_candidates,
)
from app.policies.goal_based_policies.infrastructure_graph import (
    DecisionPointGraph,
)
from app.policies.goal_based_policies.safety import SafetyParams
from app.policies.goal_based_policies.schedule import (
    ScheduleEntry,
    SchedulePlayer,
    TrainSchedule,
)
from app.policies.goal_based_policies.search import (
    STRATEGIES,
    SearchLimits,
)

# A malfunction shorter than this resolves faster than a re-plan can pay
# off; the trigger ignores it.
MIN_MALFUNCTION_STEPS = 3


@dataclass(frozen=True)
class TrainProgress:
    """One train's captured mid-episode state, in schedule terms."""
    handle: int
    status: str                  # "pending" | "running" | "done" | "off_plan"
    seed: Tuple[ScheduleEntry, ...]
    continue_entries: Tuple[ScheduleEntry, ...]
    pin_wait: int      # the frontier entry's wait as pinned (virtual time)
    serve_base: int    # standing time the player still owes at the frontier
    tail_anchor: int   # trailing seed entries the player needs (2 = mid-edge)


def _malfunction_remaining(agent) -> int:
    handler = getattr(agent, "malfunction_handler", None)
    return int(getattr(handler, "malfunction_down_counter", 0) or 0)


def _nominal_arrival(
    env: RailEnv,
    graph: DecisionPointGraph,
    handle: int,
    entries: Sequence[ScheduleEntry],
) -> float:
    """When open-loop replay puts the train at the last entry's node. The
    last entry's own wait is not included — this is arrival, not
    departure."""
    windows = edge_time_windows(
        env, graph, TrainSchedule(handle=handle, entries=list(entries))
    )
    if windows:
        return float(windows[-1][2])
    agent = env.agents[handle]
    return float(getattr(agent, "earliest_departure", 0) or 0)


def _static(
    handle: int, status: str, entries: Sequence[ScheduleEntry]
) -> TrainProgress:
    """A train the re-plan must not touch: its committed plan, verbatim.
    A complete seed offers no route options, so the search skips it while
    its completion still occupies the network for everyone else."""
    fixed = tuple(entries)
    return TrainProgress(
        handle=handle, status=status, seed=fixed, continue_entries=fixed,
        pin_wait=0, serve_base=0, tail_anchor=0,
    )


def capture_progress(
    env: RailEnv,
    graph: DecisionPointGraph,
    player: SchedulePlayer,
    schedules: Sequence[TrainSchedule],
    now: Optional[int] = None,
) -> Dict[int, TrainProgress]:
    """Where every train stands right now, as pinned schedule prefixes.

    `schedules` are the committed full schedules the player was loaded
    with; the player itself tells how much of each is already consumed.
    """
    if now is None:
        now = int(getattr(env, "_elapsed_steps", 0) or 0)
    progress: Dict[int, TrainProgress] = {}

    for schedule in schedules:
        handle = schedule.handle
        full = list(schedule.entries)
        remaining = player.remaining(handle)
        executed = full[: len(full) - len(remaining)]
        agent = env.agents[handle]
        malfunction = _malfunction_remaining(agent)

        if agent.state == TrainState.DONE:
            progress[handle] = _static(handle, "done", full)
            continue

        if agent.position is None:
            # Not on the map yet: everything is still open, but entry may
            # already be overdue (blocked origin, pre-departure malfunction).
            departure = int(getattr(agent, "earliest_departure", 0) or 0)
            serve_base = full[0].wait if full else 0
            pin = max(0, max(now, departure) + malfunction - departure)
            seed = (ScheduleEntry(full[0].node_id, serve_base + pin),)
            progress[handle] = TrainProgress(
                handle=handle, status="pending", seed=seed,
                continue_entries=seed + tuple(full[1:]),
                pin_wait=seed[0].wait, serve_base=serve_base, tail_anchor=1,
            )
            continue

        located = player.locate(handle)
        if located is None or not remaining:
            # Standing on its final node, or off plan — either way there
            # is nothing left to re-decide for this train.
            status = "done" if len(remaining) <= 1 else "off_plan"
            progress[handle] = _static(
                handle, status, executed + remaining if remaining else full
            )
            continue

        edge, index = located
        if index == 0:
            # Standing on the current node, edge not yet entered.
            current = remaining[0]
            base = executed
            served = player.waited(handle)
            serve_base = max(current.wait - served, malfunction, 0)
            nominal = _nominal_arrival(
                env, graph, handle,
                base + [ScheduleEntry(current.node_id, 0)],
            )
            pin = max(0, now + serve_base - int(nominal))
            seed = tuple(base) + (ScheduleEntry(current.node_id, pin),)
            progress[handle] = TrainProgress(
                handle=handle, status="running", seed=seed,
                continue_entries=seed + tuple(remaining[1:]),
                pin_wait=pin, serve_base=serve_base, tail_anchor=1,
            )
            continue

        # Mid-edge: the train must reach the next node before it can act on
        # anything new, so the frontier is `remaining[1]`.
        frontier = remaining[1]
        base = executed + [remaining[0]]
        steps_left = len(edge.path) - 1 - index
        arrival = now + steps_left + malfunction
        serve_base = frontier.wait
        nominal = _nominal_arrival(
            env, graph, handle, base + [ScheduleEntry(frontier.node_id, 0)]
        )
        pin = max(0, arrival + serve_base - int(nominal))
        seed = tuple(base) + (ScheduleEntry(frontier.node_id, pin),)
        progress[handle] = TrainProgress(
            handle=handle, status="running", seed=seed,
            continue_entries=seed + tuple(remaining[2:]),
            pin_wait=pin, serve_base=serve_base, tail_anchor=2,
        )

    return progress


def splice_entries(
    progress: TrainProgress, final: TrainSchedule
) -> Optional[List[ScheduleEntry]]:
    """The player-facing tail of a chosen schedule, or None to keep the
    train's current entries.

    None when the train is static, or when the chosen schedule does not
    extend the captured seed (the search's dead-end fallback can produce
    an origin-planned schedule that no longer matches reality — splicing
    that would teleport the plan out from under the train).
    """
    if progress.status not in ("running", "pending"):
        return None
    seed = progress.seed
    entries = list(final.entries)
    if len(entries) < len(seed):
        return None
    if any(
        entries[i].node_id != seed[i].node_id for i in range(len(seed))
    ):
        return None

    extra = max(0, entries[len(seed) - 1].wait - progress.pin_wait)
    front = ScheduleEntry(seed[-1].node_id, progress.serve_base + extra)
    tail: List[ScheduleEntry] = []
    if progress.tail_anchor == 2:
        # The player's anchor is the node the train departed last; its wait
        # is behind the train — zeroed so an edge that rolls back over that
        # cell cannot trigger a spurious stand.
        tail.append(ScheduleEntry(seed[-2].node_id, 0))
    tail.append(front)
    tail.extend(entries[len(seed):])
    return tail


@dataclass
class ResidualPlan:
    """A mid-episode planning result: what to commit and the evidence."""
    schedules: List[TrainSchedule]        # full absolute schedules chosen
    tails: Dict[int, List[ScheduleEntry]]  # per-handle player splice
    source: str                            # "research" | "continue"
    score: CandidateScore
    considered: Dict[str, float]
    trace: List[Dict[str, object]]
    decisions: int
    step: int
    reason: str

    def event(self) -> Dict[str, object]:
        """The JSON-able record of this re-plan for the plan info."""
        return {
            "step": self.step,
            "reason": self.reason,
            "source": self.source,
            "weighted": self.score.weighted,
            "utilities": dict(self.score.breakdown["utilities"]),
            "considered": dict(self.considered),
            "decisions": self.decisions,
            "changed": sorted(self.tails),
        }


def residual_plan(
    env: RailEnv,
    graph: DecisionPointGraph,
    weights: DirectorWeights,
    evaluator,
    connection_model,
    player: SchedulePlayer,
    schedules: Sequence[TrainSchedule],
    reason: str = "",
    safety_params: SafetyParams = SafetyParams(),
    limits: SearchLimits = SearchLimits(),
    strategy: str = "greedy",
    context: Optional[ScenarioContext] = None,
    now: Optional[int] = None,
    progress: Optional[Dict[int, TrainProgress]] = None,
) -> ResidualPlan:
    """Re-plan the episode's remainder from the captured state.

    The search decides only what is still open; the result competes with
    simply continuing the committed plan, and — unlike at t=0 — ties keep
    the current plan: mid-episode churn has to pay for itself.

    `progress` accepts a pre-captured state so the capture (which must
    read the live player and env atomically with the step loop) can be
    separated from the search (which reads only immutable env facts and
    may therefore run on a background thread while the episode keeps
    stepping). The tails in the result are anchored to that capture —
    if the world moved since, re-anchor them with a fresh capture and
    `splice_entries` before applying.
    """
    if strategy not in STRATEGIES:
        raise ValueError(
            f"unknown strategy '{strategy}'; one of {sorted(STRATEGIES)}")
    if now is None:
        now = int(getattr(env, "_elapsed_steps", 0) or 0)
    if context is None:
        context = ScenarioContext.build(env, graph)

    if progress is None:
        progress = capture_progress(env, graph, player, schedules, now=now)
    order = sorted(progress)
    seeds = {handle: progress[handle].seed for handle in order}

    outcome = STRATEGIES[strategy](
        env, graph, context, weights, evaluator, connection_model,
        safety_params, limits, seeds=seeds,
    )
    keep = [
        TrainSchedule(handle=h, entries=list(progress[h].continue_entries))
        for h in order
    ]
    keep_score = score_candidates(
        context, [keep], weights, evaluator, connection_model, safety_params,
    )[0]

    considered = {
        "research": outcome.score.weighted,
        "continue": keep_score.weighted,
    }
    if outcome.score.weighted > keep_score.weighted:
        source, score = "research", outcome.score
        searched = {s.handle: s for s in outcome.schedules}
        kept = {s.handle: s for s in keep}
        chosen, tails = [], {}
        for handle in order:
            tail = splice_entries(progress[handle], searched[handle])
            if tail is not None:
                tails[handle] = tail
                chosen.append(searched[handle])
            else:
                # Static trains — and dead-end fallbacks whose schedule
                # abandoned the seed — keep their committed entries. The
                # stored plan must describe what actually drives, or the
                # *next* capture reads a plan the player never followed.
                chosen.append(kept[handle])
    else:
        source, chosen, score, tails = "continue", keep, keep_score, {}

    return ResidualPlan(
        schedules=list(chosen),
        tails=tails,
        source=source,
        score=score,
        considered=considered,
        trace=outcome.trace,
        decisions=outcome.decisions,
        step=now,
        reason=reason,
    )


def apply_residual_plan(player: SchedulePlayer, plan: ResidualPlan) -> None:
    """Splice the chosen tails into the live player. A "continue" plan has
    no tails and leaves the player untouched."""
    for handle, tail in plan.tails.items():
        player.set_schedule(TrainSchedule(handle=handle, entries=tail))


def rollout_gate(
    env: RailEnv, player: SchedulePlayer, plan: ResidualPlan
) -> Dict[str, object]:
    """Model proposes, simulation disposes: play both branches to the
    episode's end on forks and say whether the re-plan actually beats
    continuing.

    The `replan` CLI benchmark showed the models commit "research" far more
    often than reality rewards it (18/20 chosen, 3 wins vs 3 losses, one
    catastrophic), and the predicted margin does not separate the wins
    from the losses — the same Goodhart dynamic the t=0 portfolio guards
    against. Forks share the live env's RNG state, so both branches see
    the *same* future malfunction stream and the verdict is a paired
    ground truth, not an estimate. Better means: more trains arrive, or
    equally many with strictly less delay — recovery is judged on
    outcomes; the weighted model score already had its say in
    `residual_plan`. Ties keep the current plan.
    """
    import copy

    snapshot = player.snapshot()

    def branch(splice: bool) -> Dict[str, object]:
        fork = copy.deepcopy(env)
        fork_player = SchedulePlayer(player.graph, fork)
        fork_player.restore(snapshot)
        if splice:
            apply_residual_plan(fork_player, plan)
        return simulate_forward(fork, fork_player)

    keep = branch(False)
    switch = branch(True)
    commit = (
        (switch["arrived"], -switch["total_delay"])
        > (keep["arrived"], -keep["total_delay"])
    )
    return {"commit": bool(commit), "keep": keep, "switch": switch}


def new_malfunctions(
    env: RailEnv,
    known: set,
    now: Optional[int] = None,
    min_steps: int = MIN_MALFUNCTION_STEPS,
) -> List[Tuple[int, int]]:
    """Malfunctions worth reacting to that `known` has not seen yet, as
    `(handle, end_step)` — `end_step` is stable across the steps of one
    malfunction, so each outage triggers exactly once. Mutates `known`.
    """
    if now is None:
        now = int(getattr(env, "_elapsed_steps", 0) or 0)
    fresh: List[Tuple[int, int]] = []
    for agent in env.agents:
        down = _malfunction_remaining(agent)
        if down < min_steps:
            continue
        key = (int(agent.handle), now + down)
        if key not in known:
            known.add(key)
            fresh.append(key)
    return fresh


def simulate_forward(
    env: RailEnv,
    player: SchedulePlayer,
    watch_cells: Optional[Iterable[Tuple[int, int]]] = None,
) -> Dict[str, object]:
    """Drive `env` from its *current* state to the episode end and report
    absolute outcomes — `rollout.run_schedules` for a mid-episode fork.

    Steps are absolute (`env._elapsed_steps`), so delays stay comparable
    with `latest_arrival` deadlines. A train already DONE when the run
    starts counts as arrived with delay 0; events from before the fork
    are invisible to every branch alike, so what-if comparisons stay
    fair.
    """
    handles = sorted(player.snapshot())
    limit = int(
        getattr(env, "_max_episode_steps", 0)
        or int(getattr(env, "_elapsed_steps", 0) or 0) + 200
    )
    watched = {(int(c[0]), int(c[1])) for c in (watch_cells or ())}
    arrivals: Dict[int, Optional[int]] = {handle: None for handle in handles}
    occupancy: Dict[int, Dict[Tuple[int, int], Tuple[int, int]]] = {
        handle: {} for handle in handles
    }
    for handle in handles:
        if (arrivals[handle] is None
                and env.agents[handle].state == TrainState.DONE):
            arrivals[handle] = int(getattr(env, "_elapsed_steps", 0) or 0)

    step = int(getattr(env, "_elapsed_steps", 0) or 0)
    while step < limit:
        _, _, dones, _ = env.step(player.act_many(handles))
        step = int(getattr(env, "_elapsed_steps", step + 1) or step + 1)
        for handle in handles:
            agent = env.agents[handle]
            if watched and agent.position is not None:
                cell = (int(agent.position[0]), int(agent.position[1]))
                if cell in watched:
                    seen = occupancy[handle].get(cell)
                    occupancy[handle][cell] = (
                        (step, step) if seen is None else (seen[0], step)
                    )
            if arrivals[handle] is None and agent.state == TrainState.DONE:
                arrivals[handle] = step
        if all(arrivals[h] is not None for h in handles):
            break
        if dones.get("__all__"):
            break

    delays: Dict[int, int] = {}
    for handle in handles:
        latest = getattr(env.agents[handle], "latest_arrival", None)
        deadline = int(latest) if latest is not None else limit
        reference = arrivals[handle] if arrivals[handle] is not None else step
        delays[handle] = max(0, int(reference) - deadline)

    return {
        "all_arrived": all(arrivals[h] is not None for h in handles),
        "arrived": sum(1 for h in handles if arrivals[h] is not None),
        "trains": len(handles),
        "total_delay": int(sum(delays.values())),
        "max_delay": int(max(delays.values())) if delays else 0,
        "steps": int(step),
        "arrivals": arrivals,
        "delays": delays,
        "occupancy": occupancy,
    }


def _benchmark(
    scenarios: int,
    seed: int,
    mix_name: str,
    evaluator,
    connection_model,
    rate: float,
    min_duration: int,
    max_duration: int,
    horizon_factor: int,
    strategy: str,
    verbose: bool = True,
) -> Dict[str, object]:
    """The acceptance experiment: does reacting beat continuing?

    Per scenario: plan at t=0 on a malfunction-prone env, run two
    identical copies in lockstep until the first significant malfunction,
    then let one branch continue the committed plan while the other
    re-plans from the captured state — same malfunction stream (same
    seeds, same actions up to the split), so the comparison is paired.
    """
    import random

    from flatland.envs.malfunction_generators import (
        MalfunctionParameters,
        ParamMalfunctionGen,
    )

    from app.policies.goal_based_policies.dataset import Layout
    from app.policies.goal_based_policies.eval_set import mixes_by_name
    from app.policies.goal_based_policies.infrastructure_graph import (
        build_decision_point_graph,
    )
    from app.policies.goal_based_policies.search import director_plan
    from app.policies.goal_based_policies.visualization import build_demo_env

    def build(layout: Layout, trains: int) -> RailEnv:
        # `build_layout_env`'s exact flags, plus the malfunction stream —
        # so the layouts match the training distribution.
        env = build_demo_env(
            seed=layout.seed, width=layout.size, height=layout.size,
            number_of_agents=trains, max_num_cities=layout.cities,
            line_length=layout.line_length, flexible_terminus=True,
            malfunction_generator=ParamMalfunctionGen(MalfunctionParameters(
                malfunction_rate=rate, min_duration=min_duration,
                max_duration=max_duration,
            )),
        )
        env._max_episode_steps = int(
            (getattr(env, "_max_episode_steps", 0) or 200) * horizon_factor
        )
        return env

    mix = mixes_by_name([mix_name])[0]
    rng = random.Random(seed)
    weights = DirectorWeights()
    rows: List[Dict[str, object]] = []
    attempts = 0

    while len(rows) < scenarios and attempts < scenarios * 8:
        attempts += 1
        layout = Layout(
            index=attempts, seed=rng.randint(*mix.seed_range),
            size=rng.choice(mix.sizes), cities=rng.choice(mix.cities),
            line_length=mix.line_length,
        )
        trains = rng.randint(mix.min_trains, mix.max_trains)
        try:
            env_a = build(layout, trains)
            env_b = build(layout, trains)
            graph_a = build_decision_point_graph(env_a)
            graph_b = build_decision_point_graph(env_b)
            plan = director_plan(
                env_a, graph_a, weights, evaluator, connection_model,
                strategy="greedy",
            )
        except Exception:
            continue

        player_a = SchedulePlayer(graph_a, env_a, plan.schedules)
        player_b = SchedulePlayer(graph_b, env_b, plan.schedules)
        handles = sorted(s.handle for s in plan.schedules)
        limit = int(getattr(env_a, "_max_episode_steps", 0) or 200)

        known: set = set()
        trigger = None
        step = 0
        while step < limit and trigger is None:
            env_a.step(player_a.act_many(handles))
            env_b.step(player_b.act_many(handles))
            step = int(getattr(env_a, "_elapsed_steps", step + 1) or step + 1)
            fresh = new_malfunctions(env_a, known, now=step)
            if fresh:
                trigger = fresh[0]
            if all(env_a.agents[h].state == TrainState.DONE for h in handles):
                break
        if trigger is None:
            continue  # nothing to react to — not a re-planning scenario

        continued = simulate_forward(env_a, player_a)
        try:
            residual = residual_plan(
                env_b, graph_b, weights, evaluator, connection_model,
                player_b, plan.schedules,
                reason=f"malfunction on train {trigger[0]}",
                strategy=strategy,
            )
        except Exception:
            continue
        source = residual.source
        if source == "research":
            # The shipped behavior: the paired rollout gate has the last
            # word on whether the research plan is committed.
            verdict = rollout_gate(env_b, player_b, residual)
            if verdict["commit"]:
                apply_residual_plan(player_b, residual)
            else:
                source = "continue (gated)"
        replanned = simulate_forward(env_b, player_b)

        rows.append({
            "layout_seed": layout.seed, "size": layout.size,
            "trains": trains, "trigger_step": residual.step,
            "trigger_handle": trigger[0],
            "source": source,
            "predicted": residual.considered,
            "continue": {
                k: continued[k]
                for k in ("total_delay", "arrived", "all_arrived", "steps")
            },
            "replan": {
                k: replanned[k]
                for k in ("total_delay", "arrived", "all_arrived", "steps")
            },
        })
        if verbose:
            row = rows[-1]
            print(
                f"  scenario {len(rows)}/{scenarios}: size {layout.size} "
                f"trains {trains}, trigger t={row['trigger_step']} "
                f"[{row['source']}] delay {row['continue']['total_delay']}"
                f" -> {row['replan']['total_delay']} arrived "
                f"{row['continue']['arrived']} -> {row['replan']['arrived']}"
            )

    researched = [r for r in rows if r["source"] == "research"]
    summary = {
        "scenarios": len(rows),
        "chose_research": len(researched),
        "gated": sum(1 for r in rows if r["source"] == "continue (gated)"),
        "mean_delay_continue": (
            sum(r["continue"]["total_delay"] for r in rows) / len(rows)
            if rows else 0.0
        ),
        "mean_delay_replan": (
            sum(r["replan"]["total_delay"] for r in rows) / len(rows)
            if rows else 0.0
        ),
        "arrived_continue": sum(r["continue"]["arrived"] for r in rows),
        "arrived_replan": sum(r["replan"]["arrived"] for r in rows),
        "delay_wins": sum(
            1 for r in researched
            if r["replan"]["total_delay"] < r["continue"]["total_delay"]
        ),
        "delay_losses": sum(
            1 for r in researched
            if r["replan"]["total_delay"] > r["continue"]["total_delay"]
        ),
    }
    return {"rows": rows, "summary": summary}


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import json

    from app.policies.goal_based_policies.connection_model import (
        ConnectionTransformer,
    )
    from app.policies.goal_based_policies.evaluator import ScheduleEvaluator

    parser = argparse.ArgumentParser(description=_benchmark.__doc__)
    parser.add_argument("--scenarios", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--mix", default="control")
    parser.add_argument("--evaluator", required=True)
    parser.add_argument("--connection-model", required=True)
    parser.add_argument("--rate", type=float, default=1 / 120)
    parser.add_argument("--min-duration", type=int, default=10)
    parser.add_argument("--max-duration", type=int, default=30)
    parser.add_argument("--horizon-factor", type=int, default=2)
    parser.add_argument("--strategy", default="greedy",
                        choices=sorted(STRATEGIES))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    payload = _benchmark(
        scenarios=args.scenarios,
        seed=args.seed,
        mix_name=args.mix,
        evaluator=ScheduleEvaluator.load(args.evaluator),
        connection_model=ConnectionTransformer.load(args.connection_model),
        rate=args.rate,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        horizon_factor=args.horizon_factor,
        strategy=args.strategy,
    )
    summary = payload["summary"]
    print("summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print(f"written: {args.out}")
    return 0


__all__ = [
    "MIN_MALFUNCTION_STEPS",
    "ResidualPlan",
    "TrainProgress",
    "apply_residual_plan",
    "capture_progress",
    "new_malfunctions",
    "residual_plan",
    "rollout_gate",
    "simulate_forward",
    "splice_entries",
]


if __name__ == "__main__":
    raise SystemExit(main())
