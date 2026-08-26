"""Tests for the goal-based decision-point graph preprocessing."""
import warnings
warnings.filterwarnings("ignore")

import pytest

from app.core.env_factory import create_env
from app.policies.goal_based_policies import (
    build_decision_point_graph,
    find_switch_cells,
    find_switch_decision_cells,
    station_cells_from_env,
)
from app.policies.goal_based_policies.infrastructure_graph import (
    DIR_TO_DELTA,
    _get_transitions,
)


@pytest.fixture(scope="module")
def env():
    return create_env(width=30, height=30, number_of_agents=3, seed=42)


@pytest.fixture(scope="module")
def graph(env):
    return build_decision_point_graph(env)


def test_stations_are_agent_origins_and_targets(env, graph):
    stations = station_cells_from_env(env)
    assert stations, "expected at least one station"
    expected = set()
    for agent in env.agents:
        expected.add(tuple(int(v) for v in agent.initial_position))
        expected.add(tuple(int(v) for v in agent.target))
    assert set(stations) == expected
    for cell in stations:
        assert cell in graph.nodes
        assert "station" in graph.nodes[cell].kinds


def test_switch_decision_cells_sit_in_front_of_their_switch(env):
    switches = find_switch_cells(env)
    assert switches, "expected switches in a sparse env"
    decision_cells = find_switch_decision_cells(env, switches)
    assert decision_cells, "expected decision cells in front of switches"

    for cell, approaches in decision_cells.items():
        assert approaches
        for approach in approaches:
            assert approach.switch_cell in switches
            # Moving one cell along the waiting heading reaches the switch.
            dr, dc = DIR_TO_DELTA[approach.heading]
            assert (cell[0] + dr, cell[1] + dc) == approach.switch_cell
            # The approach is a funneled one: exactly one exit, shared with
            # another in-heading (a merge, not a diamond crossing).
            exits = _get_transitions(env, approach.switch_cell, approach.heading)
            assert sum(exits) == 1
            exit_dir = exits.index(1)
            assert any(
                h != approach.heading
                and _get_transitions(env, approach.switch_cell, h)[exit_dir]
                for h in range(4)
            )


def test_simple_switches_have_two_decision_cells(env):
    """Every plain 3-way switch contributes exactly two funneled approaches."""
    switches = find_switch_cells(env)
    decision_cells = find_switch_decision_cells(env, switches)
    approaches_per_switch = {}
    for approaches in decision_cells.values():
        for a in approaches:
            approaches_per_switch.setdefault(a.switch_cell, 0)
            approaches_per_switch[a.switch_cell] += 1

    simple = [
        s for s, facing in switches.items()
        if len(facing) == 1
        and sum(sum(_get_transitions(env, s, h)) for h in range(4)) == 4
    ]
    assert simple, "expected at least one simple 3-way switch"
    for s in simple:
        assert approaches_per_switch.get(s) == 2


def _move_heading(a, b):
    """Heading of the move from cell a to adjacent cell b (0=N,1=E,2=S,3=W)."""
    dr, dc = b[0] - a[0], b[1] - a[1]
    return {(-1, 0): 0, (0, 1): 1, (1, 0): 2, (0, -1): 3}[(dr, dc)]


def test_edges_connect_nodes_without_relevant_interior_nodes(env, graph):
    assert graph.edges
    for edge in graph.edges:
        assert edge.from_cell in graph.nodes
        assert edge.to_cell in graph.nodes
        assert edge.path[0] == edge.from_cell
        assert edge.path[-1] == edge.to_cell
        assert edge.length == len(edge.path) - 1 >= 1
        for a, b in zip(edge.path, edge.path[1:]):
            # Consecutive path cells are grid neighbours.
            assert abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1
        # Interior cells may only be nodes that are irrelevant for the
        # traversal direction: never a station, and a switch wait cell only
        # when the train's next move from it does NOT lead into its switch
        # (e.g. rolling away from the switch over the far branch).
        for a, b in zip(edge.path[:-2], edge.path[1:-1]):
            node = graph.nodes.get(b)
            if node is None:
                continue
            assert "station" not in node.kinds, (
                f"edge {edge.from_cell}->{edge.to_cell} passes station {b}"
            )
            orientation = _move_heading(a, b)
            exits = _get_transitions(env, b, orientation)
            assert not any(exits[ap.heading] for ap in node.approaches), (
                f"edge {edge.from_cell}->{edge.to_cell} passes decision "
                f"point {b} in its relevant direction"
            )


