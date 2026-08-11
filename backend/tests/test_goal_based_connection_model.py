"""Per-connection transformer: tokens, masking, and training."""
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

torch = pytest.importorskip("torch")

from app.policies.goal_based_policies.connection_model import (  # noqa: E402
    ConnectionTransformer,
)
from app.policies.goal_based_policies.dataset import (  # noqa: E402
    CONNECTION_FEATURES,
    EDGE_FEATURES,
    MAX_CONNECTIONS,
    MAX_EDGES,
    MAX_NODES,
    MAX_SCHEDULE_NODES,
    MAX_TRAINS,
    NODE_FEATURES,
    STOP_FLAGS,
    TRAIN_SCALARS,
    Sample,
    generate_samples,
)
from app.policies.goal_based_policies.train_connection_model import (  # noqa: E402
    _roc_auc,
    _tensors,
    evaluate,
    train_connection_model,
)


def _batch(pairs, trains=4, seed=7, batch=1):
    """A scenario whose connections differ only in which trains they join."""
    torch.manual_seed(seed)
    n = len(pairs)
    fields = [
        torch.rand(batch, MAX_NODES, NODE_FEATURES), torch.ones(batch, MAX_NODES),
        torch.zeros(batch, MAX_EDGES, 2, dtype=torch.long),
        torch.rand(batch, MAX_EDGES, EDGE_FEATURES), torch.ones(batch, MAX_EDGES),
        torch.zeros(batch, MAX_TRAINS, MAX_SCHEDULE_NODES, dtype=torch.long),
        torch.zeros(batch, MAX_TRAINS, MAX_SCHEDULE_NODES),
        torch.zeros(batch, MAX_TRAINS, MAX_SCHEDULE_NODES),
        torch.zeros(batch, MAX_TRAINS, MAX_SCHEDULE_NODES, STOP_FLAGS),
        torch.zeros(batch, MAX_TRAINS, TRAIN_SCALARS), torch.zeros(batch, MAX_TRAINS),
        torch.zeros(batch, MAX_CONNECTIONS, CONNECTION_FEATURES),
        torch.zeros(batch, MAX_CONNECTIONS, 3, dtype=torch.long),
        torch.zeros(batch, MAX_CONNECTIONS),
    ]
    fields[7][:, :trains, :6] = 1.0
    fields[10][:, :trains] = 1.0
    for t in range(trains):
        fields[9][:, t] = torch.tensor([0.1 * t, 0.5 + 0.1 * t, 0.3, 0.2, 0.05 * t])
    fields[11][:, :n] = 0.3          # identical features for every connection
    fields[12][:, :n] = torch.tensor(pairs, dtype=torch.long)
    fields[13][:, :n] = 1.0
    return fields


# ── the property the pooled model could not have ─────────────────────

def test_identical_features_differ_by_which_trains_they_join():
    """The whole reason for this model: two transfers with the same numbers
    but different trains must not get the same answer. The delay
    evaluator's masked mean/max over trains makes that impossible."""
    model = ConnectionTransformer(dropout=0.0).eval()
    logits = model(*_batch([[0, 1, 5], [0, 2, 5], [1, 2, 5]]))[0, :3]
    assert len({round(x.item(), 6) for x in logits}) == 3, (
        f"identical features gave identical logits: {logits.tolist()}"
    )

    moved = model(*_batch([[2, 3, 5], [0, 2, 5], [1, 2, 5]]))[0, :3]
    assert not torch.allclose(logits[0], moved[0], atol=1e-6)
    # The connections that did not move are still affected, because
    # attention is global — that is intended, not a leak.
    assert moved.shape == logits.shape


def test_station_identity_matters():
    model = ConnectionTransformer(dropout=0.0).eval()
    here = model(*_batch([[0, 1, 5]]))[0, 0]
    there = model(*_batch([[0, 1, 9]]))[0, 0]
    assert not torch.allclose(here, there, atol=1e-6)


# ── masking ──────────────────────────────────────────────────────────

def test_padding_cannot_reach_real_connections():
    """Padded rows carry arbitrary leftovers; they must be invisible."""
    model = ConnectionTransformer(dropout=0.0).eval()
    pairs = [[0, 1, 5], [0, 2, 5], [1, 2, 5]]
    clean = model(*_batch(pairs))[0, :3]

    dirty = _batch(pairs)
    dirty[11][0, 3:40] = 9.9
    dirty[12][0, 3:40] = torch.randint(0, MAX_TRAINS, (37, 3))
    assert torch.allclose(clean, model(*dirty)[0, :3], atol=1e-6)


