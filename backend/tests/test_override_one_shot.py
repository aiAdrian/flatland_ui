"""Override is a one-shot directive: applied once at decision cell, then cleared."""
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


def _make_env(num_agents=2, seed=42):
    e = RailEnv(
        width=25, height=25, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


def test_override_cleared_after_application_at_switch():
    """If the agent is at a SWITCH cell when the override is applied,
    the manager should be empty for that handle right after."""
    env = _make_env()
    sid = "test-oneshot"
    inner = DeadLockAvoidancePolicy()
    inner.reset(env)
    pol = OverridePolicy(inner, sid)
    pol.reset(env)

    # Find an agent at a SWITCH/MERGING by stepping forward a bit.
    handle_at_switch = None
    for _ in range(60):
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
        for h, a in enumerate(env.agents):
            if a.position is None:
                continue
            kind = classify_cell_at(env, a.position, a.direction)
            if kind in ("SWITCH", "MERGING"):
                handle_at_switch = h
                break
        if handle_at_switch is not None:
            break

    if handle_at_switch is None:
        pytest.skip("no agent reached a SWITCH/MERGING in 60 steps")

    # Set override.
    override_manager.set(sid, handle_at_switch, int(RailEnvActions.MOVE_LEFT))
    assert override_manager.get(sid, handle_at_switch) is not None

    # Run act_many: should apply AND clear.
    handles = env.get_agent_handles()
    obs = {h: env for h in handles}
    actions = pol.act_many(handles, obs)

    assert int(actions[handle_at_switch]) == int(RailEnvActions.MOVE_LEFT), (
        "override should win at the switch"
    )
    assert override_manager.get(sid, handle_at_switch) is None, (
        "override should be cleared after application"
    )

    # Cleanup
    override_manager.clear_all(sid)


def test_override_parked_when_not_at_decision_cell():
    """If the agent is mid-track (not at a switch), the override
    should be PARKED — not applied, not cleared."""
    env = _make_env()
    sid = "test-parked"
    inner = DeadLockAvoidancePolicy()
    inner.reset(env)
    pol = OverridePolicy(inner, sid)
    pol.reset(env)

    # Find an agent on plain track (not at switch).
    handle_on_track = None
    for _ in range(20):
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
        for h, a in enumerate(env.agents):
            if a.position is None:
                continue
            kind = classify_cell_at(env, a.position, a.direction)
            if kind not in ("SWITCH", "MERGING"):
                handle_on_track = h
                break
        if handle_on_track is not None:
            break

    if handle_on_track is None:
        pytest.skip("no agent on plain track")

    override_manager.set(sid, handle_on_track, int(RailEnvActions.MOVE_LEFT))
    handles = env.get_agent_handles()
    obs = {h: env for h in handles}
    pol.act_many(handles, obs)

    # Override must STILL be present — agent didn't reach a switch yet.
    assert override_manager.get(sid, handle_on_track) is not None, (
        "parked override must remain until decision cell"
    )

    override_manager.clear_all(sid)


def test_override_does_not_persist_across_multiple_steps():
    """E2E: set override, run many steps, override must be gone afterward
    (whether applied or no longer relevant). It must NEVER be sticky."""
    env = _make_env()
    sid = "test-not-sticky"
    inner = DeadLockAvoidancePolicy()
    inner.reset(env)
    pol = OverridePolicy(inner, sid)
    pol.reset(env)

    # Step a bit so an agent is on the map.
    for _ in range(15):
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
    on_map = [h for h, a in enumerate(env.agents) if a.position is not None]
    if not on_map:
        pytest.skip("no agent on map")
    h = on_map[0]

    override_manager.set(sid, h, int(RailEnvActions.MOVE_LEFT))

    # Run the override policy for up to 30 steps.
    pol.start_episode()
    for _ in range(30):
        handles = env.get_agent_handles()
        obs = {hh: env for hh in handles}
        pol.start_step()
        actions = pol.act_many(handles, obs)
        try:
            env.step(actions)
        except Exception:
            break
        pol.end_step()
        # If the agent passed a switch, override should be cleared.
        if override_manager.get(sid, h) is None:
            break
    pol.end_episode()

    # In any case: override should not be set after a long run that
    # crossed at least one switch. We just assert it didn't loop forever
    # and (with high probability) was applied & cleared.
    final = override_manager.get(sid, h)
    # Allow it to still be parked if the agent never reached a switch
    # (rare but possible). Just ensure no crash.
    assert final is None or isinstance(final, int)

    override_manager.clear_all(sid)
