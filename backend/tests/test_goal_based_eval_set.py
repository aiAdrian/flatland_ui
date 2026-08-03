"""The held-out, harder-than-training evaluation set."""
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.policies.goal_based_policies.dataset import (  # noqa: E402
    EVAL_MIXES,
    TRAINING_MIX,
    Sample,
    ScenarioMix,
)
from app.policies.goal_based_policies.eval_set import (  # noqa: E402
    CAP_SKIPS,
    connection_baseline,
    describe,
    generate_eval_set,
    mixes_by_name,
    report,
)


def _sample(mix: str, kept, connections=None) -> Sample:
    """A minimal encoded scenario — enough for the grouping and summary."""
    from app.policies.goal_based_policies.dataset import (
        CONNECTION_FEATURES, EDGE_FEATURES, MAX_CONNECTIONS, MAX_EDGES,
        MAX_NODES, MAX_SCHEDULE_NODES, MAX_TRAINS, NODE_FEATURES, STOP_FLAGS,
        TRAIN_SCALARS,
    )

    count = len(kept)
    mask = np.zeros((MAX_CONNECTIONS,), dtype=np.float32)
    labels = np.zeros((MAX_CONNECTIONS,), dtype=np.float32)
    mask[:count] = 1.0
    labels[:count] = np.array(kept, dtype=np.float32)
    train_mask = np.zeros((MAX_TRAINS,), dtype=np.float32)
    train_mask[:2] = 1.0
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
        train_mask=train_mask,
        layout=0,
        all_arrived=1.0,
        bucket=0,
        total_delay=0,
        connections_total=count,
        connections_kept=int(sum(kept)),
        connection_features=np.zeros(
            (MAX_CONNECTIONS, CONNECTION_FEATURES), dtype=np.float32),
        connection_index=np.zeros((MAX_CONNECTIONS, 3), dtype=np.int64),
        connection_kept=labels,
        connection_mask=mask,
        mix=mix,
    )


def test_every_eval_mix_is_held_out_from_training():
    """The whole claim of the set is that no eval scenario sits on a network
    a model trained on. That comes from the seed ranges being disjoint, so
    it has to hold for every mix, not just the ones added first."""
    assert EVAL_MIXES
    for mix in EVAL_MIXES:
        assert not TRAINING_MIX.overlaps_seeds(mix), (
            f"eval mix '{mix.name}' can draw training layout seeds"
        )
    assert len({mix.name for mix in EVAL_MIXES}) == len(EVAL_MIXES)


def test_the_set_keeps_a_control_at_the_training_distribution():
    """Without a same-distribution control, a lower score on the hard mixes
    cannot be told apart from the model simply meeting new networks."""
    control = next(mix for mix in EVAL_MIXES if mix.name == "control")
    for field in ("sizes", "cities", "min_trains", "max_trains", "line_length"):
        assert getattr(control, field) == getattr(TRAINING_MIX, field)
    assert control.seed_range != TRAINING_MIX.seed_range


def test_mixes_are_selected_by_name_and_typos_are_refused():
    assert [m.name for m in mixes_by_name()] == [m.name for m in EVAL_MIXES]
    assert [m.name for m in mixes_by_name(["long"])] == ["long"]
    with pytest.raises(ValueError, match="unknown mix"):
        mixes_by_name(["lnog"])


def test_generation_refuses_a_mix_that_could_reuse_training_networks():
    """Silently scoring on networks the model memorised would look like
    excellent generalisation, so this fails loudly rather than warns."""
    leaky = ScenarioMix(name="leaky", seed_range=(1, 20_000_000))
    with pytest.raises(ValueError, match="overlaps the training range"):
        generate_eval_set(per_mix=1, mixes=[leaky], verbose=False)


