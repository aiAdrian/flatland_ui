"""Schedule planning and playback over the decision-point graph.

The core test is an end-to-end run: build a one-train scenario, plan its
run with shortest path, then play the schedule in the real Flatland env and
check the train arrives exactly when the plan says it does.
"""
import warnings
warnings.filterwarnings("ignore")

import pytest
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.step_utils.states import TrainState

from app.policies.goal_based_policies import (
    SchedulePlayer,
    TrainSchedule,
    build_decision_point_graph,
    plan_shortest_path,
)
from app.policies.goal_based_policies.infrastructure_graph import (
    _get_transitions,
    action_for_move,
    move_direction,
)
from app.policies.goal_based_policies.visualization import build_demo_env


def _one_train_scenario():
    """Small reproducible infrastructure with a single train."""
    env = build_demo_env(number_of_agents=1)
    graph = build_decision_point_graph(env)
    return env, graph


def _plan(env, graph, handle=0):
    agent = env.agents[handle]
    return plan_shortest_path(
        graph,
        env,
        tuple(int(v) for v in agent.initial_position),
        int(agent.initial_direction),
        tuple(int(v) for v in agent.target),
        handle=handle,
    )


def _edges_of(env, graph, schedule, start_heading):
    """Resolve the schedule's node list back to the edges a train drives."""
    cells = [graph.cell_of(e.node_id) for e in schedule.entries]
    heading = int(start_heading)
    for cell, nxt in zip(cells, cells[1:]):
        usable = [
            e for e in graph.edges_from(cell)
            if e.to_cell == nxt
            and _get_transitions(env, cell, heading)[e.out_direction]
        ]
        assert usable, f"no edge {cell} -> {nxt} usable with heading {heading}"
        edge = min(usable, key=lambda e: (e.travel_time, e.out_direction))
        yield edge
        heading = edge.in_direction


def _planned_time(env, graph, schedule, start_heading):
    return sum(e.travel_time for e in _edges_of(env, graph, schedule, start_heading))


def _run(env, graph, schedule, max_steps=400):
    """Play the schedule; return (steps from entering the map to DONE, arrived).

    Counting starts once the train is on its origin cell — that is the
    schedule's first node, and departure itself costs a step Flatland
    charges for placing the agent.
    """
    player = SchedulePlayer(graph, env, [schedule])
    entered = None
    for step in range(max_steps):
        env.step(player.act_many([0]))
        agent = env.agents[0]
        if entered is None and agent.position is not None:
            entered = step
        if agent.state == TrainState.DONE:
            return (step - entered if entered is not None else 0), True
    return 0, False


@pytest.fixture(scope="module")
def scenario():
    return _one_train_scenario()


def test_edge_moves_and_actions_match_the_path(scenario):
    env, graph = scenario
    for edge in graph.edges:
        moves = edge.moves
        assert len(moves) == edge.travel_time
        assert moves[0] == edge.out_direction
        assert moves[-1] == edge.in_direction
        for (a, b), move in zip(zip(edge.path, edge.path[1:]), moves):
            assert move_direction(a, b) == move

        # Actions replay the moves: after each action the heading is the
        # move it encoded, so the next action is relative to that.
        entry_heading = edge.out_direction
        actions = edge.actions(entry_heading)
        assert len(actions) == len(moves)
        heading = entry_heading
        for action, move in zip(actions, moves):
            assert action == action_for_move(heading, move)
            heading = move

        payload = edge.to_dict()
        assert payload["moves"] == list(moves)
        assert payload["actions"] == list(actions)


def test_schedule_flat_list_round_trip():
    schedule = TrainSchedule.from_flat_list(3, [7, 0, 11, 4, 2, 0])
    assert [(e.node_id, e.wait) for e in schedule.entries] == [(7, 0), (11, 4), (2, 0)]
    assert schedule.to_flat_list() == [7, 0, 11, 4, 2, 0]
    assert schedule.total_wait == 4
    with pytest.raises(ValueError):
        TrainSchedule.from_flat_list(0, [1, 0, 2])


