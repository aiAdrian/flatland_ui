"""Branch generation for the schedule search: completion, options, pruning."""
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.policies.goal_based_policies.branching import (  # noqa: E402
    WAIT_MENU,
    advance_through_forced,
    arrival_time,
    complete_from,
    has_planned_overlap,
    initial_prefixes,
    is_complete,
    next_decision,
    route_options,
)
from app.policies.goal_based_policies.dataset import (  # noqa: E402
    Layout,
    build_layout_env,
    plan_all_lines,
)
from app.policies.goal_based_policies.infrastructure_graph import (  # noqa: E402
    build_decision_point_graph,
)
from app.policies.goal_based_policies.schedule import (  # noqa: E402
    ScheduleEntry,
    plan_avoiding_overlaps,
)


@pytest.fixture(scope="module")
def scenario():
    env = build_layout_env(Layout(index=0, seed=2001, size=30, cities=2), 4)
    graph = build_decision_point_graph(env)
    base = plan_all_lines(env, graph)
    assert base is not None
    return env, graph, base


def test_completing_a_bare_origin_reproduces_plan_line(scenario):
    """The completion *is* the baseline planner applied to whatever is not
    yet committed — so committing nothing must give the baseline plan,
    entry for entry, or leaf scores would not be comparable to it."""
    env, graph, base = scenario
    for schedule in base:
        origin = schedule.entries[0]
        completed = complete_from(
            env, graph, schedule.handle, (ScheduleEntry(origin.node_id, 0),)
        )
        assert completed is not None
        assert completed.entries == schedule.entries


def test_an_unresolvable_prefix_is_a_dead_branch(scenario):
    env, graph, base = scenario
    origin = base[0].entries[0]
    looped = (ScheduleEntry(origin.node_id, 0), ScheduleEntry(origin.node_id, 0))
    assert complete_from(env, graph, 0, looped) is None
    assert route_options(env, graph, 0, looped) == []


def test_initial_prefixes_stop_at_the_first_real_choice(scenario):
    """Forced nodes are driven through without spending a decision; the
    search should only ever be asked about nodes with ≥2 ways onward."""
    env, graph, _ = scenario
    prefixes = initial_prefixes(env, graph)
    assert set(prefixes) == {0, 1, 2, 3}
    for handle, prefix in prefixes.items():
        options = route_options(env, graph, handle, prefix)
        assert len(options) != 1  # a real choice, or nothing left to choose
        assert advance_through_forced(env, graph, handle, prefix) == prefix


def test_route_options_are_feasible_distinct_and_capped(scenario):
    env, graph, _ = scenario
    prefixes = initial_prefixes(env, graph)
    decision = next_decision(env, graph, prefixes)
    assert decision is not None
    edges = route_options(env, graph, decision.handle, prefixes[decision.handle])
    assert len(edges) >= 2
    assert len({e.to_cell for e in edges}) == len(edges)
    assert route_options(
        env, graph, decision.handle, prefixes[decision.handle], k=1
    ) == edges[:1]


def test_decision_options_cross_routes_with_the_hold_menu(scenario):
    env, graph, _ = scenario
    prefixes = initial_prefixes(env, graph)
    decision = next_decision(env, graph, prefixes)
    assert decision is not None
    routes = route_options(env, graph, decision.handle, prefixes[decision.handle])
    assert len(decision.options) == len(routes) * len(WAIT_MENU)
    assert sorted({o.wait for o in decision.options}) == sorted(WAIT_MENU)

    held_at = len(prefixes[decision.handle]) - 1
    base_wait = prefixes[decision.handle][-1].wait
    for option in decision.options:
        # The hold lands on the decision node, on top of any dwell it has.
        assert option.prefix[held_at].wait == base_wait + option.wait
        # The chosen edge's target is the next committed node.
        assert option.prefix[held_at + 1].node_id == graph.node_id(
            option.edge.to_cell)
        # Every option leads somewhere the completion can finish from.
        assert complete_from(
            env, graph, decision.handle, option.prefix) is not None


def test_decisions_run_chronologically_and_deterministically(scenario):
    """Whoever reaches their choice first decides first, repeatably —
    and committing first options one by one finishes every train."""
    env, graph, _ = scenario
    prefixes = initial_prefixes(env, graph)
    first = next_decision(env, graph, prefixes)
    again = next_decision(env, graph, prefixes)
    assert (first.handle, first.node_id, first.time) == (
        again.handle, again.node_id, again.time)
    assert first.time == min(
        arrival_time(env, graph, h, p) for h, p in prefixes.items()
        if route_options(env, graph, h, p)
    )

    steps = 0
    while steps < 50:
        decision = next_decision(env, graph, prefixes)
        if decision is None:
            break
        prefixes[decision.handle] = decision.options[0].prefix
        steps += 1
    assert steps < 50
    assert all(
        is_complete(env, graph, handle, prefix)
        for handle, prefix in prefixes.items()
    )


def test_pruner_flags_colliding_plans_and_passes_clean_ones(scenario):
    """The conflict-blind baseline collides on paper; the avoidance
    planner's whole job is to hold trains until it does not — the
    predicate must agree with both, and a lone train can never collide
    (not even with its own path, which the occupancy sim emits twice)."""
    env, graph, base = scenario
    assert has_planned_overlap(env, graph, base)
    assert not has_planned_overlap(env, graph, [base[0]])
    avoided = plan_avoiding_overlaps(
        env, graph, base, safety=1, max_total_wait=200, max_iterations=2000)
    assert not has_planned_overlap(env, graph, avoided)
