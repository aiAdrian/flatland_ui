"""Mid-episode re-planning for the Director.

Splicing a new plan into a running episode is the delicate part, and it is
all here. The planning itself is the ordinary tree search, rooted on the
live situation instead of on an empty timetable (`tree_search.director`);
what this module owns is reading the world atomically, turning a re-plan
into player entries the trains can actually join, and deciding whether the
switch is worth making.

Capture (`capture_progress`) reads the live `SchedulePlayer`: per train,
the entries already consumed, where it stands on the current edge, the
wait already served, and the remaining malfunction time. From that it
builds, per train:

- a *seed prefix* — executed nodes plus the frontier node, whose wait is
  set so that the nominal departure from the frontier equals the earliest
  the train can actually leave;
- the *continue candidate* — seed plus the rest of the committed plan —
  which is what keeps driving if the re-plan is not taken;
- the splice bookkeeping (`pin_wait`, `serve_base`, `tail_anchor`) that
  turns a chosen absolute schedule back into player entries: the player
  serves `serve_base` (dwell still owed, malfunction remaining) plus
  whatever extra hold the search added on top of the pin.

Whether to commit is decided by simulation, not by the search's own score
— `rollout_gate` plays both branches forward on forks of the live episode
that share its future malfunctions, and commits only on a strictly better
outcome. A planner scoring its own proposal is exactly the comparison that
should not be trusted, and the measured history of this code base is that
it over-chooses re-planning when allowed to.

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

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from flatland.envs.rail_env import RailEnv
from flatland.envs.step_utils.states import TrainState

from app.policies.goal_based_policies.infrastructure_graph import (
    DecisionPointGraph,
)
from app.policies.goal_based_policies.schedule import (
    ScheduleEntry,
    SchedulePlayer,
    TrainSchedule,
    edge_time_windows,
)
from app.policies.tree_search import director
from app.policies.tree_search.metrics import DirectorWeights
from app.policies.tree_search.scenario import Scenario

# Steps a malfunction must still have to run for it to be worth re-planning
# around. Anything shorter is over before a search would finish.
MIN_MALFUNCTION_STEPS = 4


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
    weighted: float
    utilities: Dict[str, float]
    considered: Dict[str, float]
    decisions: int
    step: int
    reason: str
    trace: List[Dict[str, object]] = field(default_factory=list)

    def event(self) -> Dict[str, object]:
        """The JSON-able record of this re-plan for the plan info."""
        return {
            "step": self.step,
            "reason": self.reason,
            "source": self.source,
            "weighted": self.weighted,
            "utilities": dict(self.utilities),
            "considered": dict(self.considered),
            "decisions": self.decisions,
            "changed": sorted(self.tails),
        }


def _absolute(
    progress: TrainProgress, tail: TrainSchedule
) -> TrainSchedule:
    """A re-plan's tail, expressed as a schedule from the origin.

    The search plans from where the train stands, so its first entries are
    the node it is at (or the one it drove out of, mid-edge). `splice_entries`
    works on absolute schedules, so the captured prefix is put back in front
    — overlapping entries matched by node id rather than assumed, since a
    mid-edge train's anchor is two entries deep and a standing one's is one.
    """
    seed = list(progress.seed)
    entries = list(tail.entries)
    if not seed or not entries:
        return TrainSchedule(handle=tail.handle, entries=seed or entries)
    for overlap in (2, 1):
        if len(seed) >= overlap and len(entries) >= overlap and all(
            seed[-overlap + i].node_id == entries[i].node_id
            for i in range(overlap)
        ):
            return TrainSchedule(
                handle=tail.handle,
                entries=seed[:len(seed) - overlap] + entries,
            )
    # No overlap: the train is somewhere the re-plan did not start from.
    # Returning the seed alone makes `splice_entries` decline it, which is
    # the safe answer — better to keep driving than to teleport the plan.
    return TrainSchedule(handle=tail.handle, entries=seed)


def residual_plan(
    env: RailEnv,
    graph: DecisionPointGraph,
    weights: DirectorWeights,
    player: SchedulePlayer,
    schedules: Sequence[TrainSchedule],
    reason: str = "",
    now: Optional[int] = None,
    progress: Optional[Dict[int, TrainProgress]] = None,
    scenario: Optional[Scenario] = None,
    budget: int = director.REPLAN_BUDGET,
    models: Optional[Dict[str, object]] = None,
) -> ResidualPlan:
    """Re-plan the episode's remainder from where the trains actually are.

    The tree search is rooted on the live situation (`live.state_from_env`),
    so it decides only what is still open and every train keeps the progress
    it has made. What comes back are tails, which are put back behind the
    captured prefixes so the caller can splice them exactly as before.

    Whether the result is worth committing is *not* decided here. The
    search's own score would be judging its own proposal; the decision is
    made at application time by `rollout_gate`, which plays both branches
    forward on forks of the live episode and compares what actually
    happens.

    `progress` accepts a pre-captured state so the capture — which must
    read the live player and env atomically with the step loop — can be
    separated from the search, which reads only immutable env facts and may
    therefore run on a background thread while the episode keeps stepping.
    The tails are anchored to that capture; if the world moved on, re-anchor
    them with a fresh capture and `splice_entries` before applying.
    """
    if now is None:
        now = int(getattr(env, "_elapsed_steps", 0) or 0)
    if progress is None:
        progress = capture_progress(env, graph, player, schedules, now=now)
    scenario = scenario or Scenario.build(env, graph)

    plan = director.replan(
        scenario, env, weights=weights, budget=budget, models=models,
        player=player,
    )
    searched = {s.handle: s for s in plan.schedules}
    chosen: List[TrainSchedule] = []
    tails: Dict[int, List[ScheduleEntry]] = {}
    for handle in sorted(progress):
        committed = TrainSchedule(
            handle=handle, entries=list(progress[handle].continue_entries))
        tail = None
        if handle in searched:
            absolute = _absolute(progress[handle], searched[handle])
            tail = splice_entries(progress[handle], absolute)
        if tail is None:
            chosen.append(committed)
        else:
            tails[handle] = tail
            chosen.append(_absolute(progress[handle], searched[handle]))

    return ResidualPlan(
        schedules=chosen,
        tails=tails,
        source="research" if tails else "continue",
        weighted=plan.weighted,
        utilities=dict(plan.utilities),
        considered={"research": plan.weighted},
        decisions=plan.decisions,
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