def test_decision_point_edges_are_directional(env, graph):
    """Edges at a pure switch wait cell respect its direction: a train
    arriving there must be about to enter the switch on its next move, and
    departures start from such an orientation."""

    def relevant_orientations(cell, node):
        return [
            o for o in range(4)
            if any(
                _get_transitions(env, cell, o)[ap.heading]
                for ap in node.approaches
            )
        ]

    checked_in = checked_out = 0
    for edge in graph.edges:
        to_node = graph.nodes[edge.to_cell]
        if "station" not in to_node.kinds:
            assert edge.in_direction in relevant_orientations(edge.to_cell, to_node)
            checked_in += 1
        from_node = graph.nodes[edge.from_cell]
        if "station" not in from_node.kinds:
            allowed_exits = set()
            for o in relevant_orientations(edge.from_cell, from_node):
                trans = _get_transitions(env, edge.from_cell, o)
                allowed_exits.update(d for d in range(4) if trans[d])
            assert edge.out_direction in allowed_exits
            checked_out += 1
    assert checked_in and checked_out


def test_travel_time_matches_simulated_traversal(env, graph):
    """Walk the rail cell by cell like a train at one tile per step and
    check the step count matches the stored travel time."""
    from flatland.core.grid.grid4_utils import get_new_position

    from app.policies.goal_based_policies.infrastructure_graph import (
        _get_transitions as get_transitions,
    )

    checked = 0
    for edge in graph.edges:
        position = edge.from_cell
        heading = None
        steps = 0
        for hop, expected in enumerate(edge.path[1:]):
            move = _move_heading(position, expected)
            if hop == 0:
                # The train's orientation while standing on the source node
                # depends on how it got there; the edge only fixes the exit.
                assert move == edge.out_direction
                assert any(
                    get_transitions(env, position, o)[move] for o in range(4)
                ), "edge leaves the source node on a transition that does not exist"
            else:
                assert get_transitions(env, position, heading)[move], (
                    "edge path uses a transition the rail does not allow"
                )
            heading = move
            position = tuple(int(v) for v in get_new_position(position, heading))
            steps += 1
            assert position == expected
        assert position == edge.to_cell
        assert steps == edge.travel_time
        assert heading == edge.in_direction
        checked += 1
    assert checked == len(graph.edges)


def test_every_node_has_an_outgoing_edge(graph):
    sources = {e.from_cell for e in graph.edges}
    for cell in graph.nodes:
        assert cell in sources, f"node {cell} has no outgoing edge"


def test_to_dict_is_json_serializable(graph):
    import json

    payload = graph.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert len(payload["nodes"]) == len(graph.nodes)
    assert len(payload["edges"]) == len(graph.edges)
    for edge in graph.edges:
        assert edge.to_dict()["travel_time"] == edge.travel_time


def test_mission_stations_sorted_like_frontend_registry(env):
    """Mission-derived stations are named S1… by (row, col) order, matching
    the frontend station layer (SessionStore.stations)."""
    from app.policies.goal_based_policies import stations_from_agent_missions

    stations = stations_from_agent_missions(env)
    cells = [s.stop_cells[0] for s in stations]
    assert cells == sorted(cells)
    assert [s.name for s in stations] == [f"S{i + 1}" for i in range(len(stations))]


def test_scene_stations_use_builder_coordinates():
    from app.policies.goal_based_policies import stations_from_scene

    scene = {"stations": [
        {"id": "st-1", "name": "Alpha", "x": 3, "y": 5},
        {"id": "st-2", "name": "Beta", "x": 7, "y": 2},
        {"broken": True},
    ]}
    stations = stations_from_scene(scene)
    # Builder scenes use (x, y) with row = y, col = x.
    assert [(s.name, s.stop_cells) for s in stations] == [
        ("Alpha", ((5, 3),)),
        ("Beta", ((2, 7),)),
    ]


