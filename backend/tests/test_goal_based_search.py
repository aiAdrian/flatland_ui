"""The greedy Director search: determinism, trace, portfolio guarantee."""
import json
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.policies.goal_based_policies.dataset import (  # noqa: E402
    Layout,
    build_layout_env,
    plan_all_lines,
)
from app.policies.goal_based_policies.ensemble import (  # noqa: E402
    DirectorWeights,
    ScenarioContext,
)
from app.policies.goal_based_policies.infrastructure_graph import (  # noqa: E402
    build_decision_point_graph,
)
from app.policies.goal_based_policies.search import (  # noqa: E402
    SearchLimits,
    beam_search,
    director_plan,
    greedy_search,
    mcts_search,
    verify_plan,
)


@pytest.fixture(scope="module")
def scenario():
    env = build_layout_env(Layout(index=0, seed=2001, size=30, cities=2), 4)
    graph = build_decision_point_graph(env)
    assert plan_all_lines(env, graph) is not None
    return env, graph, ScenarioContext.build(env, graph)


@pytest.fixture(scope="module")
def models():
    import torch

    from app.policies.goal_based_policies.connection_model import (
        ConnectionTransformer,
    )
    from app.policies.goal_based_policies.evaluator import ScheduleEvaluator

    torch.manual_seed(0)
    evaluator = ScheduleEvaluator(
        hidden=16, rounds=1, trunk_layers=1, sequence_layers=1)
    connection_model = ConnectionTransformer(
        hidden=16, rounds=1, layers=1, heads=2, dropout=0.0)
    return evaluator, connection_model


def test_the_search_is_deterministic(scenario, models):
    """Same scenario, same models, same weights — the trace and the plan
    must repeat exactly, or no experiment downstream is reproducible."""
    env, graph, context = scenario
    weights = DirectorWeights(2.0, 1.0, 1.0)
    first = greedy_search(env, graph, context, weights, *models)
    second = greedy_search(env, graph, context, weights, *models)
    assert json.dumps(first.trace, sort_keys=True) == json.dumps(
        second.trace, sort_keys=True)
    assert [s.to_flat_list() for s in first.schedules] == [
        s.to_flat_list() for s in second.schedules]


def test_the_search_finishes_every_train_and_explains_itself(scenario, models):
    env, graph, context = scenario
    outcome = greedy_search(
        env, graph, context, DirectorWeights(), *models)
    assert outcome.stuck == ()
    assert {s.handle for s in outcome.schedules} == {0, 1, 2, 3}
    assert all(len(s.entries) >= 2 for s in outcome.schedules)
    assert outcome.decisions == len(outcome.trace) > 0

    for entry in outcome.trace:
        assert entry["chosen"] in range(len(entry["options"]))
        chosen = entry["options"][entry["chosen"]]
        assert chosen["considered"]
        # The chosen option is the best among the considered ones.
        best = max(
            (o for o in entry["options"] if o["considered"]),
            key=lambda o: o["weighted"],
        )
        assert chosen["weighted"] == pytest.approx(best["weighted"])
    json.dumps(outcome.trace)


def test_decision_budget_caps_the_walk(scenario, models):
    env, graph, context = scenario
    capped = greedy_search(
        env, graph, context, DirectorWeights(), *models,
        limits=SearchLimits(max_decisions=2))
    assert capped.decisions == 2
    assert len(capped.schedules) == 4  # completions still cover everyone


def test_the_director_never_returns_worse_than_the_baselines(scenario, models):
    """The portfolio guarantee, per corner weight: whatever the search
    produced, the committed plan's weighted score is at least the score
    of both baseline planners — by construction, so a regression here
    means the portfolio pick broke."""
    env, graph, context = scenario
    for weights in (
        DirectorWeights(1, 0, 0),
        DirectorWeights(0, 1, 0),
        DirectorWeights(0, 0, 1),
    ):
        plan = director_plan(
            env, graph, weights, *models, context=context)
        assert plan.source in plan.considered
        assert plan.score.weighted == pytest.approx(
            max(plan.considered.values()))
        assert set(plan.considered) == {"search", "lines", "avoidance"}
        payload = json.loads(json.dumps(plan.to_dict()))
        assert payload["source"] == plan.source
        assert set(payload["schedules"]) == {"0", "1", "2", "3"} or set(
            payload["schedules"]) == {0, 1, 2, 3}


