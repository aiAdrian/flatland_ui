"""Tests for the exhaustive action-space event graph (Phase 0)."""
import warnings
warnings.filterwarnings("ignore")

from types import SimpleNamespace

from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_generators import sparse_rail_generator

from app.core.action_event_graph import (
    ExhaustiveActionGraphBuilder,
    GraphLimits,
    hard_deadlocked_agents,
    state_hash,
)


def _make_env(num_agents: int = 2, seed: int = 42) -> RailEnv:
    e = RailEnv(
        width=25, height=25, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


# ── hard_deadlocked_agents (fake env: straight EW track) ────────────

# Transition tuples are (N, E, S, W).
_EAST = (0, 1, 0, 0)
_WEST = (0, 0, 0, 1)


class _FakeRail:
    def __init__(self, trans):
        self._trans = trans

    def get_transitions(self, cfg):
        (pos, direction) = cfg
        return self._trans.get((tuple(pos), int(direction)), (0, 0, 0, 0))


def _fake_env(agents, trans):
    return SimpleNamespace(
        agents=agents, rail=_FakeRail(trans), height=5, width=5)


def _fake_agent(pos, direction):
    return SimpleNamespace(
        position=pos, direction=direction,
        state=SimpleNamespace(name="MOVING"))


def test_hard_deadlock_mutual_pair():
    # a0 at (0,0) heading E, a1 at (0,1) heading W — mutual block.
    env = _fake_env(
        [_fake_agent((0, 0), 1), _fake_agent((0, 1), 3)],
        {((0, 0), 1): _EAST, ((0, 1), 3): _WEST},
    )
    assert hard_deadlocked_agents(env) == {0, 1}


def test_hard_deadlock_ignores_follow_behind():
    # a0 behind a1, both heading E, a1's exit is free — nobody is stuck.
    env = _fake_env(
        [_fake_agent((0, 0), 1), _fake_agent((0, 1), 1)],
        {((0, 0), 1): _EAST, ((0, 1), 1): _EAST},
    )
    assert hard_deadlocked_agents(env) == set()


def test_hard_deadlock_flags_convoy_behind_pair():
    # a2 → a0 →← a1 : a0/a1 are mutual, a2 is stuck behind them.
    env = _fake_env(
        [
            _fake_agent((0, 1), 1),   # a0, E
            _fake_agent((0, 2), 3),   # a1, W
            _fake_agent((0, 0), 1),   # a2, E, behind a0
        ],
        {((0, 1), 1): _EAST, ((0, 2), 3): _WEST, ((0, 0), 1): _EAST},
    )
    assert hard_deadlocked_agents(env) == {0, 1, 2}


# ── builder ─────────────────────────────────────────────────────────


def test_build_graph_shape():
    env = _make_env()
    g = ExhaustiveActionGraphBuilder(
        env, GraphLimits(max_depth=20, max_nodes=100, max_wall_s=60),
    ).build()
    assert g.root_id in g.nodes
    assert g.nodes[g.root_id].event == "root"
    for e in g.edges:
        assert e.from_id in g.nodes
        assert e.to_id in g.nodes
        assert e.steps >= 1
    assert g.stats.nodes == len(g.nodes)
    assert g.stats.edges == len(g.edges)
    # depth budget: no node further than max_depth from the root
    root_step = g.nodes[g.root_id].step
    assert all(n.step - root_step <= 20 for n in g.nodes.values())
    # jsonable
    d = g.to_dict()
    assert set(d) == {"root_id", "nodes", "edges", "stats"}


def test_base_env_not_mutated():
    env = _make_env()
    before = state_hash(env)
    ExhaustiveActionGraphBuilder(
        env, GraphLimits(max_depth=15, max_nodes=50, max_wall_s=60),
    ).build()
    assert state_hash(env) == before
    assert int(getattr(env, "_elapsed_steps", 0) or 0) == 0


def test_deterministic_rebuild():
    g1 = ExhaustiveActionGraphBuilder(
        _make_env(seed=42), GraphLimits(max_depth=15, max_nodes=60, max_wall_s=60),
    ).build()
    g2 = ExhaustiveActionGraphBuilder(
        _make_env(seed=42), GraphLimits(max_depth=15, max_nodes=60, max_wall_s=60),
    ).build()
    assert set(g1.nodes) == set(g2.nodes)
    assert g1.stats.branch_points == g2.stats.branch_points
    assert g1.stats.merges == g2.stats.merges


def test_branching_produces_action_labeled_edges():
    # 3 agents over 40 steps reliably cross switches on this seed.
    env = _make_env(num_agents=3, seed=42)
    g = ExhaustiveActionGraphBuilder(
        env, GraphLimits(max_depth=40, max_nodes=120, max_wall_s=120),
    ).build()
    branch_edges = [e for e in g.edges if e.actions]
    assert g.stats.branch_points > 0
    assert branch_edges, "expected at least one divergence edge"
    for e in branch_edges:
        for h, name in e.actions.items():
            assert name in ("MOVE_LEFT", "MOVE_FORWARD", "MOVE_RIGHT")
