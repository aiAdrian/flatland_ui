"""Mid-episode re-planning: capture, splice, residual search,
malfunction detection, forward simulation."""
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.policies.goal_based_policies.infrastructure_graph import (  # noqa: E402
    build_decision_point_graph,
)
from app.policies.goal_based_policies.replan import (  # noqa: E402
    ResidualPlan,
    apply_residual_plan,
    capture_progress,
    new_malfunctions,
    residual_plan,
    rollout_gate,
    simulate_forward,
    splice_entries,
)
from app.policies.goal_based_policies.schedule import (  # noqa: E402
    SchedulePlayer,
    TrainSchedule,
    plan_avoiding_overlaps,
    plan_line,
)
from app.policies.goal_based_policies.visualization import (  # noqa: E402
    build_demo_env,
)
from app.policies.tree_search.metrics import DirectorWeights  # noqa: E402

TRAINS = 4
STEPS_BEFORE_CAPTURE = 12
# Small enough to keep the suite quick; these tests are about capture and
# splicing, not about how deeply the search thinks.
BUDGET = 60


def _build_env():
    return build_demo_env(
        seed=2001, width=30, height=30, number_of_agents=TRAINS,
        max_num_cities=2, line_length=2,
    )


def _running_setup():
    """A fresh env driven a few steps into a committed avoidance plan.

    Deliberately not a searched plan: what these tests exercise is
    capturing a *running* episode and splicing into it, which has to work
    whatever put the trains where they are.
    """
    env = _build_env()
    graph = build_decision_point_graph(env)
    lines = [plan_line(graph, env, handle) for handle in range(len(env.agents))]
    plans = plan_avoiding_overlaps(env, graph, lines)
    player = SchedulePlayer(graph, env, plans)
    handles = [s.handle for s in plans]
    for _ in range(STEPS_BEFORE_CAPTURE):
        env.step(player.act_many(handles))
    return env, graph, plans, player, handles


def test_capture_pins_reality_into_the_schedule_language():
    """Seeds extend the executed prefix, the continue candidate extends
    the seed, and the frontier's nominal departure is never before the
    earliest the train can actually leave."""
    env, graph, plans, player, _ = _running_setup()
    now = env._elapsed_steps
    progress = capture_progress(env, graph, player, plans, now=now)

    assert sorted(progress) == sorted(s.handle for s in plans)
    for schedule in plans:
        p = progress[schedule.handle]
        assert p.status in ("pending", "running", "done", "off_plan")
        assert p.continue_entries[: len(p.seed)] == p.seed
        assert p.pin_wait >= 0 and p.serve_base >= 0
        if p.status == "running":
            # The seed's cells are the plan's cells, in plan order.
            planned = [e.node_id for e in schedule.entries]
            assert [e.node_id for e in p.seed] == planned[: len(p.seed)]
            assert p.tail_anchor in (1, 2)


def test_capture_at_step_zero_reproduces_the_plan():
    """Before anything has happened there is nothing to pin: the continue
    candidate is the committed plan, entry for entry."""
    env = _build_env()
    graph = build_decision_point_graph(env)
    lines = [plan_line(graph, env, handle) for handle in range(len(env.agents))]
    plans = plan_avoiding_overlaps(env, graph, lines)
    player = SchedulePlayer(graph, env, plans)
    progress = capture_progress(env, graph, player, plans, now=0)
    for schedule in plans:
        assert list(progress[schedule.handle].continue_entries) == list(
            schedule.entries
        )


def test_splicing_the_continue_candidate_is_timing_neutral():
    """The strong invariant behind every re-plan: capturing mid-episode
    and splicing the *unchanged* plan back must reproduce the untouched
    episode exactly, per-train arrival steps included."""

    def run(splice: bool):
        env, graph, plans, player, _ = _running_setup()
        if splice:
            progress = capture_progress(env, graph, player, plans)
            for handle, p in sorted(progress.items()):
                tail = splice_entries(
                    p, TrainSchedule(handle=handle,
                                     entries=list(p.continue_entries)),
                )
                if tail is not None:
                    player.set_schedule(
                        TrainSchedule(handle=handle, entries=tail))
        result = simulate_forward(env, player)
        return result["arrivals"], result["total_delay"]

    assert run(False) == run(True)


def test_splice_refuses_a_schedule_that_abandons_the_seed():
    """The search's dead-end fallback can produce an origin-planned
    schedule; splicing it would teleport the plan out from under the
    train, so it must be refused."""
    env, graph, plans, player, _ = _running_setup()
    progress = capture_progress(env, graph, player, plans)
    running = next(
        p for p in progress.values() if p.status == "running"
    )
    other = next(s for s in plans if s.handle != running.handle)
    foreign = TrainSchedule(handle=running.handle, entries=list(other.entries))
    assert splice_entries(running, foreign) is None