def test_beam_search_is_deterministic_and_never_below_its_own_pool(scenario, models):
    """Repeat runs must match exactly, every train must be planned, and
    widening the beam must not *lower* the search's own objective — a
    wider beam sees a superset of one-step choices at every step."""
    env, graph, context = scenario
    weights = DirectorWeights(1, 1, 1)
    first = beam_search(env, graph, context, weights, *models,
                        limits=SearchLimits(beam_width=3))
    again = beam_search(env, graph, context, weights, *models,
                        limits=SearchLimits(beam_width=3))
    assert json.dumps(first.trace, sort_keys=True) == json.dumps(
        again.trace, sort_keys=True)
    assert {s.handle for s in first.schedules} == {0, 1, 2, 3}
    assert first.trace  # step-level records exist
    json.dumps(first.trace)

    narrow = beam_search(env, graph, context, weights, *models,
                         limits=SearchLimits(beam_width=1))
    assert first.score.weighted >= narrow.score.weighted - 1e-9


@pytest.mark.integration
def test_mcts_search_is_deterministic_and_reports_visits(scenario, models):
    """No randomness anywhere: repeat runs must be identical. Every root
    decision's trace carries visit counts summing to the simulation
    budget — the training signal for the future policy prior."""
    env, graph, context = scenario
    weights = DirectorWeights(1, 1, 1)
    limits = SearchLimits(simulations=8)
    first = mcts_search(env, graph, context, weights, *models, limits=limits)
    again = mcts_search(env, graph, context, weights, *models, limits=limits)
    assert json.dumps(first.trace, sort_keys=True) == json.dumps(
        again.trace, sort_keys=True)
    assert {s.handle for s in first.schedules} == {0, 1, 2, 3}
    for entry in first.trace:
        visits = sum(o["visits"] for o in entry["options"])
        assert visits == limits.simulations
        chosen = entry["options"][entry["chosen"]]
        assert chosen["considered"]
        assert chosen["visits"] == max(o["visits"] for o in entry["options"])
    json.dumps(first.trace)


@pytest.mark.integration
def test_mcts_accepts_a_learned_prior_and_stays_deterministic(
        scenario, models):
    """The prior redistributes exploration; it must not break determinism
    or the visit accounting, and the result is still a complete plan."""
    import torch

    from app.policies.goal_based_policies.priors import BranchPrior

    env, graph, context = scenario
    torch.manual_seed(3)
    prior = BranchPrior()
    limits = SearchLimits(simulations=6)
    first = mcts_search(env, graph, context, DirectorWeights(), *models,
                        limits=limits, prior=prior)
    again = mcts_search(env, graph, context, DirectorWeights(), *models,
                        limits=limits, prior=prior)
    assert json.dumps(first.trace, sort_keys=True) == json.dumps(
        again.trace, sort_keys=True)
    assert {s.handle for s in first.schedules} == {0, 1, 2, 3}
    for entry in first.trace:
        assert sum(o["visits"] for o in entry["options"]) == limits.simulations


def test_director_plan_dispatches_strategies_and_keeps_the_guarantee(
        scenario, models):
    env, graph, context = scenario
    weights = DirectorWeights(1, 1, 1)
    with pytest.raises(ValueError, match="unknown strategy"):
        director_plan(env, graph, weights, *models, context=context,
                      strategy="beem")
    for strategy in ("beam", "mcts"):
        plan = director_plan(
            env, graph, weights, *models, context=context,
            strategy=strategy,
            limits=SearchLimits(beam_width=2, simulations=6),
        )
        assert plan.score.weighted == pytest.approx(
            max(plan.considered.values()))


def test_verification_returns_ground_truth_for_the_plan(models):
    """Rollout on a fresh env: the verified numbers exist and are typed;
    their agreement with predictions is the offline sweep's territory."""
    from app.policies.goal_based_policies.stations import resolve_stations

    env = build_layout_env(Layout(index=0, seed=2001, size=30, cities=2), 4)
    graph = build_decision_point_graph(env)
    context = ScenarioContext.build(env, graph)
    plan = director_plan(
        env, graph, DirectorWeights(), *models, context=context)

    fresh = build_layout_env(Layout(index=0, seed=2001, size=30, cities=2), 4)
    fresh_graph = build_decision_point_graph(fresh)
    verified = verify_plan(
        fresh, fresh_graph, resolve_stations(fresh), plan.schedules)
    assert set(verified) == {
        "total_delay", "all_arrived", "bucket", "connections_total",
        "connections_kept", "kept_ratio", "safety", "steps",
    }
    assert verified["total_delay"] >= 0
    assert 0.0 <= verified["kept_ratio"] <= 1.0
    assert 0.0 <= verified["safety"] <= 1.0
