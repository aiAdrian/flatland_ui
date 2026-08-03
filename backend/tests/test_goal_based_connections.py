"""Connections as the planned order of trains at a station."""
import warnings

warnings.filterwarnings("ignore")

from itertools import combinations  # noqa: E402

import pytest  # noqa: E402

from app.policies.goal_based_policies.connections import (  # noqa: E402
    planned_connections,
    planned_order,
    station_calls,
)
from app.policies.goal_based_policies.schedule import line_stops  # noqa: E402
from app.policies.goal_based_policies.stations import resolve_stations  # noqa: E402
from app.policies.goal_based_policies.visualization import build_demo_env  # noqa: E402


def _line_env(seed=0, agents=4, cities=4):
    env = build_demo_env(seed=seed, width=45, height=45, number_of_agents=agents,
                         max_num_cities=cities, line_length=4)
    return env, resolve_stations(env)


def test_calls_come_from_the_timetables_earliest_departures():
    """The planned time must be the train's own earliest departure at that
    stop — that is the plan we are holding the run to."""
    env, stations = _line_env()
    calls = station_calls(env, stations)
    assert calls

    for call in calls:
        agent = env.agents[call.handle]
        assert call.time == agent.waypoints_earliest_departure[call.stop_index]
        assert call.from_departure
        assert line_stops(env, call.handle)[call.stop_index] == call.cell


def test_terminal_stops_are_excluded_by_default_and_opt_in():
    """A terminus has no earliest departure; its only planned time is a
    deadline, which is not comparable with departure times."""
    env, stations = _line_env()
    default = station_calls(env, stations)
    with_terminal = station_calls(env, stations, include_terminal=True)

    assert all(c.from_departure for c in default)
    extra = [c for c in with_terminal if not c.from_departure]
    assert extra, "this env should have terminating trains"
    assert len(with_terminal) == len(default) + len(extra)

    # The opt-in ones are exactly the last stop of each line, timed by the
    # latest arrival.
    for call in extra:
        agent = env.agents[call.handle]
        assert call.stop_index == len(line_stops(env, call.handle)) - 1
        assert call.time == agent.waypoints_latest_arrival[call.stop_index]


def test_calls_are_filed_under_the_station_owning_their_cell():
    env, stations = _line_env(agents=6)
    by_id = {s.id: set(s.stop_cells) for s in stations}
    for sid, calls in planned_order(env, stations).items():
        assert {c.cell for c in calls} <= by_id[sid]


def test_platform_grouping_makes_trains_on_different_platforms_meet():
    """Trains stopping on different platforms of one city must count as
    meeting there — that is why stations group cells at all.

    Measured on this generator, platform variety comes from *terminating*
    trains: with terminal calls excluded every train reaches a given city on
    the same platform (0/79 stations across 20 seeds), while including them
    puts 80% of stations on more than one platform. So this is asserted
    where the effect exists rather than pretending it is everywhere.
    """
    env, stations = _line_env(agents=6)
    order = planned_order(env, stations, include_terminal=True)

    multi = {
        sid: {c.cell for c in calls}
        for sid, calls in order.items()
        if len({c.cell for c in calls}) > 1
    }
    assert multi, "no station reached on two platforms; premise does not hold"

    by_id = {s.id: set(s.stop_cells) for s in stations}
    for sid, cells in multi.items():
        assert cells <= by_id[sid]
        # Trains on those different platforms are connected to each other,
        # which is exactly what would be lost without the grouping.
        pairs = {
            c.pair for c in planned_connections(env, stations, include_terminal=True)
            if c.station_id == sid
        }
        handles = [c.handle for c in order[sid]]
        assert len(pairs) == len(handles) * (len(handles) - 1) // 2


def test_order_is_sorted_by_planned_time_and_is_total():
    env, stations = _line_env()
    for calls in planned_order(env, stations).values():
        keys = [(c.time, c.handle) for c in calls]
        assert keys == sorted(keys)
        # One call per train per station, so handles are unique.
        assert len({c.handle for c in calls}) == len(calls)