def test_residual_plan_extends_seeds_and_the_episode_still_ends():
    """The residual search decides only what is open: every chosen
    schedule extends its captured seed cell-for-cell, the splice keeps
    the player playable, and the verdict is explained.

    Whether the re-plan is *worth* committing is not decided here — the
    search would be marking its own homework — so `considered` carries the
    proposal alone, and `rollout_gate` settles it at application time."""
    env, graph, plans, player, _ = _running_setup()
    plan = residual_plan(
        env, graph, DirectorWeights(), budget=BUDGET,
        player=player, schedules=plans, reason="test",
    )
    assert plan.source in ("research", "continue")
    assert set(plan.considered) == {"research"}
    progress = capture_progress(env, graph, player, plans,
                                now=plan.step)
    by_handle = {s.handle: s for s in plan.schedules}
    for handle, p in progress.items():
        chosen = by_handle[handle].entries
        assert [e.node_id for e in chosen[: len(p.seed)]] == [
            e.node_id for e in p.seed
        ]
    event = plan.event()
    assert event["step"] == plan.step and event["reason"] == "test"

    apply_residual_plan(player, plan)
    result = simulate_forward(env, player)
    assert result["steps"] > plan.step
    # Whatever the search chose, the plan must stay playable:
    # trains keep arriving rather than freezing off-plan.
    assert result["arrived"] > 0


def test_repeated_replans_stay_aligned():
    """A second re-plan captures against the schedules the first one
    committed — those must describe what the player actually drives
    (static trains and dead-end fallbacks keep their entries), or the
    executed/remaining split reads a plan that never ran."""
    env, graph, plans, player, handles = _running_setup()
    first = residual_plan(
        env, graph, DirectorWeights(), budget=BUDGET,
        player=player, schedules=plans, reason="first",
    )
    apply_residual_plan(player, first)
    for _ in range(6):
        env.step(player.act_many(handles))

    second = residual_plan(
        env, graph, DirectorWeights(), budget=BUDGET,
        player=player, schedules=first.schedules, reason="second",
    )
    progress = capture_progress(
        env, graph, player, first.schedules, now=second.step)
    for p in progress.values():
        assert p.continue_entries[: len(p.seed)] == p.seed
    apply_residual_plan(player, second)
    result = simulate_forward(env, player)
    assert result["arrived"] > 0


def test_stale_background_plan_applies_safely_after_the_world_moved():
    """The frozen-trains regression: a plan computed from an old capture
    must never be spliced onto trains that have moved on. Re-anchoring
    against a *fresh* capture lets trains still on the shared route join
    the new plan (fresh wait bookkeeping) and leaves diverged trains on
    their current plan — afterwards no train may be off its plan (the
    player's 'hold rather than guess' would freeze it forever)."""
    env, graph, plans, player, handles = _running_setup()
    progress = capture_progress(env, graph, player, plans)
    plan = residual_plan(
        env, graph, DirectorWeights(), budget=BUDGET,
        player=player, schedules=plans, progress=progress,
    )
    # The world keeps moving while the "background" result is pending.
    for _ in range(10):
        env.step(player.act_many(handles))

    fresh = capture_progress(env, graph, player, plans)
    new_by = {s.handle: s for s in plan.schedules}
    for handle in handles:
        tail = splice_entries(fresh[handle], new_by[handle])
        if tail is not None:
            player.set_schedule(TrainSchedule(handle=handle, entries=tail))

    for handle in handles:
        agent = env.agents[handle]
        if agent.state.name == "DONE" or agent.position is None:
            continue
        assert (
            player.locate(handle) is not None
            or len(player.remaining(handle)) <= 1
        ), f"train {handle} was stranded off its plan"
    result = simulate_forward(env, player)
    assert result["arrived"] > 0


def test_residual_plan_is_deterministic():
    def once():
        env, graph, plans, player, _ = _running_setup()
        plan = residual_plan(
            env, graph, DirectorWeights(), budget=BUDGET,
            player=player, schedules=plans,
        )
        return (
            plan.source,
            [(s.handle, s.to_flat_list()) for s in plan.schedules],
        )

    assert once() == once()


def test_future_paths_are_contiguous_and_start_at_the_train():
    """The map overlay's data contract: a train's future path starts at
    its actual position (or its origin, pre-departure), walks the rails
    cell by adjacent cell to the last planned node, with non-decreasing
    step estimates — a chain that stops mid-track or jumps cells draws
    broken routes."""
    env, graph, plans, player, handles = _running_setup()
    for handle in handles:
        agent = env.agents[handle]
        path = player.future_path(handle)
        if agent.state.name == "DONE":
            assert path == []
            continue
        assert path, f"train {handle} should still have a future"
        for a, b in zip(path, path[1:]):
            assert abs(a["row"] - b["row"]) + abs(a["col"] - b["col"]) == 1
            assert b["step"] >= a["step"]
        if agent.position is not None:
            assert (path[0]["row"], path[0]["col"]) == (
                int(agent.position[0]), int(agent.position[1]))
        terminus = graph.cell_of(player.remaining(handle)[-1].node_id)
        assert (path[-1]["row"], path[-1]["col"]) == (
            int(terminus[0]), int(terminus[1]))