@pytest.mark.integration
def test_ecml_stations_have_platform_stops():
    from app.policies.goal_based_policies import resolve_stations

    preset = "ecml2026-scene1-level0"
    ecml_env = create_env(scenario_preset_id=preset)
    stations = resolve_stations(ecml_env, scenario_preset_id=preset)

    # The physical network is shared across ECML scenes: all 25 cities from
    # stations.pkl have their platforms on rail and must all be included.
    fixture = [s for s in stations if s.source == "ecml_fixture"]
    assert len(fixture) == 25
    assert sum(len(s.stop_cells) for s in fixture) == 84
    for station in fixture:
        assert len(station.stop_cells) >= 2, "platforms expected per city"

    # Mission cells outside the platforms are kept as extra stops.
    mission_cells = set()
    for agent in ecml_env.agents:
        mission_cells.add(tuple(int(v) for v in agent.initial_position))
        mission_cells.add(tuple(int(v) for v in agent.target))
    all_stops = {c for s in stations for c in s.stop_cells}
    assert mission_cells <= all_stops

    # Every stop cell becomes a station node carrying its station name.
    graph = build_decision_point_graph(ecml_env, scenario_preset_id=preset)
    for station in stations:
        for cell in station.stop_cells:
            node = graph.nodes[cell]
            assert "station" in node.kinds
            assert node.station_name == station.name


def test_alternative_route_flags_match_reachability(env, graph):
    """Each edge's flag must equal 'can still get source->target without it',
    checked against an independent directed reachability computation."""
    from collections import deque

    edges = graph.edges
    alt = graph.edges_have_alternative_route()
    assert len(alt) == len(edges)

    adjacency = {}
    for i, e in enumerate(edges):
        adjacency.setdefault(e.from_cell, []).append((e.to_cell, i))

    def reachable_without(source, target, excluded):
        seen, queue = {source}, deque([source])
        while queue:
            cell = queue.popleft()
            for nxt, eid in adjacency.get(cell, ()):
                if eid == excluded or nxt in seen:
                    continue
                if nxt == target:
                    return True
                seen.add(nxt)
                queue.append(nxt)
        return False

    for i, edge in enumerate(edges):
        assert alt[i] == reachable_without(edge.from_cell, edge.to_cell, i)


def test_alternative_route_on_a_hand_built_graph():
    """Precise cases: a triangle gives every edge a detour; a single edge to
    a leaf does not; a doubled edge is its own alternative; and a loop back
    to the source must NOT count as reaching a leaf that only one edge
    reaches (the bug this feature was first written with)."""
    from app.policies.goal_based_policies.infrastructure_graph import (
        DecisionPointGraph,
        GraphEdge,
        GraphNode,
    )

    def build(edges):
        cells = {c for pair in edges for c in pair}
        nodes = {c: GraphNode(cell=c) for c in cells}
        return DecisionPointGraph(
            nodes=nodes,
            edges=[GraphEdge(x, y, 0, 0, (x, y)) for x, y in edges],
            switch_cells={},
        )

    a, b, c, d = (0, 0), (0, 1), (0, 2), (0, 3)

    # The feature is per edge: can its *source* still reach its *target*
    # without it. A directed triangle has out-degree 1 at every node, so no
    # edge has a second path to its own target.
    assert build([(a, b), (b, c), (c, a)]).edges_have_alternative_route() == [
        False, False, False
    ]

    # Two parallel a->b edges: each is the other's alternative.
    assert build([(a, b), (a, b)]).edges_have_alternative_route() == [True, True]

    # A genuine detour: a->b directly, and a->c->b around it. Only a->b has
    # the alternative; the two legs of the detour are each the sole path to
    # their target.
    assert build([(a, b), (a, c), (c, b)]).edges_have_alternative_route() == [
        True, False, False
    ]

    # a<->b loop plus a single b->c: no edge has an alternative, and crucially
    # b->c stays False even though b can be re-reached via a (the loop-back
    # bug this was first written with).
    assert build([(a, b), (b, a), (b, c)]).edges_have_alternative_route() == [
        False, False, False
    ]


@pytest.mark.parametrize("on_flatland", [True, False])
def test_visualization_writes_png(env, graph, tmp_path, on_flatland):
    from app.policies.goal_based_policies import save_decision_point_graph

    out = tmp_path / f"overlay_{on_flatland}.png"
    save_decision_point_graph(env, str(out), graph, on_flatland=on_flatland)
    assert out.exists() and out.stat().st_size > 0