def test_predict_returns_probabilities_and_a_masked_ratio():
    model = ConnectionTransformer(dropout=0.0).eval()
    fields = _batch([[0, 1, 5], [0, 2, 5]])
    out = model.predict(*fields)

    probability = out["connection_probability"]
    assert probability.shape == (1, MAX_CONNECTIONS)
    assert ((probability >= 0) & (probability <= 1)).all()
    # Masked-out rows contribute nothing.
    assert probability[0, 2:].sum() == 0
    assert out["kept_ratio"].item() == pytest.approx(
        probability[0, :2].mean().item(), abs=1e-6
    )

    # No connections at all scores 1.0: nothing was broken.
    empty = _batch([[0, 1, 5]])
    empty[13][:] = 0.0
    assert model.predict(*empty)["kept_ratio"].item() == pytest.approx(1.0)


def test_save_and_load_round_trip(tmp_path):
    model = ConnectionTransformer(dropout=0.1)
    fields = _batch([[0, 1, 5], [1, 2, 5]])
    before = model.predict(*fields)["connection_probability"]

    path = tmp_path / "connection.pt"
    model.save(path)
    after = ConnectionTransformer.load(path).predict(*fields)["connection_probability"]
    assert torch.allclose(before, after, atol=1e-6)


# ── scoring ──────────────────────────────────────────────────────────

def test_auc_matches_the_brute_force_definition():
    """AUC drives the stopping decision, so it is checked against the
    pairwise definition rather than trusted."""
    rng = np.random.default_rng(0)
    for round_to in (None, 1):
        for _ in range(3):
            size = int(rng.integers(20, 120))
            labels = (rng.random(size) > 0.6).astype(float)
            scores = rng.random(size) * 0.5 + labels * rng.random(size) * 0.5
            if round_to is not None:
                scores = np.round(scores, round_to)   # force ties
            positive, negative = scores[labels > 0], scores[labels == 0]
            if not len(positive) or not len(negative):
                continue
            brute = np.mean([
                (a > b) + 0.5 * (a == b) for a in positive for b in negative
            ])
            assert _roc_auc(scores, labels) == pytest.approx(brute, abs=1e-9)

    assert _roc_auc(np.array([.1, .2, .8, .9]), np.array([0., 0, 1, 1])) == 1.0
    assert _roc_auc(np.array([.9, .8, .2, .1]), np.array([0., 0, 1, 1])) == 0.0
    # Degenerate labels cannot be ranked; chance is the honest answer.
    assert _roc_auc(np.array([.1, .2]), np.array([1., 1])) == 0.5


@pytest.mark.integration
def test_evaluate_reports_the_metric_schema_regardless_of_chunk_size():
    """`evaluate` reports the fixed metric schema, bounded, and chunking
    is an implementation detail, not a scoring change. (Padded rows are
    invisible at the model level — see
    test_padding_cannot_reach_real_connections.)"""
    samples = generate_samples(10, seed=31)
    batch = _tensors(samples)
    model = ConnectionTransformer(dropout=0.0)
    metrics = evaluate(model, batch)
    assert set(metrics) == {
        "connection_accuracy", "connection_auc",
        "connection_brier", "scenario_ratio_mae",
    }
    assert 0.0 <= metrics["connection_accuracy"] <= 1.0
    assert 0.0 <= metrics["connection_auc"] <= 1.0

    # Chunking is an implementation detail, not a scoring change.
    assert evaluate(model, batch, chunk_size=2) == pytest.approx(
        evaluate(model, batch, chunk_size=10**9), abs=1e-6
    )


