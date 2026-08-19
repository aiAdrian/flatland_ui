"""The fast graph-level simulator, and the action model on top of it.

The simulator is a *model* of Flatland, and the whole design rests on the
two agreeing. That is what most of this file checks: movement rules,
deadlock, holds, and — at the end — that a plan the model says works also
works when the real environment plays it.
"""
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.policies.goal_based_policies.infrastructure_graph import (  # noqa: E402
    build_decision_point_graph,
)
from app.policies.goal_based_policies.visualization import (  # noqa: E402
    build_demo_env,
)
from app.policies.tree_search import actions, plan, simulator  # noqa: E402
from app.policies.tree_search.scenario import Scenario  # noqa: E402


def make_scenario(seed=7, agents=3, size=30, cities=2, line_length=2):
    env = build_demo_env(
        seed=seed, width=size, height=size, number_of_agents=agents,
        max_num_cities=cities, line_length=line_length,
    )
    return Scenario.build(env)


@pytest.fixture(scope="module")
def scenario():
    return make_scenario()


def play(scenario, choose=lambda options: options[0]):
    """Run a whole scenario, picking with `choose` at every branch.

    Returns the final state and the branch decisions taken, which is what
    a replay needs — the forced moves in between are not decisions and are
    recovered by replaying the same machinery.
    """
    state = actions.advance_to_choice(scenario, simulator.initial_state(scenario))
    taken = []
    guard = 0
    while not simulator.is_terminal(scenario, state) and guard < 500:
        handles = simulator.deciding(scenario, state)
        options = actions.joint_actions(scenario, state, handles)
        if not options:
            break
        chosen = choose(options)
        taken.append(chosen)
        state = actions.apply(scenario, state, chosen)
        guard += 1
    return state, taken


# --------------------------------------------------------------- movement

def test_a_train_occupies_one_cell_and_moves_one_cell_per_step(scenario):
    state = actions.advance_to_choice(
        scenario, simulator.initial_state(scenario))
    moving = [t for t in state.trains if t.edge is not None]
    if not moving:
        pytest.skip("no train is mid-edge at the first decision")
    before = moving[0]
    after = simulator.step(scenario, state).train(before.handle)
    assert after.index in (before.index, before.index + 1)


def test_two_trains_never_stand_on_the_same_cell(scenario):
    state = actions.advance_to_choice(
        scenario, simulator.initial_state(scenario))
    for _ in range(60):
        occupied = [
            t.cell for t in state.trains if t.departed and not t.done
        ]
        assert len(occupied) == len(set(occupied)), occupied
        if simulator.is_terminal(scenario, state):
            break
        handles = simulator.deciding(scenario, state)
        if handles:
            options = actions.joint_actions(scenario, state, handles)
            state = simulator.apply_decisions(
                scenario, state, dict(options[0]))
        state = simulator.step(scenario, state)


def test_the_naive_policy_gets_every_train_home_on_an_easy_network(scenario):
    """Always take the cheapest way onward, never hold. On a network with
    room this has to work — if it does not, the movement rules are wrong,
    not the search."""
    final, _ = play(scenario)
    outcome = simulator.outcome(scenario, final)
    assert outcome.all_arrived, outcome.to_dict()
    assert outcome.total_delay == 0


def test_a_stranded_train_is_charged_against_the_end_of_the_episode():
    """Gridlock must not look cheap. A run that seizes up early strands
    its trains while none of them is late *yet*; charging that against the
    step the run stopped at would make an early deadlock score better than
    a small delay."""
    scenario = make_scenario(seed=5, agents=8, size=25)
    stuck = simulator.WorldState(
        step=3,
        trains=tuple(scenario.trains and [
            simulator.TrainState(
                handle=data.handle, cell=data.origin,
                heading=data.initial_direction, departed=True,
            )
            for data in scenario.trains
        ]),
        stuck_for=simulator.STUCK_STEPS,
    )
    outcome = simulator.outcome(scenario, stuck)
    assert outcome.deadlocked
    assert outcome.arrived_fraction == 0.0
    assert outcome.total_delay > 0, "a gridlocked run must cost something"


# ---------------------------------------------------------------- actions

def test_holding_is_offered_only_where_it_achieves_something(scenario):
    """A train may be held at a platform or in front of a merge, where
    standing still lets another train past. In front of a split it may
    only be steered: there is no other branch to let through."""
    state = actions.advance_to_choice(
        scenario, simulator.initial_state(scenario))
    seen_any = False
    for _ in range(40):
        for handle in simulator.deciding(scenario, state):
            train = state.train(handle)
            options = actions.options_for(scenario, state, handle)
            waits = [o for o in options if o.is_wait]
            routes = [o for o in options if not o.is_wait]
            assert routes, "a deciding train always has somewhere to go"
            if waits:
                seen_any = True
                assert scenario.can_hold(train.cell, train.heading)
            elif train.underway:
                assert not scenario.can_hold(train.cell, train.heading)
        if simulator.is_terminal(scenario, state):
            break
        handles = simulator.deciding(scenario, state)
        options = actions.joint_actions(scenario, state, handles)
        if not options:
            break
        state = actions.apply(scenario, state, options[0])
    assert seen_any, "this scenario never offered a hold — nothing was tested"


