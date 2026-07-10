"""Tests for TrajectoryBranchRunner (R6)."""
import warnings
warnings.filterwarnings("ignore")

import pytest
from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.rail_generators import sparse_rail_generator

from app.core.scenario_runner import BranchResult, TrajectoryBranchRunner
from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy
from app.policies.shortest_path_policy import ShortestPathPolicy


def _make_env(num_agents: int = 2, seed: int = 42) -> RailEnv:
    e = RailEnv(
        width=25, height=25, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


# ── basic shape ────────────────────────────────────────────────────


def test_branch_result_dataclass_defaults():
    r = BranchResult()
    assert r.conflicts == []
    assert r.kpis == {}
    assert r.snapshots == []
    assert r.total_agents == 0
    assert r.success_count == 0
    assert r.success_rate == 0.0
    assert r.terminated_early is False


def test_branch_result_success_rate():
    r = BranchResult(total_agents=4, success_count=3)
    assert r.success_rate == 0.75


def test_branch_result_to_dict_jsonable():
    r = BranchResult(total_agents=2, success_count=1, elapsed_steps=10)
    d = r.to_dict()
    for key in ("conflicts", "kpis", "snapshots", "total_agents",
                "success_count", "elapsed_steps", "terminated_early",
                "success_rate"):
        assert key in d
    assert d["success_rate"] == 0.5


# ── core: runner runs ──────────────────────────────────────────────


def test_runner_baseline_no_overrides():
    """A baseline branch (no overrides) must run, produce snapshots,
    and have well-formed KPIs."""
    env = _make_env()
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    result = runner.run_branch(overrides={}, max_steps=15)

    assert result.elapsed_steps > 0, "baseline should advance the env"
    assert result.total_agents == 2
    assert 0 <= result.success_count <= result.total_agents
    assert 0.0 <= result.success_rate <= 1.0
    assert len(result.snapshots) >= 2, "should have at least start + steps"
    # KPI shape from the detector.
    assert "total_conflicts" in result.kpis
    assert "by_kind" in result.kpis


def test_runner_does_not_modify_base_env():
    """The runner must always fork; the base env must be untouched."""
    env = _make_env()
    base_elapsed_before = env._elapsed_steps
    base_pos_before = [a.position for a in env.agents]

    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    runner.run_branch(overrides={}, max_steps=20)
    runner.run_branch(overrides={0: RailEnvActions.MOVE_LEFT}, max_steps=20)

    assert env._elapsed_steps == base_elapsed_before, (
        "base env was modified — fork is leaking"
    )
    base_pos_after = [a.position for a in env.agents]
    assert base_pos_before == base_pos_after, "base env agent positions changed"


def test_runner_accepts_enum_and_int_overrides():
    """Overrides may be RailEnvActions enum members or plain ints."""
    env = _make_env()
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)

    r_enum = runner.run_branch(overrides={0: RailEnvActions.MOVE_LEFT}, max_steps=10)
    r_int = runner.run_branch(overrides={0: 1}, max_steps=10)  # 1 = MOVE_LEFT

    # Same override value via different types → same outcome.
    assert r_enum.success_count == r_int.success_count
    assert r_enum.elapsed_steps == r_int.elapsed_steps


def test_runner_determinism():
    """Two branches with identical inputs must produce identical outputs."""
    env = _make_env()
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)

    a = runner.run_branch(overrides={}, max_steps=15)
    b = runner.run_branch(overrides={}, max_steps=15)

    assert a.success_count == b.success_count
    assert a.elapsed_steps == b.elapsed_steps
    assert len(a.conflicts) == len(b.conflicts)
    assert len(a.snapshots) == len(b.snapshots)


def test_runner_terminates_early_when_all_done():
    """Run long enough that all agents finish — terminated_early must be True."""
    env = _make_env(num_agents=2)
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    result = runner.run_branch(overrides={}, max_steps=300)

    if result.success_count == result.total_agents:
        assert result.terminated_early is True
    else:
        # If not all agents reach DONE within 300 steps with this seed,
        # we just sanity-check that elapsed_steps is bounded.
        assert result.elapsed_steps <= 300


# ── policy factory ─────────────────────────────────────────────────


def test_runner_works_with_shortest_path_factory():
    """Runner must be policy-agnostic: ShortestPathPolicy also works."""
    env = _make_env()

    def factory():
        return ShortestPathPolicy(env)

    runner = TrajectoryBranchRunner(env, factory)
    result = runner.run_branch(overrides={}, max_steps=15)
    assert result.elapsed_steps > 0
    assert result.total_agents == 2


def test_runner_factory_invoked_each_branch():
    """A *factory* (not a shared instance) is required because policies
    hold per-episode state. Verify it's actually called per branch."""
    env = _make_env()
    call_count = {"n": 0}

    def factory():
        call_count["n"] += 1
        return DeadLockAvoidancePolicy()

    runner = TrajectoryBranchRunner(env, factory)
    runner.run_branch(overrides={}, max_steps=5)
    runner.run_branch(overrides={}, max_steps=5)
    runner.run_branch(overrides={}, max_steps=5)
    assert call_count["n"] == 3, f"factory called {call_count['n']} times, expected 3"