def test_scores_are_broken_down_per_mix():
    """An aggregate would average away the whole point: the mixes turn
    different knobs, and which knob costs the model accuracy is the finding."""
    samples = (
        [_sample("control", [1, 1, 0]) for _ in range(2)]
        + [_sample("sprawl", [0, 0, 0, 1]) for _ in range(3)]
    )
    payload = report(samples)
    assert set(payload["by_mix"]) == {"control", "sprawl"}
    assert payload["by_mix"]["control"]["data"]["scenarios"] == 2
    assert payload["by_mix"]["sprawl"]["data"]["scenarios"] == 3
    assert payload["overall"]["data"]["scenarios"] == 5

    # kept_rate is over connections, not scenarios: 4 of 6 and 3 of 12.
    assert payload["by_mix"]["control"]["data"]["kept_rate"] == pytest.approx(4 / 6)
    assert payload["by_mix"]["sprawl"]["data"]["kept_rate"] == pytest.approx(3 / 12)
    assert payload["overall"]["data"]["kept_rate"] == pytest.approx(7 / 18)


def test_describe_handles_a_slice_with_nothing_in_it():
    assert describe([])["scenarios"] == 0
    assert connection_baseline([]) == {}


def test_the_accuracy_floor_is_reported_because_the_label_is_lopsided():
    """On a mix where four transfers in five break, guessing "broken" for
    everything already scores 0.8 — so a model accuracy of 0.89 has to be
    read against that floor or it reads as far better than it is."""
    samples = [_sample("long", [1, 0, 0, 0, 0]) for _ in range(4)]
    base = connection_baseline(samples)
    assert base["kept_rate"] == pytest.approx(0.2)
    assert base["majority_accuracy"] == pytest.approx(0.8)
    # AUC has no such escape: a constant predictor cannot rank at all.
    assert base["auc"] == 0.5


def test_the_ratio_floor_uses_the_rate_the_model_was_trained_on():
    """The comparison that matters is against a constant carried over from
    training, not one refitted on the eval set — refitting would hand the
    baseline information the model never had."""
    samples = [_sample("sprawl", [1, 1, 0, 0]) for _ in range(3)]
    base = connection_baseline(samples, base_rate=0.25)
    # Every scenario's measured ratio is 0.5, so the floor is |0.5 - 0.25|.
    assert base["training_rate_ratio_mae"] == pytest.approx(0.25)
    assert base["training_rate_brier"] == pytest.approx(
        (2 * (0.25 - 1) ** 2 + 2 * 0.25 ** 2) / 4)


def test_cap_skips_name_the_reasons_that_mean_a_scenario_was_too_big():
    """`encode` and `connections` are the two ways a scenario is dropped for
    exceeding a tensor cap rather than for being unplayable — the eval report
    keys off these names, so they have to stay in step with the generator."""
    from app.policies.goal_based_policies import dataset as dataset_module

    for reason, target in (("encode", "encode_sample"),
                           ("connections", "encode_connections")):
        assert reason in CAP_SKIPS
        assert hasattr(dataset_module, target)


@pytest.mark.integration
def test_a_generated_set_stamps_its_mix_on_every_scenario_and_reports_skips():
    """The mix name has to survive generation, or a set built from several
    mixes cannot be scored per mix afterwards."""
    chosen = mixes_by_name(["control", "long"])
    samples, skipped = generate_eval_set(
        per_mix=2, mixes=chosen, chunk_size=1, workers=2, verbose=False
    )
    assert {s.mix for s in samples} == {"control", "long"}
    assert set(skipped) == {"control", "long"}
    assert all(isinstance(count, int)
               for reasons in skipped.values() for count in reasons.values())


@pytest.mark.integration
def test_a_generated_set_round_trips_through_the_cache_with_its_mixes(tmp_path):
    """Generation costs hours, so scoring runs off the cache — which means
    the mix labels have to survive the round trip or the per-mix breakdown
    silently collapses to one group."""
    from app.policies.goal_based_policies.dataset import load_samples, save_samples

    samples, _ = generate_eval_set(
        per_mix=2, mixes=mixes_by_name(["control", "dense"]),
        chunk_size=1, workers=2, verbose=False,
    )
    path = str(tmp_path / "eval.npz")
    save_samples(path, samples)
    restored = load_samples(path)
    assert [s.mix for s in restored] == [s.mix for s in samples]
    assert [s.source for s in restored] == [s.source for s in samples]
