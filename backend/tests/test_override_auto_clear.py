"""Tests for override auto-clear after decision-point consumption.

Spec
----
A user-set override is the operator's decision for the agent's NEXT
decision point. As soon as the agent is at that decision cell and
the override is applied, the override is consumed and cleared.
The next step reverts to the default policy.
"""
import warnings
warnings.filterwarnings("ignore")

import pytest
from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.rail_generators import sparse_rail_generator

from app.core.cell_classifier import classify_cell_at
from app.core.override_manager import override_manager
from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy
from app.policies.override_policy import OverridePolicy


def _make_env(num_agents: int = 2, seed: int = 42) -> RailEnv:
    e = RailEnv(
        width=25, height=25, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


def _drive_until_at_decision(env, max_steps: int = 30):
    """MOVE_FORWARD until any agent stands on a SWITCH/MERGING cell."""
    for step in range(max_steps):
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
        for h, ag in enumerate(env.agents):
            if ag.position is None:
                continue
            if classify_cell_at(env, ag.position, ag.direction) in ("SWITCH", "MERGING"):
                return h, step + 1
    return None, max_steps


def test_override_cleared_after_decision_consumption():
    sess = "test-autoclear-1"
    override_manager.clear_all(sess)
    env = _make_env()
    handle, _ = _drive_until_at_decision(env)
    if handle is None:
        pytest.skip("no agent reached a decision cell")

    override_manager.set(sess, handle, int(RailEnvActions.MOVE_LEFT))
    policy = OverridePolicy(DeadLockAvoidancePolicy(), sess)
    policy.reset(env)

    handles = env.get_agent_handles()
    obs = {h: env for h in handles}
    actions = policy.act_many(handles, obs)

    assert actions[handle] == RailEnvActions(int(RailEnvActions.MOVE_LEFT))
    assert override_manager.get(sess, handle) is None
    override_manager.clear_all(sess)


def test_override_persists_until_decision_cell_reached():
    sess = "test-autoclear-2"
    override_manager.clear_all(sess)
    env = _make_env()
    handle = 0
    override_manager.set(sess, handle, int(RailEnvActions.MOVE_RIGHT))

    policy = OverridePolicy(DeadLockAvoidancePolicy(), sess)
    policy.reset(env)
    handles = env.get_agent_handles()
    obs = {h: env for h in handles}

    for _ in range(3):
        ag = env.agents[handle]
        at_decision = (ag.position is not None
                       and classify_cell_at(env, ag.position, ag.direction)
                       in ("SWITCH", "MERGING"))
        if at_decision:
            break
        policy.act_many(handles, obs)
        # Not at a switch → override must still be set.
        assert override_manager.get(sess, handle) == int(RailEnvActions.MOVE_RIGHT)
        env.step({h: RailEnvActions.MOVE_FORWARD for h in handles})

    override_manager.clear_all(sess)


def test_override_one_shot_next_step_uses_default():
    sess = "test-autoclear-3"
    override_manager.clear_all(sess)
    env = _make_env()
    handle, _ = _drive_until_at_decision(env)
    if handle is None:
        pytest.skip("no agent reached a decision cell")

    override_manager.set(sess, handle, int(RailEnvActions.MOVE_LEFT))
    policy = OverridePolicy(DeadLockAvoidancePolicy(), sess)
    policy.reset(env)
    handles = env.get_agent_handles()
    obs = {h: env for h in handles}

    a1 = policy.act_many(handles, obs)
    assert a1[handle] == RailEnvActions(int(RailEnvActions.MOVE_LEFT))
    env.step(a1)

    policy.act_many(handles, obs)
    assert override_manager.get(sess, handle) is None
    override_manager.clear_all(sess)


def test_act_for_handle_also_clears():
    sess = "test-autoclear-4"
    override_manager.clear_all(sess)
    env = _make_env()
    handle, _ = _drive_until_at_decision(env)
    if handle is None:
        pytest.skip("no agent reached a decision cell")

    override_manager.set(sess, handle, int(RailEnvActions.MOVE_LEFT))
    policy = OverridePolicy(DeadLockAvoidancePolicy(), sess)
    policy.reset(env)

    a = policy.act_for_handle(handle)
    assert a == RailEnvActions(int(RailEnvActions.MOVE_LEFT))
    assert override_manager.get(sess, handle) is None
    override_manager.clear_all(sess)