def test_the_first_option_is_the_cheapest_way_onward_without_holding(scenario):
    state = actions.advance_to_choice(
        scenario, simulator.initial_state(scenario))
    for handle in simulator.deciding(scenario, state):
        first = actions.options_for(scenario, state, handle)[0]
        assert not first.is_wait


def test_a_train_at_its_origin_is_not_asked_whether_to_wait(scenario):
    """Departures are the timetable's business, not a decision — a train
    at its origin has not started yet, so holding it is not on offer."""
    state = simulator.initial_state(scenario)
    state = simulator.run(scenario, state)
    for handle in simulator.deciding(scenario, state):
        if state.train(handle).underway:
            continue
        assert not any(
            option.is_wait
            for option in actions.options_for(scenario, state, handle)
        )


def test_joint_actions_are_the_product_of_the_deciding_trains(scenario):
    state = actions.advance_to_choice(
        scenario, simulator.initial_state(scenario))
    handles = simulator.deciding(scenario, state)
    expected = 1
    for handle in handles:
        expected *= len(actions.options_for(scenario, state, handle))
    combos = actions.joint_actions(scenario, state, handles, max_children=10_000)
    assert len(combos) == expected
    assert all(len(combo) == len(handles) for combo in combos)


def test_the_cap_drops_long_holds_and_never_a_direction():
    """A hold is only postponed by being dropped — the train re-decides at
    the same node. A direction would be gone from the tree for good."""
    scenario = make_scenario(seed=5, agents=8, size=25)
    state = actions.advance_to_choice(
        scenario, simulator.initial_state(scenario))
    def directions(combos):
        """Per train, the branches still on offer anywhere in the set."""
        offered: dict = {}
        for combo in combos:
            for handle, decision in combo:
                if not decision.is_wait:
                    offered.setdefault(handle, set()).add(decision.edge.to_cell)
        return offered

    trimmed_somewhere = False
    for _ in range(30):
        if simulator.is_terminal(scenario, state):
            break
        handles = simulator.deciding(scenario, state)
        uncapped = actions.joint_actions(
            scenario, state, handles, max_children=10_000)
        capped = actions.joint_actions(scenario, state, handles, max_children=4)
        if len(capped) < len(uncapped):
            trimmed_somewhere = True
            # Everything dropped was a hold: every train's directions are
            # all still on offer.
            assert directions(capped) == directions(uncapped)
            # And the holds that went are the long ones.
            kept = {d.wait for combo in capped for _, d in combo if d.is_wait}
            dropped = {
                d.wait for combo in uncapped for _, d in combo if d.is_wait
            } - kept
            assert not kept or not dropped or min(dropped) >= max(kept)
        state = actions.apply(scenario, state, uncapped[0])
    assert trimmed_somewhere, "the cap never bound — nothing was tested"


def test_forced_decisions_never_become_branches(scenario):
    """A train rolling through a node with one way onward decides nothing.
    Such states are executed while the child is built, so every state the
    search is handed is a point where something is actually chosen."""
    state = actions.advance_to_choice(
        scenario, simulator.initial_state(scenario))
    for _ in range(40):
        if simulator.is_terminal(scenario, state):
            break
        handles = simulator.deciding(scenario, state)
        options = actions.joint_actions(scenario, state, handles)
        assert len(options) != 1, "a forced decision was left as a branch"
        state = actions.apply(scenario, state, options[0])


# ------------------------------------------------- the model vs. Flatland

def test_a_plan_that_works_in_the_model_works_in_flatland():
    """The equivalence the whole design rests on. The simulator is not
    Flatland; a plan it approves has to survive the real environment."""
    checked = 0
    for seed in (7, 11, 13):
        scenario = make_scenario(seed=seed, agents=4, size=30)
        final, taken = play(scenario)
        modelled = simulator.outcome(scenario, final)
        if not modelled.all_arrived:
            continue
        checked += 1

        replayed = plan.replay(
            scenario, simulator.initial_state(scenario), taken)
        assert replayed.outcome.all_arrived, (
            f"seed {seed}: the replay disagreed with the run it repeats")

        from app.policies.goal_based_policies.rollout import run_schedules

        fresh = build_demo_env(
            seed=seed, width=30, height=30, number_of_agents=4,
            max_num_cities=2, line_length=2,
        )
        result = run_schedules(
            fresh, build_decision_point_graph(fresh), replayed.schedules)
        assert result.all_arrived, (
            f"seed {seed}: the model got every train home, Flatland did not")
        assert result.total_delay == modelled.total_delay
        # One step of slack: Flatland spends a step putting a train on the
        # map that the model counts as the departure itself.
        assert abs(result.steps - modelled.steps) <= 1
    assert checked, "no scenario got far enough to compare the two"