def test_shortest_path_plan_is_consistent_with_the_graph(scenario):
    env, graph = scenario
    schedule = _plan(env, graph)
    assert schedule is not None, "target should be reachable"

    agent = env.agents[0]
    cells = [graph.cell_of(e.node_id) for e in schedule.entries]
    assert cells[0] == tuple(int(v) for v in agent.initial_position)
    assert cells[-1] == tuple(int(v) for v in agent.target)
    assert all(e.wait == 0 for e in schedule.entries), "single train never waits"

    # Consecutive nodes are joined by a real edge, usable with the
    # orientation the train actually has on arrival (asserted in _edges_of).
    edges = list(_edges_of(env, graph, schedule, agent.initial_direction))
    assert len(edges) == len(cells) - 1


def test_plan_is_as_short_as_flatlands_own_distance_map():
    """Independent check that the reduced graph preserves shortest paths:
    Flatland's distance map knows the true cost from (cell, direction)."""
    for number_of_agents in (1, 3):
        env = build_demo_env(number_of_agents=number_of_agents)
        graph = build_decision_point_graph(env)
        distances = env.distance_map.get()
        for handle, agent in enumerate(env.agents):
            schedule = _plan(env, graph, handle)
            assert schedule is not None
            start = tuple(int(v) for v in agent.initial_position)
            heading = int(agent.initial_direction)
            assert _planned_time(env, graph, schedule, heading) == (
                distances[handle, start[0], start[1], heading]
            )


def test_planned_run_reaches_the_target_in_the_planned_time():
    """End-to-end: plan by shortest path, play it, arrive on schedule."""
    env, graph = _one_train_scenario()
    schedule = _plan(env, graph)
    assert schedule is not None

    planned_time = _planned_time(
        env, graph, schedule, env.agents[0].initial_direction
    )
    steps, arrived = _run(env, graph, schedule)
    assert arrived, "train did not reach its target"
    assert steps == planned_time, (
        f"took {steps} steps, plan said {planned_time}"
    )


def test_waits_delay_arrival_by_exactly_the_wait_time():
    """A wait on a node holds the train there and shifts arrival by that much."""
    env, graph = _one_train_scenario()
    baseline = _plan(env, graph)
    assert baseline is not None and len(baseline.entries) >= 3

    base_steps, arrived = _run(env, graph, baseline)
    assert arrived

    # Same plan, but wait 5 turns on the second node.
    flat = baseline.to_flat_list()
    flat[3] = 5
    delayed = TrainSchedule.from_flat_list(0, flat)

    env2, graph2 = _one_train_scenario()
    delayed_steps, arrived2 = _run(env2, graph2, delayed)
    assert arrived2, "train with a wait did not reach its target"
    assert delayed_steps == base_steps + 5


def test_player_holds_the_train_while_waiting():
    """While a wait counts down the train stands still on the node."""
    env, graph = _one_train_scenario()
    plan = _plan(env, graph)
    flat = plan.to_flat_list()
    flat[3] = 3
    schedule = TrainSchedule.from_flat_list(0, flat)
    wait_cell = graph.cell_of(schedule.entries[1].node_id)

    player = SchedulePlayer(graph, env, [schedule])
    stalled = 0
    for _ in range(400):
        actions = player.act_many([0])
        agent = env.agents[0]
        position = (
            tuple(int(v) for v in agent.position)
            if agent.position is not None else None
        )
        if position == wait_cell and actions[0] == RailEnvActions.STOP_MOVING.value:
            stalled += 1
        env.step(actions)
        if env.agents[0].state == TrainState.DONE:
            break
    assert stalled == 3, f"expected 3 held steps on {wait_cell}, saw {stalled}"


# ── multi-stop lines ─────────────────────────────────────────────────

def _line_env(seed=0, agents=3):
    """Infrastructure whose trains call at several cities."""
    env = build_demo_env(seed=seed, width=45, height=45,
                         number_of_agents=agents, max_num_cities=4, line_length=4)
    return env, build_decision_point_graph(env)


def test_line_stops_lists_every_call_not_just_the_target():
    """`agent.target` is only the last waypoint, so routing to it skips the
    calls in between — `line_stops` is what exposes them."""
    from app.policies.goal_based_policies import line_stops

    env, _ = _line_env()
    for handle, agent in enumerate(env.agents):
        stops = line_stops(env, handle)
        assert stops[0] == tuple(int(v) for v in agent.initial_position)
        assert stops[-1] == tuple(int(v) for v in agent.target)
        assert len(stops) == len(agent.waypoints)
        assert len(stops) > 2, "this env should generate multi-stop lines"


