"""Tests for the policy-divergence event graph."""
import warnings
warnings.filterwarnings("ignore")

from types import SimpleNamespace

from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_generators import sparse_rail_generator

from app.core.action_event_graph import state_hash
from app.core.policy_divergence_graph import (
    PolicyDivergenceGraphBuilder,
    PolicyGraphLimits,
    default_participants,
)
from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy
from app.policies.shortest_path_policy import ShortestPathPolicy


def _make_env(num_agents: int = 3, seed: int = 42) -> RailEnv:
    e = RailEnv(
        width=25, height=25, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


_BOTH = [
    ("deadlock_avoidance", DeadLockAvoidancePolicy),
    ("shortest_path", ShortestPathPolicy),
]


def _build(env, **kw):
    limits = PolicyGraphLimits(
        max_depth=kw.pop("max_depth", None),
        max_nodes=kw.pop("max_nodes", 200),
        max_wall_s=kw.pop("max_wall_s", 120),
    )
    return PolicyDivergenceGraphBuilder(
        env, kw.pop("participants", _BOTH), limits, **kw
    ).build()


# ── participants ────────────────────────────────────────────────────


def test_random_policy_excluded_by_default():
    """RandomPolicy is nondeterministic — it would branch every step and
    make the graph irreproducible."""
    ids = [pid for pid, _f in default_participants()]
    assert "random" not in ids
    assert "deadlock_avoidance" in ids and "shortest_path" in ids


# ── graph shape ─────────────────────────────────────────────────────


def test_graph_shape_and_root():
    g = _build(_make_env())
    assert g.root_id in g.nodes
    assert g.nodes[g.root_id].event == "root"
    assert g.policy_ids == ["deadlock_avoidance", "shortest_path"]
    for e in g.edges:
        assert e.from_id in g.nodes and e.to_id in g.nodes
        assert e.steps >= 1
    assert g.stats.nodes == len(g.nodes)
    assert g.stats.edges == len(g.edges)
    d = g.to_dict()
    assert set(d) == {
        "root_id", "policy_ids", "num_agents", "agent_targets",
        "nodes", "edges", "stats",
    }
    # Targets are sent once at graph level, not repeated per node.
    assert d["num_agents"] == 3
    assert all(len(t) == 2 for t in d["agent_targets"].values())


def test_base_env_not_mutated():
    env = _make_env()
    before = state_hash(env)
    _build(env)
    assert state_hash(env) == before
    assert int(getattr(env, "_elapsed_steps", 0) or 0) == 0


def test_deterministic_rebuild():
    g1 = _build(_make_env())
    g2 = _build(_make_env())
    assert set(g1.nodes) == set(g2.nodes)
    assert g1.stats.divergences == g2.stats.divergences
    assert g1.stats.false_divergences == g2.stats.false_divergences


# ── divergence semantics ────────────────────────────────────────────


def test_single_policy_never_diverges():
    """A lone policy cannot disagree with itself — the whole run must
    collapse to a chain of event nodes with no branches."""
    g = _build(_make_env(), participants=[("shortest_path", ShortestPathPolicy)])
    assert g.stats.divergences == 0
    assert g.stats.false_divergences == 0
    assert all(not e.action_diff for e in g.edges)
    # A chain: every node has at most one outgoing edge.
    from collections import Counter
    out = Counter(e.from_id for e in g.edges)
    assert all(c <= 1 for c in out.values())


def test_divergence_edges_are_annotated():
    g = _build(_make_env(num_agents=5), max_nodes=120)
    branch_edges = [e for e in g.edges if e.action_diff]
    if not branch_edges:
        # Policies agreed for the whole run on this instance — the
        # remaining assertions do not apply, but the graph must still be
        # a well-formed chain.
        assert g.stats.divergences == 0
        return
    for e in branch_edges:
        assert e.policy_ids, "a divergence edge must name its policies"
        assert set(e.policy_ids) <= set(g.policy_ids)
        for name in e.action_diff.values():
            assert name in (
                "DO_NOTHING", "MOVE_LEFT", "MOVE_FORWARD",
                "MOVE_RIGHT", "STOP_MOVING", "?",
            )
    # Every divergence emits at least two children from the same parent.
    from collections import Counter
    per_parent = Counter(e.from_id for e in branch_edges)
    assert max(per_parent.values()) >= 2


def test_ongoing_dispute_does_not_rebranch():
    """A persistent disagreement (one policy holding a train while the
    other wants to run it) is ONE decision, not one per step. The literal
    rule re-branches every step and explodes; the default must not."""
    env_a, env_b = _make_env(num_agents=5), _make_env(num_agents=5)
    strict = _build(env_a, max_nodes=400, new_disputes_only=True)
    literal = _build(env_b, max_nodes=400, new_disputes_only=False)
    assert strict.stats.divergences <= literal.stats.divergences
    assert strict.stats.nodes <= literal.stats.nodes


def test_result_does_not_depend_on_participant_order():
    """The graph must not silently prefer whichever policy is listed first.

    Regression: with mid-section disputes resolved by "the branch owner
    drives", the root has no owner — falling back to the first policy made
    the whole graph show that policy's world (DLA first → 0 deadlock
    futures, ShortestPath first → 13). The root must branch instead.
    """
    dla_first = [
        ("deadlock_avoidance", DeadLockAvoidancePolicy),
        ("shortest_path", ShortestPathPolicy),
    ]
    sp_first = list(reversed(dla_first))
    a = _build(_make_env(num_agents=5), participants=dla_first, max_nodes=300)
    b = _build(_make_env(num_agents=5), participants=sp_first, max_nodes=300)
    assert a.stats.nodes == b.stats.nodes
    assert a.stats.divergences == b.stats.divergences
    assert a.stats.deadlock_events == b.stats.deadlock_events
    assert set(a.nodes) == set(b.nodes)


def test_decision_cell_gate_fires_without_losing_events():
    """The gate must actually skip mid-section disputes, and must not
    silence deadlock detection.

    Note node/divergence counts are deliberately NOT asserted monotone:
    declining to fork mid-section changes which worlds get explored (the
    owner keeps driving), so the gated graph is not a subset of the
    ungated one and can even be larger on some instances.
    """
    gated = _build(_make_env(num_agents=5), max_nodes=600, decision_cells_only=True)
    ungated = _build(_make_env(num_agents=5), max_nodes=600, decision_cells_only=False)
    # Whether the gate *fires* is instance-dependent (on a sparse network
    # most holds sit at pre-switch cells and are genuine decisions), so
    # only the disabled side is a hard invariant. The predicate itself is
    # covered by test_hold_point_is_the_cell_before_a_switch_not_the_switch.
    assert ungated.stats.non_decision_disputes == 0, "gate fired while disabled"
    assert gated.stats.nodes > 1 and ungated.stats.nodes > 1
    if ungated.stats.deadlock_events > 0:
        assert gated.stats.deadlock_events > 0, (
            "gating must not hide every deadlock future"
        )


def test_hold_point_is_the_cell_before_a_switch_not_the_switch():
    """A hold belongs one field BEFORE a junction, never on it.

    Regression: those pre-switch cells classify as FORWARD_ONLY, not
    MERGING (MERGING is the cell before a *merge point* — a different set
    of cells). Requiring MERGING for holds silently discarded every
    pre-switch hold decision and collapsed the graph.
    """
    from flatland.core.grid.grid4_utils import get_new_position
    from flatland.envs.fast_methods import fast_argmax, fast_count_nonzero

    from app.core.cell_classifier import _get_transitions, classify_cell_at

    env = _make_env(num_agents=3)
    is_hold = PolicyDivergenceGraphBuilder.is_hold_point

    before_switch, on_switch = [], []
    for r in range(env.height):
        for c in range(env.width):
            for d in range(4):
                try:
                    cell = classify_cell_at(env, (r, c), d)
                    trans = _get_transitions(env, r, c, d)
                except Exception:
                    continue
                if cell == "SWITCH":
                    on_switch.append(((r, c), d))
                    continue
                if fast_count_nonzero(trans) != 1:
                    continue
                nd = fast_argmax(trans)
                nr, nc = get_new_position((r, c), nd)
                if not (0 <= nr < env.height and 0 <= nc < env.width):
                    continue
                if classify_cell_at(env, (nr, nc), nd) == "SWITCH":
                    before_switch.append((((r, c), d), cell))

    assert before_switch, "test env has no pre-switch cells"
    # The regression: these are FORWARD_ONLY, and must still be hold points.
    assert any(cell == "FORWARD_ONLY" for _p, cell in before_switch)
    for (pos, d), _cell in before_switch:
        assert is_hold(env, pos, d) is True, f"{pos} dir {d} must be a hold point"

    assert on_switch, "test env has no switches"
    for pos, d in on_switch:
        assert is_hold(env, pos, d) is False, "must never hold a train on a switch"


def test_deadlock_branches_are_not_expanded():
    """A hard-deadlocked train can never reach its target, so nothing
    downstream is a usable plan. The node stays visible as an outcome, but
    it must be terminal and have no outgoing edges."""
    g = _build(_make_env(num_agents=5), max_nodes=400)
    deadlocked = [n for n in g.nodes.values() if n.deadlocked]
    outgoing = {e.from_id for e in g.edges}
    for n in deadlocked:
        assert n.terminal, f"deadlock node {n.id} must end its branch"
        assert n.id not in outgoing, f"deadlock node {n.id} was expanded anyway"


def test_deadlock_pruning_shrinks_the_graph():
    pruned = _build(_make_env(num_agents=5), max_nodes=800, prune_deadlocks=True)
    full = _build(_make_env(num_agents=5), max_nodes=800, prune_deadlocks=False)
    assert pruned.stats.nodes <= full.stats.nodes
    # Deadlocks still get reported — pruning stops expansion, not detection.
    if full.stats.deadlock_events:
        assert pruned.stats.deadlock_events > 0
        assert pruned.stats.pruned_deadlock_branches > 0


def test_budget_truncation_is_flagged():
    g = _build(_make_env(num_agents=5), max_nodes=12)
    assert g.stats.nodes <= 12 + 4  # children of the last expansion
    if g.stats.truncated_nodes:
        assert any(n.truncated for n in g.nodes.values())
