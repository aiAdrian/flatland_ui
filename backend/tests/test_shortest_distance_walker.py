"""Tests for ShortestDistanceWalker (R2)."""
import warnings
warnings.filterwarnings("ignore")

import pytest
from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.rail_generators import sparse_rail_generator

from app.utils.agent_compat import agent_direction, agent_position, agent_target
from app.utils.shortest_distance_walker import ShortestDistanceWalker


def _make_env(num_agents: int = 2, seed: int = 42) -> RailEnv:
    e = RailEnv(
        width=25, height=25, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


@pytest.fixture
def env():
    return _make_env()


def _run_until_on_map(env: RailEnv, handle: int, max_steps: int = 30) -> bool:
    """Step env with MOVE_FORWARD until the given agent has a position
    on the grid. Returns True if the agent made it onto the map."""
    for _ in range(max_steps):
        if agent_position(env.agents[handle]) is not None:
            return True
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
    return agent_position(env.agents[handle]) is not None


def test_walker_constructs_and_resets(env):
    w = ShortestDistanceWalker(env)
    assert w.env is env
    other = _make_env(seed=7)
    w.reset(other)
    assert w.env is other


def test_walk_one_step_off_map_uses_initial_position(env):
    """Before any env.step, agent has no position yet — walker must
    fall back to initial_position and still produce a valid lookahead."""
    w = ShortestDistanceWalker(env)
    handle = 0
    assert agent_position(env.agents[handle]) is None  # off-map at start
    result = w.walk_one_step(handle)
    assert result is not None, "walker should use initial_position when off-map"
    next_pos, next_dir, action, transitions = result
    assert isinstance(next_pos, tuple) and len(next_pos) == 2
    assert next_dir in (0, 1, 2, 3)
    assert isinstance(action, RailEnvActions)
    assert len(transitions) == 4


def test_walk_one_step_on_map(env):
    w = ShortestDistanceWalker(env)
    handle = 0
    assert _run_until_on_map(env, handle), "agent did not enter the map"
    result = w.walk_one_step(handle)
    assert result is not None
    next_pos, next_dir, action, transitions = result
    # Sanity: next_pos should be a neighbor of current position
    cur = agent_position(env.agents[handle])
    dr = abs(next_pos[0] - cur[0])
    dc = abs(next_pos[1] - cur[1])
    assert dr + dc == 1, f"next_pos {next_pos} is not a neighbor of {cur}"


def test_walk_to_target_makes_progress(env):
    """walk_to_target should walk multiple cells; each callback invocation
    must receive a position adjacent to the previous one."""
    handle = 0
    assert _run_until_on_map(env, handle)

    visited = []

    class TracingWalker(ShortestDistanceWalker):
        def callback(self, handle, agent, position, direction, action, possible_transitions):
            visited.append((position, direction))
            return True

    w = TracingWalker(env)
    walked = w.walk_to_target(handle, max_steps=200)
    assert walked == len(visited)
    assert walked > 0, "walker should progress at least one cell"

    # Adjacent cells along the trace.
    prev = agent_position(env.agents[handle])
    for pos, _ in visited:
        dr = abs(pos[0] - prev[0])
        dc = abs(pos[1] - prev[1])
        assert dr + dc == 1, f"non-adjacent step: {prev} -> {pos}"
        prev = pos


def test_walk_to_target_terminates_at_target(env):
    """When walked to the end, the last visited cell must be the agent's
    target (within max_steps budget)."""
    handle = 0
    assert _run_until_on_map(env, handle)

    visited = []

    class TracingWalker(ShortestDistanceWalker):
        def callback(self, handle, agent, position, direction, action, possible_transitions):
            visited.append(position)
            return True

    w = TracingWalker(env)
    target = agent_target(env.agents[handle])
    w.walk_to_target(handle, max_steps=500)

    if visited:
        # Either we reached the target, or we hit max_steps / dead-end.
        # In a sparse rail layout the walker must reach the target.
        assert visited[-1] == target, (
            f"walker did not reach target {target}; last visited {visited[-1]}, "
            f"path length {len(visited)}"
        )


def test_callback_can_abort_walk(env):
    """Returning False from callback must stop walk_to_target immediately."""
    handle = 0
    assert _run_until_on_map(env, handle)

    class StopAfter(ShortestDistanceWalker):
        def __init__(self, env, n):
            super().__init__(env)
            self.n = n
            self.count = 0

        def callback(self, *args, **kwargs):
            self.count += 1
            return self.count < self.n

    w = StopAfter(env, n=3)
    walked = w.walk_to_target(handle, max_steps=500)
    assert walked == 3, f"expected 3 cells walked, got {walked}"


def test_done_agent_yields_no_walk():
    """A DONE agent must produce no walk."""
    from flatland.envs.step_utils.states import TrainState
    e = _make_env()
    handle = 0
    # Fake DONE state to test the guard.
    e.agents[handle]._state = TrainState.DONE  # internal — only for unit test
    # Some flatland versions store state via state machine; fall back to direct attr.
    try:
        e.agents[handle].state = TrainState.DONE
    except Exception:
        pass

    w = ShortestDistanceWalker(e)
    if e.agents[handle].state == TrainState.DONE:
        assert w.walk_one_step(handle) is None
        assert w.walk_to_target(handle) == 0
    else:
        pytest.skip("could not force agent into DONE state in this Flatland build")
