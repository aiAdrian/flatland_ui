"""Search-plan samples: Director plans, rollout labels, provenance."""
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.policies.goal_based_policies.search_dataset import (  # noqa: E402
    generate_search_samples_report,
)


@pytest.fixture(scope="module")
def models():
    import torch

    from app.policies.goal_based_policies.connection_model import (
        ConnectionTransformer,
    )
    from app.policies.goal_based_policies.evaluator import ScheduleEvaluator

    torch.manual_seed(0)
    return (
        ScheduleEvaluator(hidden=16, rounds=1, trunk_layers=1,
                          sequence_layers=1),
        ConnectionTransformer(hidden=16, rounds=1, layers=1, heads=2,
                              dropout=0.0),
    )


def test_unknown_weight_settings_are_refused(models):
    with pytest.raises(ValueError, match="unknown weight settings"):
        generate_search_samples_report(
            1, seed=1, evaluator=models[0], connection_model=models[1],
            weight_names=["stabilty"],
        )


@pytest.mark.integration
def test_samples_carry_provenance_and_rollout_labels(models):
    """A sample is only useful for retraining if it records which weight
    setting planned it and what the episode actually did — and it must
    survive the cache round trip like every other sample."""
    from app.policies.goal_based_policies.dataset import (
        load_samples, save_samples,
    )

    samples, skipped = generate_search_samples_report(
        2, seed=5, evaluator=models[0], connection_model=models[1],
        weight_names=["stability"],
    )
    assert len(samples) == 2
    assert all(isinstance(v, int) for v in skipped.values())
    for sample in samples:
        assert sample.source == "search:stability"
        assert sample.mix == "training"
        assert sample.all_arrived in (0.0, 1.0)
        assert 0 <= sample.bucket <= 5
        assert sample.total_delay >= 0
        assert sample.connection_mask is not None

    import tempfile
    with tempfile.TemporaryDirectory() as scratch:
        path = f"{scratch}/search.npz"
        save_samples(path, samples)
        restored = load_samples(path)
    assert [s.source for s in restored] == [s.source for s in samples]
    assert [s.bucket for s in restored] == [s.bucket for s in samples]
