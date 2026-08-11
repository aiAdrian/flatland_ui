"""The static safety measure: slack, deadlock exposure, track load, cascade."""
import json
import math
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.policies.goal_based_policies.infrastructure_graph import (  # noqa: E402
    GraphEdge,
)
from app.policies.goal_based_policies.safety import (  # noqa: E402
    PlanTimeline,
    SafetyParams,
    assess_safety,
    assess_timelines,
    build_timelines,
    corridor_alternatives,
)

PARAMS = SafetyParams()


def _corridor(row=0, start=0, length=3):
    """A straight corridor and its two directed edges (east, west)."""
    path = tuple((row, start + i) for i in range(length + 1))
    east = GraphEdge(
        from_cell=path[0], to_cell=path[-1],
        out_direction=1, in_direction=1, path=path,
    )
    west = GraphEdge(
        from_cell=path[-1], to_cell=path[0],
        out_direction=3, in_direction=3, path=tuple(reversed(path)),
    )
    return east, west


def _timeline(handle, windows=(), slack=10.0, node_visits=None,
              playable=True, arrival=100.0):
    windows = tuple(windows)
    if node_visits is None:
        # What build_timelines produces: the endpoints of every window are
        # covered by a node visit.
        node_visits = []
        for edge, enter, exit_ in windows:
            node_visits.append((edge.from_cell, enter, enter))
            node_visits.append((edge.to_cell, exit_, exit_))
    return PlanTimeline(
        handle=handle,
        windows=windows,
        node_visits=tuple(node_visits),
        playable=playable,
        planned_arrival=arrival,
        latest_arrival=None if slack is None else arrival + slack,
    )


def test_more_buffer_is_safer():
    comfortable = assess_timelines(
        [_timeline(h, slack=10.0) for h in range(3)], {})
    tight = assess_timelines(
        [_timeline(h, slack=1.0) for h in range(3)], {})
    assert comfortable.slack_score > tight.slack_score
    expected = (1 - PARAMS.p_disturb * math.exp(-10 / PARAMS.tau_slack)) ** 3
    assert comfortable.slack_score == pytest.approx(expected)


def test_one_zero_buffer_train_caps_the_slack_score():
    """The score is a survival product, not a mean: five comfortable trains
    must not be able to hide the one that cannot absorb anything."""
    fleet = [_timeline(h, slack=10.0) for h in range(5)]
    report = assess_timelines(fleet + [_timeline(5, slack=0.0)], {})
    assert report.slack_score <= 1 - PARAMS.p_disturb
    assert assess_timelines(fleet, {}).slack_score > 1 - PARAMS.p_disturb


def test_a_plan_that_is_already_late_is_maximally_fragile():
    report = assess_timelines([_timeline(0, slack=-5.0)], {})
    assert report.trains[0].fragility == pytest.approx(1.0)
    assert report.trains[0].slack == pytest.approx(-5.0)


def test_a_train_without_a_deadline_cannot_be_late():
    report = assess_timelines([_timeline(0, slack=None)], {})
    assert report.trains[0].slack is None
    assert report.trains[0].fragility == 0.0
    assert report.slack_score == 1.0


def test_opposing_meets_score_by_their_gap():
    """Two trains through one corridor head-on: the minutes between one
    clearing it and the other entering are all that keeps them apart."""
    east, west = _corridor()
    tight = assess_timelines([
        _timeline(0, windows=[(east, 10.0, 13.0)]),
        _timeline(1, windows=[(west, 15.0, 18.0)]),
    ], {})
    wide = assess_timelines([
        _timeline(0, windows=[(east, 10.0, 13.0)]),
        _timeline(1, windows=[(west, 60.0, 63.0)]),
    ], {})
    assert len(tight.meets) == 1
    assert tight.meets[0].gap == pytest.approx(2.0)
    assert (tight.meets[0].first, tight.meets[0].second) == (0, 1)
    assert tight.deadlock_score < wide.deadlock_score
    expected = 1 - PARAMS.q_deadlock * math.exp(-2 / PARAMS.tau_deadlock)
    assert tight.deadlock_score == pytest.approx(expected)


