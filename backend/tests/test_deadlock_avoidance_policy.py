"""Tests for DeadLockAvoidancePolicy (R3)."""
import warnings
warnings.filterwarnings("ignore")

import pytest
from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.rail_generators import sparse_rail_generator

from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy
from app.policies.override_policy import OverridePolicy
from app.utils.agent_compat import agent_position


def _make_env(num_agents: int = 2, seed: int = 42, width: int = 25, height: int = 25) -> RailEnv:
    e = RailEnv(
        width=width, height=height, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


def _is_done(env) -> bool:
    """True if the env has terminated (all agents DONE)."""
    return getattr(env, "dones", {}).get("__all__", False) or all(
        getattr(a, "state", None).name == "DONE" for a in env.agents
    )


# ── basic shape / lifecycle ────────────────────────────────────────


def test_dla_constructs():
    p = DeadLockAvoidancePolicy()
    assert p.get_name() == "DeadLockAvoidancePolicy"


def test_dla_observation_builder():
    """DLA ships with FullEnvObservation as its bundled obs builder."""
    from app.observations.full_env_observation import FullEnvObservation
    p = DeadLockAvoidancePolicy()
    builder = p.build_observation_builder()
    assert isinstance(builder, FullEnvObservation)


def test_dla_lifecycle_and_act_many():
    """reset → start_step → act_many should produce one action per handle."""
    env = _make_env()
    p = DeadLockAvoidancePolicy()
    p.reset(env)
    p.start_step()
    handles = env.get_agent_handles()
    actions = p.act_many(handles, [env for _ in handles])
    assert isinstance(actions, dict)
    assert set(actions.keys()) == set(handles)
    for a in actions.values():
        assert isinstance(a, RailEnvActions)


# ── single-agent: behaves like shortest path ────────────────────────


def test_dla_single_agent_progresses():
    """With a single agent, DLA must let it move (no oncoming traffic)."""
    env = _make_env(num_agents=1)
    p = DeadLockAvoidancePolicy()
    p.reset(env)

    # Drive a few env steps under DLA control; the agent must reach the map
    # and make at least one move (i.e. position changes over time).
    initial_position = agent_position(env.agents[0])  # likely None at t=0
    saw_move = False
    for _ in range(60):
        p.start_step()
        actions = p.act_many(env.get_agent_handles(), [env])
        env.step(actions)
        p.end_step()
        pos = agent_position(env.agents[0])
        if pos is not None and pos != initial_position:
            saw_move = True
            break
    assert saw_move, "single-agent DLA never moved the agent"


# ── multi-agent: DLA must produce a valid action per agent each step ──


def test_dla_multi_agent_runs_episode():
    """DLA controls a 3-agent env for several steps without crashing."""
    env = _make_env(num_agents=3, seed=7)
    p = DeadLockAvoidancePolicy()
    p.reset(env)

    for _ in range(40):
        if _is_done(env):
            break
        p.start_step()
        actions = p.act_many(env.get_agent_handles(), [env for _ in env.get_agent_handles()])
        # Every action must be a RailEnvActions value.
        for h, a in actions.items():
            assert isinstance(a, RailEnvActions), f"bad action for handle {h}: {a!r}"
        env.step(actions)
        p.end_step()


def test_dla_stops_at_least_once_in_dense_setup():
    """Sanity: in a dense setup, DLA should issue STOP_MOVING for at
    least one agent at some step (otherwise the heuristic would never
    avoid anything). Very mild assertion to avoid seed-flakiness."""
    env = _make_env(num_agents=4, seed=11, width=30, height=30)
    p = DeadLockAvoidancePolicy()
    p.reset(env)

    saw_stop = False
    for _ in range(80):
        if _is_done(env):
            break
        p.start_step()
        actions = p.act_many(env.get_agent_handles(), [env for _ in env.get_agent_handles()])
        if any(a == RailEnvActions.STOP_MOVING for a in actions.values()):
            saw_stop = True
        env.step(actions)
        p.end_step()
    # If this fails consistently we'd want to revisit the heuristic, but
    # with 4 agents on a small map at least one STOP is expected.
    assert saw_stop, "DLA never issued STOP_MOVING in a dense scenario"


# ── OverridePolicy wraps DLA cleanly ─────────────────────────────────


def test_override_wraps_dla():
    """OverridePolicy must forward lifecycle hooks to DLA and use its
    actions when no override is set."""
    env = _make_env(num_agents=2)
    inner = DeadLockAvoidancePolicy()
    inner.reset(env)
    op = OverridePolicy(inner, session_id="test-r3")
    op.reset(env)
    op.start_step()
    handles = env.get_agent_handles()
    actions = op.act_many(handles, [env for _ in handles])
    assert set(actions.keys()) == set(handles)
    for a in actions.values():
        assert isinstance(a, RailEnvActions)
