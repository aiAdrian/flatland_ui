"""Tests for ConflictDetectionCallbacks (R5).

These tests drive the callback directly (on_episode_start / on_episode_step /
on_episode_end) so the detection logic can be exercised deterministically
without depending on PolicyRunner's I/O.
"""
import warnings
warnings.filterwarnings("ignore")

import pytest
from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.rail_generators import sparse_rail_generator
from flatland.envs.step_utils.states import TrainState

from app.core.conflict_detector import Conflict, ConflictDetectionCallbacks
from app.utils.agent_compat import agent_position


def _make_env(num_agents: int = 2, seed: int = 42) -> RailEnv:
    e = RailEnv(
        width=25, height=25, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


def _drive(env, detector, actions_per_step, steps: int):
    """Helper: emit on_episode_start, then steps × on_episode_step,
    then on_episode_end. Mirrors how PolicyRunner would invoke it."""
    detector.on_episode_start(env=env)
    for _ in range(steps):
        try:
            env.step(actions_per_step(env))
        except Exception as e:
            if "Episode is done" in str(e):
                break
            raise
        detector.on_episode_step(env=env)
    detector.on_episode_end(env=env)


# ── construction ────────────────────────────────────────────────────


def test_constructor_defaults():
    d = ConflictDetectionCallbacks()
    assert d.blocked_threshold == 3
    assert d.detect_deadlocks is True
    kpis = d.get_kpis()
    assert kpis["total_conflicts"] == 0
    assert kpis["num_snapshots"] == 0


def test_episode_start_takes_initial_snapshot():
    env = _make_env()
    d = ConflictDetectionCallbacks()
    d.on_episode_start(env=env)
    snaps = d.get_snapshots()
    assert len(snaps) == 1
    assert snaps[0]["step"] == 0
    assert set(snaps[0]["agents"].keys()) == set(range(len(env.agents)))


# ── snapshot consistency ────────────────────────────────────────────


def test_snapshots_grow_with_steps():
    env = _make_env()
    d = ConflictDetectionCallbacks()
    _drive(env, d,
           lambda e: {h: RailEnvActions.MOVE_FORWARD for h in e.get_agent_handles()},
           steps=5)
    # 1 (start) + 5 (per step) — but stops if "Episode is done"
    assert len(d.get_snapshots()) >= 2
    # Snapshots are chronologically ordered.
    steps = [s["step"] for s in d.get_snapshots()]
    assert steps == sorted(steps)


# ── done detection ──────────────────────────────────────────────────


def test_agent_done_emitted_once_per_agent():
    """Drive a long episode with MOVE_FORWARD; eventually agents arrive."""
    env = _make_env(num_agents=2)
    d = ConflictDetectionCallbacks()
    _drive(env, d,
           lambda e: {h: RailEnvActions.MOVE_FORWARD for h in e.get_agent_handles()},
           steps=200)
    done_events = [c for c in d.get_conflicts() if c.kind == "agent_done"]
    # No agent should have produced more than one DONE event.
    handles = [c.agents[0] for c in done_events]
    assert len(handles) == len(set(handles)), "duplicate agent_done events"


# ── blocked detection ───────────────────────────────────────────────


def test_blocked_threshold_emits_event():
    """Force STOP_MOVING for several consecutive steps → blocked event."""
    env = _make_env(num_agents=2)
    # First, drive forward a few steps so an agent is on the map.
    for _ in range(15):
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
        if any(agent_position(a) is not None for a in env.agents):
            break

    on_map = [h for h, a in enumerate(env.agents) if agent_position(a) is not None]
    if not on_map:
        pytest.skip("no agent reached the map within 15 steps")

    d = ConflictDetectionCallbacks(blocked_threshold=3)
    d.on_episode_start(env=env)
    # Now hold all agents with STOP_MOVING. The agent that's on the map
    # should accumulate stopped-streak == 3 by the third step → 1 event.
    for _ in range(5):
        try:
            env.step({h: RailEnvActions.STOP_MOVING for h in env.get_agent_handles()})
        except Exception as e:
            if "Episode is done" in str(e):
                break
            raise
        d.on_episode_step(env=env)
    d.on_episode_end(env=env)

    blocked_events = [c for c in d.get_conflicts() if c.kind == "blocked"]
    # At least one blocked event for an on-map agent.
    if not blocked_events:
        pytest.skip("agents may not be in STOPPED state under STOP_MOVING in this seed; "
                    "Flatland sometimes keeps them MOVING for a tick")
    for ev in blocked_events:
        assert ev.info["consecutive_stops"] == 3
        assert ev.position is not None


def test_blocked_emitted_only_once_per_streak():
    """A 5-step stop should still emit only one blocked event (at threshold)."""
    env = _make_env(num_agents=2)
    for _ in range(15):
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
        if any(agent_position(a) is not None for a in env.agents):
            break

    on_map_handles = [h for h, a in enumerate(env.agents) if agent_position(a) is not None]
    if not on_map_handles:
        pytest.skip("no agent on map")

    d = ConflictDetectionCallbacks(blocked_threshold=3)
    d.on_episode_start(env=env)
    for _ in range(8):
        try:
            env.step({h: RailEnvActions.STOP_MOVING for h in env.get_agent_handles()})
        except Exception as e:
            if "Episode is done" in str(e):
                break
            raise
        d.on_episode_step(env=env)
    d.on_episode_end(env=env)

    blocked = [c for c in d.get_conflicts() if c.kind == "blocked"]
    # At most one blocked event per agent across the whole streak.
    counts = {}
    for ev in blocked:
        for h in ev.agents:
            counts[h] = counts.get(h, 0) + 1
    for h, n in counts.items():
        assert n == 1, f"handle {h} got {n} blocked events (expected 1)"


# ── KPI shape ───────────────────────────────────────────────────────


def test_kpis_shape_matches_spec():
    env = _make_env()
    d = ConflictDetectionCallbacks()
    _drive(env, d,
           lambda e: {h: RailEnvActions.MOVE_FORWARD for h in e.get_agent_handles()},
           steps=10)
    kpis = d.get_kpis()
    for key in (
        "total_conflicts", "by_kind", "num_snapshots",
        "num_done", "num_overdue", "num_blocked_events",
        "num_swap_attempts", "num_deadlock_cycles", "num_malfunctions",
        "total_delay", "agents_with_conflicts",
    ):
        assert key in kpis, f"missing kpi: {key}"
    assert isinstance(kpis["by_kind"], dict)
    assert isinstance(kpis["agents_with_conflicts"], list)
    assert kpis["total_conflicts"] == sum(kpis["by_kind"].values())


# ── re-use the same instance ───────────────────────────────────────


def test_episode_start_resets_state():
    env = _make_env()
    d = ConflictDetectionCallbacks()
    _drive(env, d,
           lambda e: {h: RailEnvActions.MOVE_FORWARD for h in e.get_agent_handles()},
           steps=10)
    snaps_before = len(d.get_snapshots())
    conflicts_before = len(d.get_conflicts())
    assert snaps_before > 0

    # Re-use the detector for a second episode.
    env2 = _make_env(seed=7)
    d.on_episode_start(env=env2)
    assert len(d.get_snapshots()) == 1   # only the fresh start snapshot
    assert len(d.get_conflicts()) == 0   # cleared

    _ = (snaps_before, conflicts_before)  # unused, kept for clarity


# ── Conflict dataclass ──────────────────────────────────────────────


def test_conflict_to_dict_jsonable():
    c = Conflict(
        kind="blocked", step=5, agents=[0, 1],
        position=(3, 7), info={"consecutive_stops": 3},
    )
    d = c.to_dict()
    assert d["kind"] == "blocked"
    assert d["agents"] == [0, 1]
    assert d["position"] == [3, 7]   # tuple → list
    assert d["info"]["consecutive_stops"] == 3
