"""What the networks see, and the loop that trains them.

The value network is optional — the search runs without one — so what
matters here is that the observation describes the state faithfully, that
batching cannot let one scenario bleed into another, and that the self-play
loop produces labels that are the outcome actually achieved.
"""
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.policies.tree_search import (  # noqa: E402
    actions,
    metrics,
    observation,
    selfplay,
    simulator,
)
from tests.test_tree_search_simulator import make_scenario  # noqa: E402


@pytest.fixture(scope="module")
def scenario():
    return make_scenario(seed=7, agents=3, size=30)


# ------------------------------------------------------------ observation

def test_a_travelling_train_is_drawn_at_the_node_it_is_heading_for(scenario):
    """The projection that keeps the state inside the reduced graph — with
    the steps still to drive kept, so two states that snap to the same
    nodes but are minutes apart do not look identical."""
    state = actions.advance_to_choice(
        scenario, simulator.initial_state(scenario))
    for _ in range(8):
        state = simulator.step(scenario, state)
    encoded = observation.encode(scenario, state)
    ordered = sorted(scenario.graph.nodes)

    for row, train in enumerate(state.trains):
        target = (
            train.edge.to_cell if train.edge is not None else train.cell
        )
        assert ordered[encoded.train_nodes[row]] == target
        steps_out = encoded.train_features[row][0] * scenario.horizon
        if train.edge is not None:
            assert steps_out == pytest.approx(
                len(train.edge.path) - 1 - train.index)
        elif train.departed:
            assert steps_out == pytest.approx(0.0)


def test_the_observation_says_which_trains_are_deciding(scenario):
    state = actions.advance_to_choice(
        scenario, simulator.initial_state(scenario))
    encoded = observation.encode(scenario, state)
    deciding = set(simulator.deciding(scenario, state))
    for row, train in enumerate(state.trains):
        assert bool(encoded.train_features[row][9]) == (train.handle in deciding)


def test_batching_two_different_railways_keeps_them_apart():
    """Padding a small network up to a large one must not change what the
    small one scores — otherwise a batch's contents would leak into every
    value in it."""
    from app.policies.tree_search.net import StateValueNet, evaluate_states

    import torch

    torch.manual_seed(0)
    small = make_scenario(seed=11, agents=2, size=25)
    large = make_scenario(seed=7, agents=5, size=40)
    one = observation.encode(small, simulator.initial_state(small))
    other = observation.encode(large, simulator.initial_state(large))

    model = StateValueNet(hidden=16, rounds=2, trunk_layers=1)
    alone = evaluate_states({"punctuality": model}, [one])["punctuality"][0]
    together = evaluate_states(
        {"punctuality": model}, [one, other])["punctuality"][0]
    assert alone == pytest.approx(together, abs=1e-5)


# --------------------------------------------------------------- selfplay

def test_self_play_labels_every_state_with_what_the_run_achieved(scenario):
    """The AlphaZero shape: the states on the path that was executed all
    carry the outcome that path actually reached — not a prediction, and
    not a per-state guess."""
    episode = selfplay.play(scenario, budget=40, temperature=0.0, name="t")
    assert episode.samples, "a run produced no states to learn from"
    achieved = metrics.utilities(episode.outcome)
    for sample in episode.samples:
        assert sample.labels == achieved
        assert sample.scenario == "t"
    assert 0.0 <= achieved["punctuality"] <= 1.0


def test_exploring_runs_differ_from_the_preferred_one(scenario):
    """Without exploration a generation only ever sees states the current
    network already likes, and the loop stalls."""
    preferred = selfplay.play(scenario, budget=40, temperature=0.0, seed=1)
    explored = [
        selfplay.play(scenario, budget=40, temperature=1.0, seed=seed)
        for seed in range(4)
    ]
    labels = {round(e.utilities["punctuality"], 6) for e in explored}
    labels.add(round(preferred.utilities["punctuality"], 6))
    assert len(labels) > 1, "every exploring run came out identical"


def test_samples_survive_a_round_trip_through_the_cache(tmp_path, scenario):
    episode = selfplay.play(scenario, budget=30, temperature=0.0, name="rt")
    path = str(tmp_path / "cache.npz")
    selfplay.save(path, episode.samples)
    restored = selfplay.load(path)

    assert len(restored) == len(episode.samples)
    first, again = episode.samples[0], restored[0]
    assert again.labels == first.labels
    assert np.allclose(
        again.observation.train_features, first.observation.train_features)
    assert np.array_equal(
        again.observation.graph.edge_index, first.observation.graph.edge_index)


# --------------------------------------------------------------- training

def test_training_moves_the_network_towards_the_labels():
    """The network has to be able to fit what it is shown — if this fails,
    nothing downstream can work."""
    from app.policies.tree_search.net import StateValueNet
    from app.policies.tree_search.train import evaluate, fit

    scenarios = [
        (f"s{seed}", make_scenario(seed=seed, agents=3, size=25))
        for seed in (3, 5, 7, 11)
    ]
    samples, _ = selfplay.collect(scenarios, budget=30, temperature=0.5)
    assert len(samples) > 20

    model = StateValueNet(hidden=16, rounds=2, trunk_layers=1)
    before = evaluate(model, samples, "punctuality")
    fit(model, samples, epochs=30, batch_size=16, seed=0)
    after = evaluate(model, samples, "punctuality")
    assert after["mae"] < before["mae"], (before, after)


def test_a_trained_network_can_be_saved_and_reloaded(tmp_path):
    from app.policies.tree_search.net import StateValueNet

    import torch

    torch.manual_seed(0)
    model = StateValueNet(hidden=16, rounds=2, trunk_layers=1)
    path = tmp_path / "punctuality.ckpt"
    model.save(path)

    restored = StateValueNet.load(str(path))
    assert restored.metric == "punctuality"
    for (name, one), (other_name, other) in zip(
        model.state_dict().items(), restored.state_dict().items()
    ):
        assert name == other_name
        assert torch.equal(one, other)


def test_the_planner_picks_up_an_installed_network(tmp_path):
    """Installing a checkpoint is all it takes — the planner looks in one
    place and runs unguided when nothing is there."""
    from app.policies.tree_search import director
    from app.policies.tree_search.net import StateValueNet

    StateValueNet(hidden=16, rounds=2, trunk_layers=1).save(
        tmp_path / "punctuality.ckpt")
    found = director.load_models(str(tmp_path))
    assert sorted(found) == ["punctuality"]
    assert director.load_models(str(tmp_path / "nowhere")) == {}
