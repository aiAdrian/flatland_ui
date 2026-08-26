"""The Director's ensemble scorer: three utilities, one weighted number."""
import json
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.policies.goal_based_policies.ensemble import (  # noqa: E402
    ARRIVAL_BLEND,
    BUCKET_UTILITIES,
    DirectorWeights,
    connection_utility,
    punctuality_utility,
    weighted_utility,
)


def test_weights_must_be_non_negative_and_not_all_zero():
    with pytest.raises(ValueError, match="non-negative"):
        DirectorWeights(punctuality=-0.1)
    with pytest.raises(ValueError, match="positive"):
        DirectorWeights(punctuality=0, connections=0, stability=0)


def test_weights_normalise_to_a_convex_combination():
    """The UI can expose three independent sliders; scoring re-scales, so
    (2, 1, 1) and (0.5, 0.25, 0.25) mean the same preference."""
    assert sum(DirectorWeights().normalized()) == pytest.approx(1.0)
    doubled = DirectorWeights(2.0, 1.0, 1.0).normalized()
    halved = DirectorWeights(0.5, 0.25, 0.25).normalized()
    assert doubled == pytest.approx(halved)
    assert doubled[0] == pytest.approx(0.5)


def test_punctuality_utility_spans_zero_to_one():
    best = [0.0] * len(BUCKET_UTILITIES)
    best[0] = 1.0
    worst = [0.0] * len(BUCKET_UTILITIES)
    worst[-1] = 1.0
    assert punctuality_utility(1.0, best) == pytest.approx(1.0)
    assert punctuality_utility(0.0, worst) == pytest.approx(0.0)


def test_punctuality_utility_rewards_better_buckets_and_arrivals():
    mild = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]     # 5-14 minutes
    severe = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]   # 60+
    assert punctuality_utility(0.5, mild) > punctuality_utility(0.5, severe)
    assert punctuality_utility(0.9, mild) > punctuality_utility(0.1, mild)
    # The blend keeps both terms visible: certain arrival with the worst
    # delay still scores exactly the arrival share.
    assert punctuality_utility(1.0, severe) == pytest.approx(ARRIVAL_BLEND)


def test_connection_utility_lets_one_doomed_transfer_matter():
    """The round-1 sweep showed a saturating mean cannot steer: nine
    robust transfers averaged away the broken tenth. The geometric mean
    must keep that tenth visible, and must reward rescuing it more than
    polishing an already-safe transfer by the same amount."""
    robust = [0.99] * 9
    assert connection_utility(robust + [0.5]) < 0.94
    rescued = connection_utility(robust + [0.7]) - connection_utility(
        robust + [0.5])
    polished = connection_utility([0.99] * 8 + [0.999, 0.5]) - (
        connection_utility(robust + [0.5]))
    assert rescued > 10 * abs(polished)


def test_connection_utility_edges():
    assert connection_utility([]) == 1.0  # nothing to keep, nothing broken
    assert connection_utility([1.0, 1.0]) == pytest.approx(1.0)
    # A hopeless transfer scores near zero but never erases the rest.
    assert 0.0 < connection_utility([0.0, 1.0]) < 0.02


def test_corner_weights_hand_the_decision_to_one_axis():
    """With everything on one slider, the weighted utility *is* that
    axis — the Director's 'delay matters most' promise, literally."""
    utilities = (0.9, 0.2, 0.4)
    only_punct = DirectorWeights(1, 0, 0)
    only_safety = DirectorWeights(0, 0, 1)
    assert weighted_utility(*utilities, only_punct) == pytest.approx(0.9)
    assert weighted_utility(*utilities, only_safety) == pytest.approx(0.4)
    balanced = weighted_utility(*utilities, DirectorWeights())
    assert balanced == pytest.approx((0.9 + 0.2 + 0.4) / 3)


@pytest.mark.integration
def test_candidates_of_a_real_scenario_score_end_to_end():
    """Full path: context built once, two candidate plans scored by both
    models plus the safety measure, batching must not change results, and
    the breakdown must serialize — it is the HMI explanation payload."""
    import torch

    from app.policies.goal_based_policies.connection_model import (
        ConnectionTransformer,
    )
    from app.policies.goal_based_policies.dataset import (
        Layout, build_layout_env, plan_all_lines,
    )
    from app.policies.goal_based_policies.ensemble import (
        ScenarioContext, score_candidates,
    )
    from app.policies.goal_based_policies.evaluator import ScheduleEvaluator
    from app.policies.goal_based_policies.infrastructure_graph import (
        build_decision_point_graph,
    )
    from app.policies.goal_based_policies.schedule import (
        plan_avoiding_overlaps,
    )

    env = build_layout_env(Layout(index=0, seed=2001, size=30, cities=2), 4)
    graph = build_decision_point_graph(env)
    base = plan_all_lines(env, graph)
    assert base is not None
    candidates = [
        base,
        plan_avoiding_overlaps(env, graph, base, safety=1, max_total_wait=10),
    ]

    torch.manual_seed(0)
    evaluator = ScheduleEvaluator(
        hidden=16, rounds=1, trunk_layers=1, sequence_layers=1)
    connection_model = ConnectionTransformer(
        hidden=16, rounds=1, layers=1, heads=2, dropout=0.0)

    context = ScenarioContext.build(env, graph)
    weights = DirectorWeights(2.0, 1.0, 1.0)
    scores = score_candidates(
        context, candidates, weights, evaluator, connection_model)

    assert len(scores) == len(candidates)
    for score in scores:
        for value in (score.punctuality, score.connections,
                      score.stability, score.weighted):
            assert 0.0 <= value <= 1.0
        assert score.weighted == pytest.approx(weighted_utility(
            score.punctuality, score.connections, score.stability, weights))
        # Stability is the computed measure, verbatim.
        assert score.stability == pytest.approx(score.safety_report.safety)
        payload = json.loads(json.dumps(score.breakdown))
        assert payload["utilities"]["punctuality"] == pytest.approx(
            score.punctuality)
        assert sum(payload["weights"].values()) == pytest.approx(1.0)
        assert len(payload["connection_probabilities"]) == len(
            context.connections)

    # Batch size must be an implementation detail, not a result.
    one_by_one = score_candidates(
        context, candidates, weights, evaluator, connection_model,
        batch_size=1)
    for batched, single in zip(scores, one_by_one):
        assert batched.weighted == pytest.approx(single.weighted, abs=1e-5)
        assert batched.punctuality == pytest.approx(
            single.punctuality, abs=1e-5)
        assert batched.connections == pytest.approx(
            single.connections, abs=1e-5)

    # Corner weights collapse the ranking onto one axis, per candidate.
    stability_only = score_candidates(
        context, candidates, DirectorWeights(0, 0, 1),
        evaluator, connection_model)
    for score in stability_only:
        assert score.weighted == pytest.approx(score.stability)