def test_opposing_detection_survives_offset_endpoints():
    """On real networks the two directions over one physical track run
    between *different* nodes — switch wait-cells are directional — so the
    opposing edges' paths overlap without ever being equal. Grouping by
    edge identity finds zero opposing traffic on real graphs (measured);
    detection has to work on the shared cells alone."""
    east, _ = _corridor()  # (0,0) -> (0,3)
    west_offset = GraphEdge(
        from_cell=(0, 4), to_cell=(0, 1), out_direction=3, in_direction=3,
        path=((0, 4), (0, 3), (0, 2), (0, 1)),
    )
    report = assess_timelines([
        _timeline(0, windows=[(east, 10.0, 13.0)]),
        _timeline(1, windows=[(west_offset, 15.0, 18.0)]),
    ], {})
    assert len(report.meets) == 1
    meet = report.meets[0]
    assert set(meet.cells) == {(0, 1), (0, 2), (0, 3)}
    assert meet.gap == pytest.approx(3.0)  # east clears (0,3) at 13, west
    #                                        first needs it at 16
    assert (meet.first, meet.second) == (0, 1)


def test_a_planned_opposing_overlap_is_gap_zero():
    """A plan that already has both trains inside the corridor at once is
    banking entirely on the reactive layer — maximum fragility."""
    east, west = _corridor()
    report = assess_timelines([
        _timeline(0, windows=[(east, 10.0, 13.0)]),
        _timeline(1, windows=[(west, 11.0, 14.0)]),
    ], {})
    assert report.meets[0].gap == 0.0
    assert report.deadlock_score == pytest.approx(1 - PARAMS.q_deadlock)


def test_an_alternative_route_discounts_the_meet():
    east, west = _corridor()
    timelines = [
        _timeline(0, windows=[(east, 10.0, 13.0)]),
        _timeline(1, windows=[(west, 11.0, 14.0)]),
    ]
    trapped = assess_timelines(timelines, {})
    reroutable = assess_timelines(
        timelines, {frozenset(east.path): True})
    assert reroutable.meets[0].has_alternative
    assert reroutable.deadlock_score > trapped.deadlock_score
    expected = 1 - PARAMS.q_deadlock * PARAMS.alt_discount
    assert reroutable.deadlock_score == pytest.approx(expected)


def test_same_direction_following_is_coupling_not_deadlock():
    """A follower trailing a leader is delay risk, not deadlock risk — and
    its coupling is the per-cell headway, not the corridor-hull gap."""
    east, _ = _corridor()
    report = assess_timelines([
        _timeline(0, windows=[(east, 10.0, 13.0)]),
        _timeline(1, windows=[(east, 16.0, 19.0)]),
    ], {})
    assert report.meets == []
    assert len(report.cascade_edges) == 1
    edge = report.cascade_edges[0]
    assert (edge.from_handle, edge.to_handle) == (0, 1)
    # The follower reaches every cell 6 minutes after the leader left it.
    assert edge.headway == pytest.approx(6.0)
    assert report.largest_component == 2


def test_track_score_counts_trains_one_blockage_catches():
    """Three trains threading one corridor within minutes of each other are
    all caught by a single blockage; spread far apart they are not. The
    corridor is one resource — a longer corridor must not be penalised
    more for the same conflict."""
    east, _ = _corridor()
    clustered = assess_timelines([
        _timeline(h, windows=[(east, t, t + 3.0)])
        for h, t in enumerate((0.0, 5.0, 10.0))
    ], {})
    spread = assess_timelines([
        _timeline(h, windows=[(east, t, t + 3.0)])
        for h, t in enumerate((0.0, 100.0, 200.0))
    ], {})
    assert len(clustered.loads) == 1
    assert clustered.loads[0].peak == 3
    assert clustered.loads[0].trains == (0, 1, 2)
    assert set(clustered.loads[0].cells) == set(east.path)
    assert clustered.track_score == pytest.approx(1 - PARAMS.q_track)
    assert spread.loads == []
    assert spread.track_score == 1.0


def test_holds_at_nodes_are_visible_to_track_exposure():
    """A hold occupies its node cell the whole time, so two trains dwelling
    at one node are exposed to the same blockage."""
    report = assess_timelines([
        _timeline(0, node_visits=[((5, 5), 0.0, 10.0)]),
        _timeline(1, node_visits=[((5, 5), 5.0, 12.0)]),
    ], {})
    assert len(report.loads) == 1
    assert report.loads[0].cells == ((5, 5),)
    assert report.loads[0].peak == 2
    assert report.track_score < 1.0
    assert report.meets == []  # a single shared cell has no direction


