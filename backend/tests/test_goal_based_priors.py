"""The branch prior: learn where the ensemble's choice usually lands."""
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.policies.goal_based_policies.priors import (  # noqa: E402
    BranchPrior,
    load_decisions,
    option_features,
    train_prior,
)


def _decision(chosen: int, n_options: int = 6, n_waits: int = 3):
    """A synthetic decision whose options are wait-major, like the real
    generator: (wait 0, routes 0..1), (wait 1, routes 0..1), ..."""
    routes = n_options // n_waits
    rows = np.array([
        option_features(index // routes, index % routes, True, n_options)
        for index in range(n_options)
    ], dtype=np.float32)
    return rows, chosen


def test_a_learnable_pattern_beats_the_uniform_baseline():
    """If the ensemble always picks the cheapest no-hold route, the prior
    must learn that from traces alone — that is its entire job."""
    decisions = [_decision(chosen=0) for _ in range(60)]
    model, metrics = train_prior(decisions, epochs=40, seed=1)
    assert metrics["val_accuracy"] > 0.9
    assert metrics["val_accuracy"] > metrics["uniform_accuracy"] + 0.3


def test_probabilities_are_a_distribution_and_round_trip(tmp_path):
    model = BranchPrior()
    options = [{"wait": w, "clean": True} for w in (0, 0, 1, 1, 3, 3)]
    probabilities = model.probabilities(options, n_waits=3)
    assert len(probabilities) == len(options)
    assert sum(probabilities) == pytest.approx(1.0)

    path = tmp_path / "prior.pt"
    model.save(path)
    restored = BranchPrior.load(path)
    assert restored.probabilities(options, n_waits=3) == pytest.approx(
        probabilities)


def test_traces_load_only_decisions_with_a_real_choice(tmp_path):
    import json

    path = tmp_path / "traces.jsonl"
    record = {
        "trace": [
            {"chosen": 1, "options": [
                {"wait": 0, "clean": True}, {"wait": 3, "clean": False}]},
            {"chosen": 0, "options": [{"wait": 0, "clean": True}]},  # 1 opt
            {"stuck": True, "options": []},
        ],
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    decisions = load_decisions([str(path)])
    assert len(decisions) == 1
    rows, chosen = decisions[0]
    assert rows.shape == (2, 5)
    assert chosen == 1


def test_too_little_data_is_refused():
    with pytest.raises(ValueError, match="at least 10"):
        train_prior([_decision(0)])