def test_plan_line_calls_at_every_stop_where_shortest_path_skips_them():
    """The point of plan_line: a direct route to the final target misses
    intermediate cities entirely."""
    from app.policies.goal_based_policies import line_stops, plan_line
    from app.policies.goal_based_policies.dataset import _schedule_cells

    env, graph = _line_env()
    for handle in range(len(env.agents)):
        stops = line_stops(env, handle)
        line = plan_line(graph, env, handle)
        assert line is not None
        visited = _schedule_cells(env, graph, line)
        for stop in stops:
            assert stop in visited, f"train {handle} never reaches {stop}"

        direct = _plan(env, graph, handle)
        if direct is not None:
            skipped = [s for s in stops[1:-1]
                       if s not in _schedule_cells(env, graph, direct)]
            assert skipped, (
                "shortest path already covers every stop here, so this "
                "scenario cannot show what plan_line is for"
            )


def test_plan_line_resolves_end_to_end_from_the_default_heading():
    """The legs are concatenated into one schedule that starts at the
    train's origin, so the ordinary initial-direction default walks all of
    it — no truncation at the leg joins."""
    from app.policies.goal_based_policies import plan_line
    from app.policies.goal_based_policies.dataset import _schedule_edges

    env, graph = _line_env()
    for handle in range(len(env.agents)):
        line = plan_line(graph, env, handle)
        edges = _schedule_edges(env, graph, line)
        assert len(edges) == len(line.entries) - 1, (
            f"train {handle}: resolved {len(edges)} of "
            f"{len(line.entries) - 1} hops"
        )
        # Consecutive edges must actually join up.
        for before, after in zip(edges, edges[1:]):
            assert before.to_cell == after.from_cell


def test_plan_line_dwells_at_intermediate_stops_but_not_the_target():
    """Flatland counts an intermediate stop as served only with both an
    arrival and a departure, and a transfer needs the train to stand."""
    from app.policies.goal_based_policies import line_stops, plan_line

    env, graph = _line_env()
    handle = 0
    stops = line_stops(env, handle)
    line = plan_line(graph, env, handle, dwell=3)

    held = {graph.cell_of(e.node_id): e.wait for e in line.entries if e.wait > 0}
    for stop in stops[1:-1]:
        assert held.get(stop) == 3, f"no dwell at intermediate stop {stop}"
    assert line.entries[-1].wait == 0, "the final target should not dwell"
    assert graph.cell_of(line.entries[-1].node_id) == stops[-1]

    # dwell=0 keeps the same route but stops nowhere.
    nostop = plan_line(graph, env, handle, dwell=0)
    assert [e.node_id for e in nostop.entries] == [e.node_id for e in line.entries]
    assert nostop.total_wait == 0


def test_plan_line_output_is_runnable():
    from app.policies.goal_based_policies import plan_line
    from app.policies.goal_based_policies.rollout import run_schedules

    env, graph = _line_env()
    lines = [plan_line(graph, env, h) for h in range(len(env.agents))]
    assert all(line is not None for line in lines)
    result = run_schedules(env, graph, lines)
    assert result.steps > 0
    assert set(result.delays) == {line.handle for line in lines}


def test_plan_line_fits_the_encoder_cap():
    """Multi-leg schedules are several times longer than single-leg ones,
    so the cap has to cover them or encode_sample rejects the sample."""
    from app.policies.goal_based_policies import plan_line
    from app.policies.goal_based_policies.dataset import MAX_SCHEDULE_NODES

    longest = 0
    for seed in range(6):
        try:
            env, graph = _line_env(seed=seed, agents=4)
        except Exception:
            continue  # flatland cannot build every line_length=4 scenario
        for handle in range(len(env.agents)):
            line = plan_line(graph, env, handle)
            if line is not None:
                longest = max(longest, len(line.entries))
    assert longest > 0
    assert longest <= MAX_SCHEDULE_NODES, (
        f"longest multi-stop schedule {longest} exceeds "
        f"MAX_SCHEDULE_NODES={MAX_SCHEDULE_NODES}"
    )