def test_cascade_reach_shrinks_by_the_headway_each_hop():
    east_ab, _ = _corridor(row=0)
    east_bc, _ = _corridor(row=1)
    report = assess_timelines([
        _timeline(0, windows=[(east_ab, 0.0, 3.0)]),
        _timeline(1, windows=[(east_ab, 4.0, 7.0), (east_bc, 20.0, 23.0)]),
        _timeline(2, windows=[(east_bc, 23.0, 26.0)]),
    ], {})
    reaches = {t.handle: t.reach for t in report.trains}
    # delta=10 through per-cell headways 4 then 3: train 1 catches 6,
    # train 2 still gets 3.
    assert reaches == {0: 2, 1: 1, 2: 0}
    assert report.largest_component == 3

    exhausted = assess_timelines([
        _timeline(0, windows=[(east_ab, 0.0, 3.0)]),
        _timeline(1, windows=[(east_ab, 6.0, 9.0), (east_bc, 20.0, 23.0)]),
        _timeline(2, windows=[(east_bc, 26.0, 29.0)]),
    ], {})
    reaches = {t.handle: t.reach for t in exhausted.trains}
    # Headways 6 then 6: 10 minutes of disturbance die before train 2.
    assert reaches == {0: 1, 1: 1, 2: 0}


def test_unplayable_schedules_are_flagged_not_scored():
    report = assess_timelines([
        _timeline(0, slack=10.0),
        _timeline(1, playable=False),
    ], {})
    assert report.unplayable == (1,)
    assert [t.handle for t in report.trains] == [0]


def test_the_composite_is_the_product_of_the_components():
    east, west = _corridor()
    report = assess_timelines([
        _timeline(0, windows=[(east, 10.0, 13.0)], slack=2.0),
        _timeline(1, windows=[(west, 15.0, 18.0)], slack=0.0),
    ], {})
    assert report.safety == pytest.approx(
        report.slack_score * report.deadlock_score
        * report.track_score * report.cascade_score
    )
    for score in (report.slack_score, report.deadlock_score,
                  report.track_score, report.cascade_score, report.safety):
        assert 0.0 <= score <= 1.0


def test_the_report_serializes_for_the_hmi():
    east, west = _corridor()
    report = assess_timelines([
        _timeline(0, windows=[(east, 10.0, 13.0)]),
        _timeline(1, windows=[(west, 15.0, 18.0)]),
    ], {})
    payload = json.loads(json.dumps(report.to_dict()))
    assert set(payload) >= {
        "safety", "slack_score", "deadlock_score", "track_score",
        "cascade_score", "trains", "meets", "loads", "cascade_edges",
        "largest_component", "unplayable", "params",
    }
    assert payload["meets"][0]["cells"][0] == [0, 0]


@pytest.mark.integration
def test_a_real_scenario_scores_end_to_end():
    """The full path — env, graph, planned lines, assessment — has to hold
    together on a real network, and precomputing the per-network bypass
    analysis must not change the result."""
    from app.policies.goal_based_policies.dataset import (
        Layout, build_layout_env, plan_all_lines,
    )
    from app.policies.goal_based_policies.infrastructure_graph import (
        build_decision_point_graph,
    )

    env = build_layout_env(Layout(index=0, seed=2001, size=30, cities=2), 4)
    graph = build_decision_point_graph(env)
    schedules = plan_all_lines(env, graph)
    assert schedules is not None

    report = assess_safety(env, graph, schedules)
    assert 0.0 <= report.safety <= 1.0
    assert len(report.trains) + len(report.unplayable) == 4
    assert all(meet.gap >= 0 for meet in report.meets)
    assert all(load.peak >= 2 for load in report.loads)
    json.dumps(report.to_dict())

    cached = assess_safety(
        env, graph, schedules, alternatives=corridor_alternatives(graph))
    assert cached.safety == pytest.approx(report.safety)

    timelines = build_timelines(env, graph, schedules)
    playable = [t for t in timelines if t.playable]
    assert playable, "seed 2001 should produce at least one playable plan"
    for timeline in playable:
        if timeline.windows:
            assert timeline.planned_arrival == timeline.windows[-1][2]
