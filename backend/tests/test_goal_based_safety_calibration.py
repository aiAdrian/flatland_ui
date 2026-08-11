"""The safety measure's malfunction-rollout validation and parameter fit."""
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.policies.goal_based_policies.safety_calibration import (  # noqa: E402
    fitted_params,
    run_study,
    spearman,
)


def test_spearman_recovers_monotone_relations_and_handles_ties():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert spearman([1, 1, 1], [1, 2, 3]) == 0.0  # no ranking information
    assert spearman([1], [1]) == 0.0
    # Ties by average rank: still positively related.
    assert spearman([1, 2, 2, 3], [1, 2, 3, 4]) > 0.9


def test_fitted_params_come_from_the_malfunction_distribution():
    params = fitted_params(10, 30)
    assert params.tau_deadlock == pytest.approx(20.0)
    assert params.window == pytest.approx(20.0)
    assert params.delta == pytest.approx(20.0)
    # Everything not tied to the disturbance scale stays at its default.
    assert params.tau_slack == pytest.approx(5.0)
    assert params.q_deadlock == pytest.approx(0.8)


@pytest.mark.integration
def test_the_study_produces_points_and_correlations():
    """One scenario, one disturbed episode — the plumbing, not the
    statistics: identical rail across nominal and disturbed builds,
    every point carries scores and damages, every correlation is a
    finite number in [-1, 1]."""
    payload = run_study(scenarios=1, episodes=1, verbose=False)
    assert len(payload["points"]) == 3  # lines / avoidance / noisy
    for point in payload["points"]:
        assert 0.0 <= point["safety"] <= 1.0
        assert point["failure_rate"] in (0.0, 1.0)
    for value in payload["correlations"].values():
        assert -1.0 <= value <= 1.0