def test_rollout_gate_vetoes_a_switch_without_real_improvement():
    """A "research" plan whose splice reproduces the committed plan can
    never be strictly better — the paired rollout must veto it, and the
    gate must leave the live episode and player untouched."""
    env, graph, plans, player, _ = _running_setup()
    progress = capture_progress(env, graph, player, plans)
    tails = {}
    for handle, p in sorted(progress.items()):
        tail = splice_entries(
            p, TrainSchedule(handle=handle, entries=list(p.continue_entries)))
        if tail is not None:
            tails[handle] = tail
    plan = ResidualPlan(
        schedules=[
            TrainSchedule(handle=h, entries=list(progress[h].continue_entries))
            for h in sorted(progress)
        ],
        tails=tails, source="research", weighted=0.5, utilities={},
        considered={}, decisions=0, step=env._elapsed_steps,
        reason="gate-test",
    )

    before_steps = env._elapsed_steps
    before_snapshot = player.snapshot()
    verdict = rollout_gate(env, player, plan)

    assert verdict["commit"] is False
    assert verdict["keep"]["arrivals"] == verdict["switch"]["arrivals"]
    assert env._elapsed_steps == before_steps
    assert player.snapshot() == before_snapshot


def test_rollout_gate_commits_only_on_strict_simulated_improvement(monkeypatch):
    """The gate's decision rule, case by case: more arrivals commit; equal
    arrivals with strictly less delay commit; a tie — or a worse switch —
    keeps the current plan. Pinned on canned simulation outcomes so an
    inverted comparison cannot slip through while the live-fork veto test
    still passes."""
    from app.policies.goal_based_policies import replan as replan_module

    env, graph, plans, player, _ = _running_setup()
    progress = capture_progress(env, graph, player, plans)
    plan = ResidualPlan(
        schedules=[
            TrainSchedule(handle=h, entries=list(progress[h].continue_entries))
            for h in sorted(progress)
        ],
        tails={}, source="research", weighted=0.5, utilities={},
        considered={}, decisions=0, step=env._elapsed_steps,
        reason="gate-test",
    )

    def gate_with(keep, switch):
        outcomes = [dict(keep), dict(switch)]  # branch order: keep, switch

        def fake_simulate_forward(*args, **kwargs):
            return outcomes.pop(0)

        monkeypatch.setattr(
            replan_module, "simulate_forward", fake_simulate_forward)
        return rollout_gate(env, player, plan)

    base = {"arrived": 3, "total_delay": 100}
    assert gate_with(base, {"arrived": 4, "total_delay": 250})["commit"] is True
    assert gate_with(base, {"arrived": 3, "total_delay": 99})["commit"] is True
    assert gate_with(base, {"arrived": 3, "total_delay": 100})["commit"] is False
    assert gate_with(base, {"arrived": 2, "total_delay": 0})["commit"] is False


def test_new_malfunctions_fire_once_per_outage():
    env, _, _, _, _ = _running_setup()
    agent = next(a for a in env.agents if a.position is not None)
    agent.malfunction_handler._set_malfunction_down_counter(8)
    known: set = set()
    now = env._elapsed_steps

    first = new_malfunctions(env, known, now=now)
    assert first == [(agent.handle, now + 8)]
    # Two steps later the counter has ticked down twice: same end step,
    # same key, already known. (Set the attribute directly — the public
    # setter refuses to touch an ongoing malfunction.)
    agent.malfunction_handler._malfunction_down_counter = 6
    assert new_malfunctions(env, known, now=now + 2) == []
    # Too short to react to.
    other = next(
        a for a in env.agents
        if a.position is not None and a.handle != agent.handle
    )
    other.malfunction_handler._set_malfunction_down_counter(2)
    assert new_malfunctions(env, known, now=now + 2) == []


def test_simulate_forward_reports_absolute_outcomes():
    """Delays are judged against the timetable's absolute deadlines, not
    steps-since-fork."""
    env, graph, plans, player, handles = _running_setup()
    result = simulate_forward(env, player)
    assert result["trains"] == len(handles)
    assert result["steps"] >= STEPS_BEFORE_CAPTURE
    for handle in handles:
        latest = getattr(env.agents[handle], "latest_arrival", None)
        arrival = result["arrivals"][handle]
        if arrival is not None and latest is not None:
            assert result["delays"][handle] == max(0, arrival - int(latest))
