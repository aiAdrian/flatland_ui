"""The Director planner as a session policy.

Plans every train once per env with the tree search over railway states
(`tree_search.director`), then drives the result with `SchedulePlayer`.
The three weights — punctuality, connections, stability — are the
Director-mode dials; only the metrics with a network behind them steer
anything today (see `tree_search.metrics.METRICS`), and the plan info says
which of the dials those are.

Mid-episode the plan is not fixed: a malfunction of consequence — or a
weight change while trains are already on the map — triggers a *residual*
re-plan (`replan.py`) from the captured current state, spliced into the
live player only when it out-scores continuing the committed plan. Every
re-plan is recorded in the plan info under `"replans"`.

Session APIs rebuild the Policy object on every request, so nothing
useful can live on the instance: the plan, the player's progress and the
plan's provenance are cached per *env* (weak-keyed — a dropped env takes
its plan with it). `reset(env)` plans only when the env has no plan yet.

torch is imported lazily and only when a value-network checkpoint is
actually found (`TREE_SEARCH_MODELS`, defaulting to
`backend/models/tree_search/`). Without one the search still plans — it
values every state alike and falls back on its own ordering, which is
exactly what generation zero of training does — so a missing model costs
plan quality, not planning. A train the search could not route holds
(DO_NOTHING) rather than guessing.
"""
from __future__ import annotations

import os
import weakref
from typing import Dict, Optional, Tuple

from flatland.core.env_observation_builder import (
    DummyObservationBuilder,
    ObservationBuilder,
)
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions

from app.policies.base import Policy
from app.policies.goal_based_policies.infrastructure_graph import (
    build_decision_point_graph,
)
from app.policies.goal_based_policies.schedule import SchedulePlayer

# How long the search thinks before the first plan is handed over, and how
# long a mid-episode re-plan gets. The search is anytime, so these are
# "how long to think", not a bound on what it may ever explore.
PLANNING_BUDGET = int(os.environ.get("GOAL_DIRECTED_BUDGET", "600"))

# Process-wide default dials; a session's own dials (set via the
# `/session/{id}/director/weights` endpoint) override them per env.
# Plain floats so importing this module — which the policy registry does
# at app startup — never touches torch.
_WEIGHTS: Tuple[float, float, float] = (1.0, 1.0, 1.0)

_PLAYERS: "weakref.WeakKeyDictionary[RailEnv, SchedulePlayer]" = (
    weakref.WeakKeyDictionary())
_PLAN_INFO: "weakref.WeakKeyDictionary[RailEnv, Dict[str, object]]" = (
    weakref.WeakKeyDictionary())
_ENV_WEIGHTS: "weakref.WeakKeyDictionary[RailEnv, Tuple[float, float, float]]" = (
    weakref.WeakKeyDictionary())
_SCHEDULES: "weakref.WeakKeyDictionary[RailEnv, list]" = (
    weakref.WeakKeyDictionary())
# Per-env re-planning state: which malfunctions were
# already reacted to, when the next reaction is allowed, and whether a
# mid-episode weight change is waiting to be applied.
_REPLAN_STATE: "weakref.WeakKeyDictionary[RailEnv, Dict[str, object]]" = (
    weakref.WeakKeyDictionary())
# The scenario (graph, timetable, distances) each env was planned against,
# so a re-plan reuses it instead of rebuilding the tables every time.
_SCENARIOS: "weakref.WeakKeyDictionary[RailEnv, object]" = (
    weakref.WeakKeyDictionary())

# Steps to sit out after a re-plan before reacting to the next
# malfunction — the fresh plan captured the world as-is, and planning
# costs seconds. Weight changes bypass the cooldown: the user asked.
REPLAN_COOLDOWN = 10


def _validated(
    punctuality: float, connections: float, stability: float
) -> Tuple[float, float, float]:
    if min(punctuality, connections, stability) < 0:
        raise ValueError("weights must be non-negative")
    if punctuality + connections + stability <= 0:
        raise ValueError("at least one weight must be positive")
    return (float(punctuality), float(connections), float(stability))


def set_director_weights(
    punctuality: float, connections: float, stability: float
) -> None:
    """Set the process default for envs planned from now on;
    already-planned envs keep their plan."""
    global _WEIGHTS
    _WEIGHTS = _validated(punctuality, connections, stability)


def director_weights() -> Tuple[float, float, float]:
    return _WEIGHTS