def _unlabelled_sample() -> Sample:
    """A minimal encoded scenario whose connection block carries no labels,
    like a cache built before per-connection labels existed."""
    return Sample(
        graph_nodes=np.zeros((MAX_NODES, NODE_FEATURES), dtype=np.float32),
        graph_node_mask=np.zeros((MAX_NODES,), dtype=np.float32),
        edge_index=np.zeros((MAX_EDGES, 2), dtype=np.int64),
        edge_features=np.zeros((MAX_EDGES, EDGE_FEATURES), dtype=np.float32),
        edge_mask=np.zeros((MAX_EDGES,), dtype=np.float32),
        schedule_nodes=np.zeros((MAX_TRAINS, MAX_SCHEDULE_NODES), dtype=np.int64),
        waits=np.zeros((MAX_TRAINS, MAX_SCHEDULE_NODES), dtype=np.float32),
        node_mask=np.zeros((MAX_TRAINS, MAX_SCHEDULE_NODES), dtype=np.float32),
        stop_flags=np.zeros(
            (MAX_TRAINS, MAX_SCHEDULE_NODES, STOP_FLAGS), dtype=np.float32),
        train_scalars=np.zeros((MAX_TRAINS, TRAIN_SCALARS), dtype=np.float32),
        train_mask=np.zeros((MAX_TRAINS,), dtype=np.float32),
        layout=0,
        all_arrived=1.0,
        bucket=0,
        total_delay=0,
        connection_features=np.zeros(
            (MAX_CONNECTIONS, CONNECTION_FEATURES), dtype=np.float32),
        connection_index=np.zeros((MAX_CONNECTIONS, 3), dtype=np.int64),
        connection_kept=np.zeros((MAX_CONNECTIONS,), dtype=np.float32),
        connection_mask=np.zeros((MAX_CONNECTIONS,), dtype=np.float32),
    )


def test_refuses_a_dataset_without_connection_labels():
    """A cache built before per-connection labels would silently train on
    nothing, so it has to fail loudly."""
    samples = [_unlabelled_sample() for _ in range(10)]
    with pytest.raises(ValueError, match="no connections"):
        train_connection_model(samples=samples, epochs=1, seed=33, verbose=False)


@pytest.mark.integration
def test_training_beats_predicting_the_base_rate():
    """The point of the model: rank which transfers are at risk. AUC over
    0.5 is what says it learned something a constant cannot."""
    samples = generate_samples(150, seed=21)
    model, report = train_connection_model(
        samples=samples, epochs=40, seed=21, verbose=False
    )
    assert report.train_connections > 200
    assert report.history[-1]["loss"] < report.history[0]["loss"]

    assert report.baseline["connection_auc"] == 0.5
    assert report.final["connection_auc"] > 0.7, (
        f"AUC {report.final['connection_auc']:.3f} is barely better than chance"
    )
    assert report.final["connection_brier"] < report.baseline["connection_brier"]
    assert report.final["scenario_ratio_mae"] < report.baseline["scenario_ratio_mae"]


@pytest.mark.integration
def test_block_training_resumes_and_keeps_the_best(tmp_path):
    """Blocks continue while validation improves, the checkpoint carries
    optimiser and scheduler so a resume picks up rather than restarting,
    and the file on disk is always the best model seen."""
    from app.policies.goal_based_policies.train_connection_model import (
        load_checkpoint,
        train_until_no_improvement,
        validation_score,
    )

    samples = generate_samples(120, seed=41)
    checkpoint = str(tmp_path / "connection.ckpt")
    _, report = train_until_no_improvement(
        samples=samples, checkpoint_path=checkpoint, block_epochs=3,
        max_blocks=3, seed=41, verbose=False,
    )
    _, payload = load_checkpoint(checkpoint)
    assert payload["epochs_done"] >= 3
    assert payload["optimiser"]["state"], "optimiser state must be saved"
    assert payload["scheduler"] is not None, "scheduler state must be saved"
    assert validation_score(report.final) == pytest.approx(
        payload["best_score"], abs=1e-6
    )

    first = payload["epochs_done"]
    train_until_no_improvement(
        samples=samples, checkpoint_path=checkpoint, block_epochs=3,
        max_blocks=3, seed=41, verbose=False,
    )
    _, resumed = load_checkpoint(checkpoint)
    assert resumed["epochs_done"] >= first
    assert resumed["best_score"] >= payload["best_score"]

    # A different dataset would compare scores across different validation
    # sets, so it must fail loudly rather than silently continue.
    with pytest.raises(ValueError, match="different data"):
        train_until_no_improvement(
            samples=generate_samples(60, seed=42), checkpoint_path=checkpoint,
            block_epochs=2, max_blocks=1, seed=41, verbose=False,
        )