def test_every_pair_at_a_station_is_a_connection_feeder_first():
    """All-to-all, not just consecutive: reordering two non-adjacent trains
    still breaks a transfer a passenger could have made."""
    env, stations = _line_env()
    order = planned_order(env, stations)
    connections = planned_connections(env, stations)

    expected = sum(len(calls) * (len(calls) - 1) // 2 for calls in order.values())
    assert len(connections) == expected
    assert len(connections) == len({(c.station_id, c.pair) for c in connections})

    for connection in connections:
        calls = {c.handle: c.time for c in order[connection.station_id]}
        assert calls[connection.feeder] < calls[connection.connector], (
            "feeder must be the earlier train"
        )
        assert connection.planned_gap == (
            calls[connection.connector] - calls[connection.feeder]
        )
        assert connection.planned_gap > 0

    # Both directions of a pair never appear.
    for a, b in combinations(connections, 2):
        if a.station_id == b.station_id:
            assert a.pair != (b.connector, b.feeder)


def test_simultaneous_trains_are_not_a_connection(monkeypatch):
    """Two trains planned for the same step have no order to keep, so
    demanding one would be labelling noise."""
    env, stations = _line_env()
    order = planned_order(env, stations)
    station_id = max(order, key=lambda s: len(order[s]))
    calls = order[station_id]
    assert len(calls) >= 2

    # Force two trains at this station onto the same planned time.
    first, second = calls[0], calls[1]
    agent = env.agents[second.handle]
    departures = list(agent.waypoints_earliest_departure)
    departures[second.stop_index] = first.time
    monkeypatch.setattr(agent, "waypoints_earliest_departure", departures)

    pairs = {
        c.pair for c in planned_connections(env, stations)
        if c.station_id == station_id
    }
    assert (first.handle, second.handle) not in pairs
    assert (second.handle, first.handle) not in pairs


def test_env_without_waypoints_still_yields_calls():
    """Flatland's default line_length is 2, so origin/target only — the
    origin still departs and can feed a connection."""
    env = build_demo_env(seed=3, width=40, height=40,
                         number_of_agents=4, max_num_cities=3)
    stations = resolve_stations(env)
    assert all(len(line_stops(env, h)) == 2 for h in range(len(env.agents)))

    calls = station_calls(env, stations)
    assert calls and all(c.stop_index == 0 for c in calls)
    for connection in planned_connections(env, stations):
        assert connection.planned_gap > 0


@pytest.mark.integration
def test_connections_are_reproducible_for_a_seed():
    a_env, a_st = _line_env(seed=5)
    b_env, b_st = _line_env(seed=5)
    a = [(c.station_id, c.pair, c.planned_gap) for c in planned_connections(a_env, a_st)]
    b = [(c.station_id, c.pair, c.planned_gap) for c in planned_connections(b_env, b_st)]
    assert a == b


# ── measuring what a run actually did ────────────────────────────────

def _run_with_connections(seed=1, agents=5):
    """Plan every train's line, run it, and judge the connections."""
    from app.policies.goal_based_policies.connections import (
        evaluate_connections, observed_times, station_watch_cells)
    from app.policies.goal_based_policies.infrastructure_graph import (
        build_decision_point_graph)
    from app.policies.goal_based_policies.rollout import run_schedules
    from app.policies.goal_based_policies.schedule import plan_line

    env, stations = _line_env(seed=seed, agents=agents)
    graph = build_decision_point_graph(env)
    lines = [plan_line(graph, env, h) for h in range(len(env.agents))]
    assert all(line is not None for line in lines)
    connections = planned_connections(env, stations)
    result = run_schedules(env, graph, lines,
                           watch_cells=station_watch_cells(stations))
    times = observed_times(stations, result.occupancy)
    return env, stations, connections, result, times


def test_rollout_records_station_occupancy_only_for_watched_cells():
    from app.policies.goal_based_policies.connections import station_watch_cells
    from app.policies.goal_based_policies.infrastructure_graph import (
        build_decision_point_graph)
    from app.policies.goal_based_policies.rollout import run_schedules
    from app.policies.goal_based_policies.schedule import plan_line

    env, stations = _line_env(seed=1, agents=4)
    graph = build_decision_point_graph(env)
    lines = [plan_line(graph, env, h) for h in range(len(env.agents))]

    plain = run_schedules(env, graph, lines)
    assert all(not cells for cells in plain.occupancy.values()), (
        "occupancy must stay empty unless watch_cells was asked for"
    )

    env2, _ = _line_env(seed=1, agents=4)
    graph2 = build_decision_point_graph(env2)
    lines2 = [plan_line(graph2, env2, h) for h in range(len(env2.agents))]
    watched = set(station_watch_cells(stations))
    traced = run_schedules(env2, graph2, lines2, watch_cells=watched)

    seen = {c for cells in traced.occupancy.values() for c in cells}
    assert seen, "no train was ever recorded at a station"
    assert seen <= watched, "recorded a cell that was not watched"
    for cells in traced.occupancy.values():
        for first, last in cells.values():
            assert 1 <= first <= last

    # Watching must not change the outcome it is observing.
    assert traced.all_arrived == plain.all_arrived
    assert traced.total_delay == plain.total_delay


def test_observed_time_is_the_last_step_at_the_station():
    """The planned side is an earliest *departure*, so the comparable
    observed moment is when the train is done there, not when it arrived."""
    from app.policies.goal_based_policies.connections import observed_times

    _, stations, _, result, times = _run_with_connections()
    cell_to_station = {c: s.id for s in stations for c in s.stop_cells}

    expected: dict = {}
    for handle, cells in result.occupancy.items():
        for cell, (first, last) in cells.items():
            sid = cell_to_station[cell]
            assert first <= last
            key = (handle, sid)
            expected[key] = max(last, expected.get(key, last))

    # Exactly the last step per (train, station) — several platforms of one
    # station collapse into the single call they are.
    assert times == expected
    assert len(times) <= sum(len(cells) for cells in result.occupancy.values())


def test_outcomes_classify_kept_reordered_and_absent():
    _, _, connections, _, times = _run_with_connections()
    from app.policies.goal_based_policies.connections import evaluate_connections

    report = evaluate_connections(connections, times)
    assert report.total == len(connections)
    assert set(report.reasons()) <= {
        "kept", "reordered", "feeder_absent", "connector_absent"}

    for outcome in report.outcomes:
        c = outcome.connection
        feeder, connector = times.get((c.feeder, c.station_id)), \
            times.get((c.connector, c.station_id))
        if feeder is None:
            assert outcome.reason == "feeder_absent" and not outcome.kept
        elif connector is None:
            assert outcome.reason == "connector_absent" and not outcome.kept
        elif feeder <= connector:
            assert outcome.reason == "kept" and outcome.kept
            assert outcome.observed_gap == connector - feeder
        else:
            assert outcome.reason == "reordered" and not outcome.kept
            assert outcome.observed_gap < 0

    assert report.kept == sum(1 for o in report.outcomes if o.kept)
    assert report.kept_ratio == pytest.approx(report.kept / report.total)


def test_reordering_is_detected_from_the_times():
    """Constructed rather than hoped for: flip the two trains' observed
    times and the same connection must flip from kept to reordered."""
    from app.policies.goal_based_policies.connections import (
        ConnectionReport, PlannedConnection, evaluate_connections)

    connection = PlannedConnection(
        station_id="city_0", feeder=0, connector=1, planned_gap=30)
    kept = evaluate_connections([connection], {(0, "city_0"): 10, (1, "city_0"): 40})
    assert kept.outcomes[0].kept and kept.outcomes[0].reason == "kept"
    assert kept.kept_ratio == 1.0

    flipped = evaluate_connections([connection], {(0, "city_0"): 40, (1, "city_0"): 10})
    assert not flipped.outcomes[0].kept
    assert flipped.outcomes[0].reason == "reordered"
    assert flipped.outcomes[0].observed_gap == -30
    assert flipped.kept_ratio == 0.0

    # Simultaneous is still a possible transfer, so it counts as kept.
    tied = evaluate_connections([connection], {(0, "city_0"): 20, (1, "city_0"): 20})
    assert tied.outcomes[0].kept

    # Absent trains are separated from reordering, and an empty plan scores 1.
    # A train that never came breaks the connection: the passenger is left
    # standing, so it scores 0 rather than being excused.
    absent = evaluate_connections([connection], {(1, "city_0"): 10})
    assert absent.outcomes[0].reason == "feeder_absent"
    assert not absent.outcomes[0].kept
    assert absent.served == 0
    assert absent.kept_ratio == 0.0
    assert ConnectionReport(outcomes=[]).kept_ratio == 1.0


def test_a_missing_train_counts_against_the_label():
    """The label is the passenger's chance of making their connection, so a
    train that never arrives must count as broken, not be excluded."""
    from app.policies.goal_based_policies.connections import (
        PlannedConnection, evaluate_connections)

    conns = [
        PlannedConnection("s", 0, 1, 10),   # kept
        PlannedConnection("s", 0, 2, 20),   # reordered
        PlannedConnection("s", 0, 3, 30),   # connector never arrives
    ]
    times = {(0, "s"): 5, (1, "s"): 9, (2, "s"): 1}
    report = evaluate_connections(conns, times)

    assert report.total == 3 and report.kept == 1
    # 1 of 3, not 1 of the 2 that happened to be served.
    assert report.kept_ratio == pytest.approx(1 / 3)
    assert report.served == 2, "served stays available as a diagnostic"
    assert report.reasons() == {
        "kept": 1, "reordered": 1, "connector_absent": 1}

    # Losing the train that was making a connection work costs the label;
    # losing one whose connection was already broken cannot cost it twice.
    lost_kept = evaluate_connections(conns, {(0, "s"): 5, (2, "s"): 1})
    assert lost_kept.kept == 0
    assert lost_kept.kept_ratio < report.kept_ratio

    already_broken = evaluate_connections(conns, {(0, "s"): 5, (1, "s"): 9})
    assert already_broken.kept_ratio == report.kept_ratio
    assert already_broken.reasons()["connector_absent"] == 2


@pytest.mark.integration
def test_connection_labels_are_not_degenerate():
    """The label has to vary across scenarios, or there is nothing to learn."""
    from app.policies.goal_based_policies.connections import evaluate_connections

    ratios, reasons = [], set()
    for seed in range(8):
        try:
            _, _, connections, _, times = _run_with_connections(seed=seed)
        except Exception:
            continue
        report = evaluate_connections(connections, times)
        if report.total:
            ratios.append(report.kept_ratio)
            reasons |= set(report.reasons())
    assert len(ratios) >= 4
    assert min(ratios) < max(ratios), "kept_ratio is constant across scenarios"
    # Both failure modes must occur, or the label is only measuring one.
    assert "reordered" in reasons
    assert {"feeder_absent", "connector_absent"} & reasons