def set_env_weights(
    env: RailEnv, punctuality: float, connections: float, stability: float
) -> None:
    """This env's own dials — the point of moving a slider mid-session.

    Before the episode has stepped, the cached plan is simply dropped and
    the next action request plans afresh under the new weights. Once
    trains are on the map a from-scratch plan would start them at their
    origins again — so a running episode instead marks the weights dirty
    and the next action request re-plans *from the current state*
    (`replan_now`), keeping every train where it actually is.
    """
    _ENV_WEIGHTS[env] = _validated(punctuality, connections, stability)
    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    if env not in _PLAYERS or elapsed == 0:
        _PLAYERS.pop(env, None)
        _PLAN_INFO.pop(env, None)
        _SCHEDULES.pop(env, None)
        return
    _replan_state(env)["weights_dirty"] = True


def env_weights(env: RailEnv) -> Tuple[float, float, float]:
    return _ENV_WEIGHTS.get(env, _WEIGHTS)


def plan_info(env: RailEnv) -> Optional[Dict[str, object]]:
    """Provenance of the plan driving `env`, for the HMI: source, weighted
    score, per-axis utilities, weights in force, decision trace. None
    before planning."""
    return _PLAN_INFO.get(env)


def plan_schedules(env: RailEnv):
    """The full schedules the plan committed — what verification replays.
    (The player's own copy is consumed as it drives.) None before
    planning or when the env was unroutable."""
    return _SCHEDULES.get(env)


def plan_player(env: RailEnv) -> Optional[SchedulePlayer]:
    """The live player driving this env's plan — the what-if endpoint
    copies its progress onto a forked env. None before planning."""
    return _PLAYERS.get(env)


def plan_paths(env: RailEnv) -> Optional[Dict[int, list]]:
    """The committed plan as drawable per-train cell paths: for each
    handle, `{step, row, col}` points in driving order — only what is
    still *ahead*, read from the live player's own progress
    (`SchedulePlayer.future_path`), so the chain starts at the train's
    actual position and stays contiguous on the rails however delayed
    the episode runs. A train that is done or off its plan gets an
    empty path. None before planning."""
    schedules = _SCHEDULES.get(env)
    player = _PLAYERS.get(env)
    if schedules is None or player is None:
        return None
    return {
        int(schedule.handle): player.future_path(schedule.handle)
        for schedule in schedules
    }


def _replan_state(env: RailEnv) -> Dict[str, object]:
    state = _REPLAN_STATE.get(env)
    if state is None:
        state = {
            "last_step": -1,
            "known": set(),
            "cooldown_until": 0,
            "weights_dirty": False,
            "job": None,  # in-flight background re-plan, at most one
        }
        _REPLAN_STATE[env] = state
    return state


def replan_now(
    env: RailEnv, reason: str = "manual", gate: bool = True
) -> Optional[Dict[str, object]]:
    """Re-plan the episode's remainder from the current state and splice
    the result into the live player.

    With `gate` (the default for recovery re-plans), a "research" result
    is committed only when a paired forward simulation on forks confirms
    it actually beats continuing — the models over-choose "research"
    (see `replan.rollout_gate`), so recovery is judged on simulated
    outcomes, not scores. Weight changes pass `gate=False`:
    the user changed the objective, and trading delay away may be
    exactly what the new dials ask for.

    Returns the re-plan event recorded in the plan info, or None when
    there is nothing to re-plan (no committed plan, no models) or the
    residual planner failed — in which case the current plan keeps
    driving: degraded, never broken.
    """
    player = _PLAYERS.get(env)
    schedules = _SCHEDULES.get(env)
    if player is None or schedules is None:
        return None
    try:
        from app.policies.goal_based_policies.replan import residual_plan
        from app.policies.tree_search.director import DirectorWeights

        plan = residual_plan(
            env, player.graph, DirectorWeights(*env_weights(env)),
            player=player, schedules=schedules, reason=reason,
            scenario=_SCENARIOS.get(env),
        )
    except Exception:
        return None
    # A synchronous result supersedes any in-flight background job.
    _replan_state(env)["job"] = None
    return _finish_replan(env, plan, gate=gate)