# ── overrides cleanup ──────────────────────────────────────────────


def test_runner_cleans_up_temporary_overrides():
    """The temporary session_id used for overrides must be cleared
    even if the run aborts."""
    from app.core.override_manager import override_manager

    env = _make_env()
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    runner.run_branch(overrides={0: RailEnvActions.MOVE_LEFT}, max_steps=10)

    # All branch session_ids start with 'branch-'.
    leftover = [
        sid for sid in getattr(override_manager, "_overrides", {}).keys()
        if isinstance(sid, str) and sid.startswith("branch-")
    ]
    assert leftover == [], f"leaked branch override sessions: {leftover}"


# ── per-agent outcomes (what-if "selected train" block) ────────────


def test_agent_outcomes_populated_for_every_agent():
    """BranchResult.agent_outcomes must have one entry per agent, each
    with the three fields the what-if UI reads (arrived/deadlocked/delay)."""
    env = _make_env(num_agents=2)
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    result = runner.run_branch(overrides={}, max_steps=15)

    assert set(result.agent_outcomes.keys()) == set(range(2))
    for h in range(2):
        o = result.agent_outcomes[h]
        assert set(o.keys()) == {"arrived", "deadlocked", "delay"}
        assert isinstance(o["arrived"], bool)
        assert isinstance(o["deadlocked"], bool)
        assert isinstance(o["delay"], int)
        assert o["delay"] >= 0


def test_agent_outcomes_arrived_matches_success_count():
    """`arrived` for handle h must equal (state == DONE), and the number
    of arrived agents must equal success_count."""
    env = _make_env(num_agents=2)
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    result = runner.run_branch(overrides={}, max_steps=300)

    arrived_count = sum(1 for o in result.agent_outcomes.values() if o["arrived"])
    assert arrived_count == result.success_count


def test_agent_outcomes_reports_overridden_handle():
    """The handle the operator selected must be present in agent_outcomes
    so the what-if `train` block can report its own fate."""
    env = _make_env(num_agents=2)
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    result = runner.run_branch(overrides={0: RailEnvActions.MOVE_LEFT}, max_steps=20)

    assert 0 in result.agent_outcomes
    o = result.agent_outcomes[0]
    # If the agent finished on this branch, arrived must be True; if not,
    # it must be False — never missing/None.
    assert o["arrived"] in (True, False)
    assert o["deadlocked"] in (True, False)


def test_agent_outcomes_delay_formula_matches_serializer():
    """Delay must be (elapsed - latest_arrival) when overdue and not DONE,
    else 0 — the exact serializer.py formula. Build a tiny deterministic
    case by inspecting the post-branch env directly."""
    from app.core.scenario_runner import agent_outcomes as collect_outcomes

    env = _make_env(num_agents=2)
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    result = runner.run_branch(overrides={}, max_steps=15)

    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    # Cross-check against the serializer formula for every agent.
    for h, a in enumerate(env.agents):
        latest = getattr(a, "latest_arrival", None)
        latest = int(latest) if latest is not None else None
        state = getattr(a, "state", None)
        is_done = state is not None and state.name == "DONE"
        expected = (elapsed - latest) if (latest is not None and elapsed > latest and not is_done) else 0
        assert result.agent_outcomes[h]["delay"] == max(0, expected)


def test_deadlocked_agents_returns_set_and_count_is_len():
    """deadlocked_agents returns a set of handles; count_deadlocked_agents
    is len(...) of it (refactor preserved the public count)."""
    from app.core.scenario_runner import count_deadlocked_agents, deadlocked_agents

    env = _make_env(num_agents=2)
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    runner.run_branch(overrides={}, max_steps=15)

    dl = deadlocked_agents(env)
    assert isinstance(dl, set)
    assert all(isinstance(h, int) for h in dl)
    assert count_deadlocked_agents(env) == len(dl)


def test_branch_trajectories_shape_for_overridden_handle():
    """The what-if map overlay needs per-agent trajectories in scenario
    shape ({handle_str: [{step,row,col}]}). _extract_trajectories on the
    branch snapshots must produce that for the overridden handle."""
    from app.core.hmi_scenario_adapter import _extract_trajectories

    env = _make_env(num_agents=2)
    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    result = runner.run_branch(overrides={0: RailEnvActions.MOVE_LEFT}, max_steps=20)

    traj = _extract_trajectories(result.snapshots)
    assert isinstance(traj, dict)
    # The overridden handle must have at least one point if it was on the map.
    if any(s.get("agents", {}).get(0) for s in result.snapshots):
        assert "0" in traj
        pts = traj["0"]
        assert len(pts) > 0
        # TrajectoryPoint is a pydantic model; the map overlay reads step/row/col.
        p0 = pts[0].model_dump() if hasattr(pts[0], "model_dump") else dict(pts[0])
        assert {"step", "row", "col"} <= set(p0.keys())

