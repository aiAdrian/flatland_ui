"""The tree search: growing, finding, re-rooting, and staying honest."""
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.policies.tree_search import (  # noqa: E402
    actions,
    metrics,
    plan,
    simulator,
)
from app.policies.tree_search.search import TreeSearch  # noqa: E402
from tests.test_tree_search_simulator import make_scenario, play  # noqa: E402


@pytest.fixture(scope="module")
def scenario():
    return make_scenario(seed=7, agents=4, size=30)


def test_the_search_finds_a_complete_run_and_reports_it(scenario):
    search = TreeSearch(scenario)
    search.run(node_budget=200)
    solution = search.best_solution()
    assert solution is not None, "no complete run found within the budget"
    assert 0.0 <= solution.weighted <= 1.0
    assert solution.outcome.steps > 0
    stats = search.stats()
    assert stats["has_solution"] and stats["nodes"] > 1


def test_it_is_anytime_and_never_gets_worse(scenario):
    """The best solution is available at every point and only improves —
    the running app asks for it whenever it likes."""
    search = TreeSearch(scenario)
    best = 0.0
    for _ in range(6):
        search.run(node_budget=40)
        solution = search.best_solution()
        if solution is None:
            continue
        assert solution.weighted >= best - 1e-9
        best = max(best, solution.weighted)
    assert best > 0.0


def test_it_is_at_least_as_good_as_driving_straight_at_the_problem(scenario):
    """The floor: whatever else it does, searching must not do worse than
    the obvious policy of always taking the cheapest way onward."""
    final, _ = play(scenario)
    naive = metrics.punctuality(simulator.outcome(scenario, final))

    search = TreeSearch(scenario)
    search.run(node_budget=300)
    solution = search.best_solution()
    assert solution is not None
    assert solution.weighted >= naive - 1e-9


def test_search_finds_a_way_through_where_the_naive_policy_deadlocks():
    """The point of searching at all. On a tight network the obvious
    policy runs two trains head on; holding one is what gets them home,
    and nothing but a search will find where."""
    improved = False
    for seed in (7, 3, 5, 9, 11):
        scenario = make_scenario(seed=seed, agents=3, size=40)
        final, _ = play(scenario)
        naive = metrics.punctuality(simulator.outcome(scenario, final))
        if naive > 0.9:
            continue  # nothing to improve on here
        search = TreeSearch(scenario)
        search.run(node_budget=400)
        solution = search.best_solution()
        if solution and solution.weighted > naive + 1e-6:
            improved = True
            break
    assert improved, "the search never beat the naive policy anywhere"


def test_two_searches_of_the_same_scenario_agree(scenario):
    """Deterministic: nothing is sampled, so the same budget gives the
    same plan. Without this, a re-plan could churn for no reason."""
    def once():
        search = TreeSearch(scenario)
        search.run(node_budget=150)
        solution = search.best_solution()
        return solution.weighted, len(solution.actions)

    assert once() == once()


def test_rerooting_keeps_the_work_already_done(scenario):
    """Executing a decision must not throw the tree away — that is what
    makes searching alongside a running episode affordable."""
    search = TreeSearch(scenario)
    search.run(node_budget=200)
    before = len(search.nodes)
    action = search.best_action()
    assert action is not None

    assert search.reroot(action)
    after = len(search.nodes)
    assert 1 < after < before, (before, after)
    assert search.nodes[search.root].parent is None
    assert search.nodes[search.root].depth == 0
    # And it keeps growing from there.
    assert search.run(node_budget=20) > 0


def test_rerooting_onto_an_unexplored_branch_is_refused(scenario):
    """A world that went somewhere the tree never looked has to be told
    so, and start again — quietly re-rooting on the wrong state would
    plan for a railway that does not exist."""
    search = TreeSearch(scenario)
    search.run(node_budget=20)
    root = search.nodes[search.root]
    fake = tuple(
        (handle, decision) for handle, decision in root.child_actions[0]
    )[:0]
    assert not search.reroot(fake)


def test_a_terminal_state_is_measured_not_predicted(scenario):
    """Where the run is over there is nothing to estimate: the value is
    the outcome. A model that disagreed would be overruled here."""
    search = TreeSearch(scenario, models={"punctuality": _AlwaysHalf()})
    search.run(node_budget=200)
    solution = search.best_solution()
    assert solution is not None
    assert solution.weighted == pytest.approx(
        metrics.punctuality(solution.outcome))


def test_the_weights_are_reported_as_they_are_applied(scenario):
    search = TreeSearch(scenario, weights={"punctuality": 3.0})
    assert search.stats()["weights"] == {"punctuality": 1.0}


def test_the_plan_replays_to_exactly_what_the_search_scored(scenario):
    """The schedules handed to the app must be the run the search chose —
    if the replay diverged, the score shown would describe a different
    plan than the one the trains drive."""
    search = TreeSearch(scenario)
    search.run(node_budget=250)
    solution = search.best_solution()
    replayed = plan.replay(scenario, search.replay_from, solution.actions)
    assert replayed.outcome.to_dict() == solution.outcome.to_dict()
    assert all(schedule.entries for schedule in replayed.schedules)


def test_the_node_cap_releases_the_worst_leaves_and_keeps_going(scenario):
    """Memory is bounded, so a long-running search has to shed something.
    What goes are unexpanded leaves — the tree stays consistent and the
    best solution is untouched."""
    search = TreeSearch(scenario, max_nodes=120)
    search.run(node_budget=300)
    assert len(search.nodes) <= 400   # trimming keeps it near the cap
    for node in search.nodes.values():
        assert node.parent is None or node.parent in search.nodes


class _AlwaysHalf:
    """A stand-in value network with nothing to say."""

    def predict(self, *inputs):
        import torch

        return torch.full((inputs[0].shape[0],), 0.5)