def _finish_replan(
    env: RailEnv, plan, gate: bool
) -> Optional[Dict[str, object]]:
    """Apply a computed residual plan to the live player, **re-anchored
    to a fresh capture** — the trains kept driving the current plan
    while the search ran (background job, or step requests racing an
    endpoint), so the plan's own tails may describe positions the trains
    have already left. Applying those blindly strands trains off-plan
    (they hold forever); this was the frozen-trains bug.

    Per train: if its freshly captured pinned prefix is still a prefix
    of the new schedule's route (it kept driving the shared part), it
    joins the new plan with fresh wait bookkeeping; if it already drove
    past a point where the new plan chose differently, it keeps its
    current plan. The rollout gate — when it applies — judges the
    re-anchored splice at application time, on the world as it is now.
    """
    player = _PLAYERS.get(env)
    old = _SCHEDULES.get(env)
    if player is None or old is None:
        return None
    try:
        from dataclasses import replace

        from app.policies.goal_based_policies.replan import (
            capture_progress,
            rollout_gate,
            splice_entries,
        )
        from app.policies.goal_based_policies.schedule import TrainSchedule

        now = int(getattr(env, "_elapsed_steps", 0) or 0)
        event = plan.event()
        event["step"] = now  # application time, not compute time
        committed = plan.source == "research"

        tails: Dict[int, list] = {}
        chosen = list(old)
        if committed:
            fresh = capture_progress(env, player.graph, player, old, now=now)
            new_by = {s.handle: s for s in plan.schedules}
            old_by = {s.handle: s for s in old}
            chosen = []
            for handle in sorted(old_by):
                tail = None
                if handle in fresh and handle in new_by:
                    tail = splice_entries(fresh[handle], new_by[handle])
                if tail is not None:
                    tails[handle] = tail
                    chosen.append(new_by[handle])
                else:
                    chosen.append(old_by[handle])
            event["changed"] = sorted(tails)
            if not tails:
                committed = False  # everyone diverged — nothing to join
        if committed and gate:
            verdict = rollout_gate(env, player, replace(plan, tails=tails))
            committed = verdict["commit"]
            event["gate"] = "rollout-pass" if committed else "rollout-veto"
        if committed:
            for handle, tail in tails.items():
                player.set_schedule(TrainSchedule(handle=handle, entries=tail))
    except Exception:
        return None

    # Whatever triggered this, the plan now reflects the current weights —
    # a pending weights-dirty flag is satisfied, not still owed.
    _replan_state(env)["weights_dirty"] = False
    info = _PLAN_INFO.get(env) or {}
    info.setdefault("replans", []).append(event)
    info["weights"] = list(env_weights(env))
    if committed:
        # The committed plan changed: its provenance, score and trace
        # change too. A "continue" (or vetoed) verdict keeps the original
        # plan driving and only records the event.
        _SCHEDULES[env] = chosen
        info["source"] = "replan-research"
        info["weighted"] = plan.weighted
        info["utilities"] = dict(plan.utilities)
        info["decisions"] = plan.decisions
        if plan.trace:
            info["trace"] = plan.trace
    else:
        event["source"] = "continue"
    _PLAN_INFO[env] = info
    return event


def _start_replan_job(env: RailEnv, reason: str, gate: bool) -> None:
    """Kick off a background re-plan: capture the state *now* (atomic
    with the step loop), then search on a thread while the current plan
    keeps driving. The search reads only immutable env facts (rail,
    timetable, the captured progress), so the live env may step freely
    meanwhile; `_maybe_replan` picks the result up and applies it
    re-anchored (`_finish_replan`)."""
    import threading

    player = _PLAYERS.get(env)
    schedules = _SCHEDULES.get(env)
    if player is None or schedules is None:
        return
    try:
        from app.policies.goal_based_policies.replan import capture_progress
        from app.policies.tree_search.director import DirectorWeights

        graph = player.graph
        progress = capture_progress(env, graph, player, schedules)
        weights = DirectorWeights(*env_weights(env))
        scenario = _SCENARIOS.get(env)
    except Exception:
        return

    job: Dict[str, object] = {"gate": gate, "reason": reason, "plan": None}

    def run() -> None:
        try:
            from app.policies.goal_based_policies.replan import residual_plan

            job["plan"] = residual_plan(
                env, graph, weights,
                player=player, schedules=schedules, reason=reason,
                progress=progress, scenario=scenario,
            )
        except Exception:
            job["plan"] = None

    thread = threading.Thread(target=run, daemon=True, name="director-replan")
    job["thread"] = thread
    _replan_state(env)["job"] = job
    thread.start()


def _maybe_replan(env: RailEnv) -> None:
    """Once per env step: react to a fresh malfunction or a pending
    weight change by *starting* a background re-plan — the current plan
    keeps driving while the search runs — and apply a finished job's
    result, re-anchored to the current state."""
    if _PLAYERS.get(env) is None:
        return
    state = _replan_state(env)
    now = int(getattr(env, "_elapsed_steps", 0) or 0)

    job = state.get("job")
    if job is not None:
        if job["thread"].is_alive():
            return  # still computing; the committed plan drives on
        state["job"] = None
        state["cooldown_until"] = now + REPLAN_COOLDOWN
        plan = job.get("plan")
        if plan is not None:
            _finish_replan(env, plan, gate=bool(job["gate"]))
        return

    if state["last_step"] == now and not state["weights_dirty"]:
        return
    state["last_step"] = now

    reason, gate = None, True
    if state["weights_dirty"]:
        state["weights_dirty"] = False
        reason, gate = "weights change", False
    elif now >= state["cooldown_until"]:
        from app.policies.goal_based_policies.replan import new_malfunctions

        fresh = new_malfunctions(env, state["known"], now=now)
        if fresh:
            handle, end = fresh[0]
            reason = f"malfunction on train {handle} until t={end}"
    if reason is None:
        return
    _start_replan_job(env, reason, gate)


def loaded_models() -> Optional[Dict[str, object]]:
    """The value networks driving the search, loaded on first use — what
    the what-if endpoint plans forks with. An empty dict is a working
    configuration (an unguided search), None never happens; the Optional
    is kept for callers that still test for it."""
    from app.policies.tree_search import director

    return director.load_models()


class DirectorPlanReplayPolicy(Policy):
    """Continues a committed Director plan on a *forked* env.

    The rollout baseline for Director-driven sessions: scenario forecasts, recommendation baselines and
    override what-ifs must show the future the committed plan actually
    drives, not a proxy policy's. Model-free — it only replays the live
    player's remaining schedule from the fork's current state — so a
    branch costs milliseconds, unlike a fresh `GoalDirectedPolicy`
    plan."""

    def __init__(self, graph, snapshot):
        self._graph = graph
        self._snapshot = snapshot
        self._player: Optional[SchedulePlayer] = None

    def reset(self, env: RailEnv) -> None:
        player = SchedulePlayer(self._graph, env)
        player.restore(self._snapshot)
        self._player = player

    def act_for_handle(self, handle, observation=None, eps=0.0):
        if self._player is None:
            return RailEnvActions.DO_NOTHING
        return self._player.act(int(handle))

    def build_observation_builder(self) -> ObservationBuilder:
        return DummyObservationBuilder()

    def get_name(self) -> str:
        return "DirectorPlanReplayPolicy"


def director_replay_factory(env: RailEnv):
    """Zero-arg policy factory (the `TrajectoryBranchRunner` contract)
    that continues `env`'s committed Director plan on forked envs.

    Each call snapshots the live player at that moment, so a branch
    forked now replays the plan from exactly the progress the trains
    have now. None when `env` has no committed plan yet — the only case
    a caller may fall back to an ordinary scenario baseline."""
    if _PLAYERS.get(env) is None:
        return None

    def factory() -> DirectorPlanReplayPolicy:
        player = _PLAYERS.get(env)
        if player is None:  # plan vanished since the check — hold safely
            return DirectorPlanReplayPolicy(
                build_decision_point_graph(env), {})
        return DirectorPlanReplayPolicy(player.graph, player.snapshot())

    return factory


class GoalDirectedPolicy(Policy):
    """Search-planned schedules, executed step by step."""

    def __init__(self, env: Optional[RailEnv] = None):
        self._env: Optional[RailEnv] = None
        if env is not None:
            self.reset(env)

    def reset(self, env: RailEnv) -> None:
        self._env = env
        if env in _PLAYERS:
            return
        graph = build_decision_point_graph(env)
        schedules, info = self._plan(env, graph)
        if schedules is None:
            _PLAN_INFO[env] = info
            return
        _PLAYERS[env] = SchedulePlayer(graph, env, schedules)
        _PLAN_INFO[env] = info
        _SCHEDULES[env] = list(schedules)

    def _plan(self, env: RailEnv, graph):
        """Search this environment and hand back executable schedules.

        The search needs no checkpoint to run, so there is no model-free
        branch here any more: a missing network makes the search weaker,
        not absent. Only a genuine failure — an unroutable network, a
        scenario the simulator cannot resolve — leaves the env without a
        plan, and that is reported rather than papered over.
        """
        from app.policies.tree_search import director
        from app.policies.tree_search.scenario import Scenario

        weights = env_weights(env)
        try:
            scenario = Scenario.build(env, graph)
            plan = director.plan(
                env, graph,
                weights=director.DirectorWeights(*weights),
                budget=PLANNING_BUDGET,
                scenario=scenario,
            )
        except Exception:
            return None, {"source": "unroutable", "weights": list(weights)}

        _SCENARIOS[env] = scenario
        info = plan.to_dict()
        info.pop("schedules", None)
        info["weights"] = list(weights)
        return plan.schedules, info

    def act_for_handle(self, handle, observation=None, eps=0.0):
        env = self._env
        if env is None:
            return RailEnvActions.DO_NOTHING
        _maybe_replan(env)
        player = _PLAYERS.get(env)
        if player is None:
            return RailEnvActions.DO_NOTHING
        return player.act(int(handle))

    def build_observation_builder(self) -> ObservationBuilder:
        # The player reads positions straight from the env.
        return DummyObservationBuilder()

    def get_name(self) -> str:
        return "GoalDirectedPolicy"
