"""Schedule evaluator: rollout labelling, schedule encoding, encoder, training."""
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from app.policies.goal_based_policies.dataset import (  # noqa: E402
    EDGE_FEATURES,
    MAX_EDGES,
    MAX_CONNECTIONS,
    MAX_NODES,
    MAX_SCHEDULE_NODES,
    MAX_TRAINS,
    NODE_FEATURES,
    STOP_FLAGS,
    TRAIN_SCALARS,
    Sample,
    build_layout_env,
    default_layouts,
    encode_graph,
    encode_sample,
    generate_samples,
    perturb_waits,
    plan_all_trains,
    stack_samples,
)
from app.policies.goal_based_policies.evaluator import (  # noqa: E402
    GraphEncoder,
    ScheduleEncoder,
    ScheduleEvaluator,
)
from app.policies.goal_based_policies.infrastructure_graph import (  # noqa: E402
    build_decision_point_graph,
)
from app.policies.goal_based_policies.rollout import (  # noqa: E402
    DELAY_BUCKET_LABELS,
    NUM_DELAY_BUCKETS,
    delay_bucket,
    run_schedules,
)
from app.policies.goal_based_policies.schedule import (  # noqa: E402
    ScheduleEntry,
    TrainSchedule,
    plan_avoiding_overlaps,
)
from app.policies.goal_based_policies.train_evaluator import train_evaluator  # noqa: E402

LAYOUTS = default_layouts(4, seed=0)


def _scenario(layout_index=0, trains=3):
    layout = LAYOUTS[layout_index]
    env = build_layout_env(layout, trains)
    graph = build_decision_point_graph(env)
    return layout, env, graph, plan_all_trains(env, graph)


def _model_inputs(sample):
    return (
        torch.tensor(sample.graph_nodes).unsqueeze(0),
        torch.tensor(sample.graph_node_mask).unsqueeze(0),
        torch.tensor(sample.edge_index).unsqueeze(0),
        torch.tensor(sample.edge_features).unsqueeze(0),
        torch.tensor(sample.edge_mask).unsqueeze(0),
        torch.tensor(sample.schedule_nodes).unsqueeze(0),
        torch.tensor(sample.waits).unsqueeze(0),
        torch.tensor(sample.node_mask).unsqueeze(0),
        torch.tensor(sample.stop_flags).unsqueeze(0),
        torch.tensor(sample.train_scalars).unsqueeze(0),
        torch.tensor(sample.train_mask).unsqueeze(0),
    )


# ── labelling ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "minutes,expected",
    [(0, 0), (4, 0), (5, 1), (14, 1), (15, 2), (29, 2), (30, 3),
     (44, 3), (45, 4), (59, 4), (60, 5), (600, 5)],
)
def test_delay_buckets_match_the_specified_ranges(minutes, expected):
    assert delay_bucket(minutes) == expected
    assert len(DELAY_BUCKET_LABELS) == NUM_DELAY_BUCKETS == 6


def test_delay_grows_with_holds_once_the_slack_is_used_up():
    measured = []
    for wait in (0, 10, 20, 40):
        _, env, graph, schedules = _scenario(trains=1)
        entries = list(schedules[0].entries)
        held = TrainSchedule(
            handle=0,
            entries=[ScheduleEntry(entries[0].node_id, wait)] + entries[1:],
        )
        measured.append(run_schedules(env, graph, [held]))

    delays = [r.total_delay for r in measured]
    assert delays == sorted(delays), f"delay should not shrink with holds: {delays}"
    assert delays[-1] > delays[0]
    assert measured[-1].bucket >= measured[0].bucket


# ── node ids ─────────────────────────────────────────────────────────

def test_node_ids_are_stable_for_a_layout_regardless_of_train_count():
    """Schedules address nodes by id, so an id must mean the same cell no
    matter how many trains are running."""
    layout = LAYOUTS[0]
    seen = {}
    for trains in (2, 5, 8):
        env = build_layout_env(layout, trains)
        graph = build_decision_point_graph(env)
        for cell, node in graph.nodes.items():
            assert node.node_id == cell[0] * env.width + cell[1]
            if cell in seen:
                assert seen[cell] == node.node_id
            seen[cell] = node.node_id


# ── the infrastructure in the observation ────────────────────────────

def test_graph_encoding_describes_the_real_network():
    _, env, graph, _ = _scenario(trains=3)
    nodes, node_mask, edge_index, edge_features, edge_mask, local = encode_graph(
        env, graph
    )
    assert nodes.shape == (MAX_NODES, NODE_FEATURES)
    assert edge_index.shape == (MAX_EDGES, 2)
    assert edge_features.shape == (MAX_EDGES, EDGE_FEATURES)
    assert node_mask.sum() == len(graph.nodes)
    assert edge_mask.sum() == len(graph.edges)
    assert len(local) == len(graph.nodes)

    # Every encoded edge joins the two nodes it actually joins, and carries
    # its travel time.
    ordered = sorted(graph.nodes)
    for position, edge in enumerate(graph.edges):
        source, target = edge_index[position]
        assert ordered[source] == edge.from_cell
        assert ordered[target] == edge.to_cell
        horizon = float(env._max_episode_steps)
        assert edge_features[position][0] == pytest.approx(
            edge.travel_time / horizon
        )
        assert edge_features[position][1] == pytest.approx(
            np.log1p(edge.travel_time) / np.log1p(128.0), rel=1e-5
        )
        assert edge_features[position][2] in (0.0, 1.0)
        # Crowding and peak occupancy are schedule-dependent, so
        # encode_graph alone leaves them 0.
        assert edge_features[position][3] == 0.0
        assert edge_features[position][4] == 0.0

    # Station and switch-decision flags match the graph.
    for cell, index in ((c, local[graph.nodes[c].node_id]) for c in ordered):
        node = graph.nodes[cell]
        assert nodes[index][0] == float("station" in node.kinds)
        assert nodes[index][1] == float("switch_decision" in node.kinds)


def test_crowding_counts_trains_routing_through_each_edge():
    """The crowding column must equal how many trains' routes touch each
    edge, and encode_sample must write it (encode_graph does not know it)."""
    from app.policies.goal_based_policies.dataset import (
        _schedule_cells,
        edge_train_counts,
    )

    _, env, graph, schedules = _scenario(trains=4)
    counts = edge_train_counts(env, graph, schedules)
    assert len(counts) == len(graph.edges)
    assert max(counts) <= len(schedules)

    # Independent recount: a train contributes to an edge iff its covered
    # cells intersect the edge's cells.
    coverage = [_schedule_cells(env, graph, s) for s in schedules]
    for position, edge in enumerate(graph.edges):
        section = set(edge.path)
        assert counts[position] == sum(1 for c in coverage if c & section)

    # Every train's own route must register: the edge leaving its first node
    # is covered by at least that train.
    assert max(counts) >= 1

    # encode_sample writes it into the fourth edge column, normalised by
    # MAX_TRAINS; encode_graph leaves it zero (checked elsewhere).
    sample = encode_sample(env, graph, 0, schedules)
    for position, count in enumerate(counts):
        assert sample.edge_features[position][3] == pytest.approx(count / MAX_TRAINS)


def test_schedule_edges_needs_the_heading_the_train_actually_has():
    """A cell offers different onward edges depending on which way the train
    points, so resolving a schedule that does not start at the train's
    origin needs its real starting heading. Without it the first hop matches
    nothing and the walk truncates — silently, which is what made multi-leg
    plans look unroutable."""
    from app.policies.goal_based_policies.dataset import (
        _schedule_edges,
        start_heading_of,
    )

    _, env, graph, schedules = _scenario(trains=2)
    schedule = schedules[0]
    correct = start_heading_of(env, schedule)

    full = _schedule_edges(env, graph, schedule)
    assert len(full) == len(schedule.entries) - 1, "baseline plan must resolve"
    # Explicitly passing the right heading is identical to the default.
    assert _schedule_edges(env, graph, schedule, correct) == full

    # Some other heading resolves strictly less of the same schedule; at
    # least one must truncate, or the heading would not matter at all.
    truncated = [
        len(_schedule_edges(env, graph, schedule, h))
        for h in range(4) if h != correct
    ]
    assert min(truncated) < len(full), (
        "no heading truncated — the walk is not heading-sensitive"
    )


def test_crowding_uses_the_supplied_headings():
    """The features built on `_schedule_edges` must honour the headings too,
    or a multi-leg schedule silently contributes nothing to them."""
    from app.policies.goal_based_policies.dataset import (
        edge_peak_occupancy,
        edge_train_counts,
        start_heading_of,
    )

    _, env, graph, schedules = _scenario(trains=3)
    right = [start_heading_of(env, s) for s in schedules]
    assert edge_train_counts(env, graph, schedules, right) == \
        edge_train_counts(env, graph, schedules)

    # A wrong heading truncates the walk, so coverage can only shrink.
    wrong = [(h + 2) % 4 for h in right]
    assert sum(edge_train_counts(env, graph, schedules, wrong)) <= \
        sum(edge_train_counts(env, graph, schedules, right))
    assert sum(edge_peak_occupancy(env, graph, schedules, wrong)) <= \
        sum(edge_peak_occupancy(env, graph, schedules, right))

    # Headings are positional, so a length mismatch is an error, not a guess.
    with pytest.raises(ValueError, match="positional"):
        edge_train_counts(env, graph, schedules, right[:-1])


def test_encode_sample_accepts_headings_without_changing_the_default():
    from app.policies.goal_based_policies.dataset import start_heading_of

    layout, env, graph, schedules = _scenario(trains=3)
    default = encode_sample(env, graph, layout.index, schedules)
    explicit = encode_sample(
        env, graph, layout.index, schedules,
        start_headings=[start_heading_of(env, s) for s in schedules],
    )
    assert np.array_equal(default.edge_features, explicit.edge_features)
    assert np.array_equal(default.train_scalars, explicit.train_scalars)


def test_peak_occupancy_is_time_aware_crowding():
    """Column 4 counts trains planned to be on an edge *at the same time*,
    so it can never exceed the spatial count, and a lone train can never
    contest an edge with itself."""
    from app.policies.goal_based_policies.dataset import (
        edge_peak_occupancy,
        edge_train_counts,
    )

    _, env, graph, schedules = _scenario(trains=4)
    counts = edge_train_counts(env, graph, schedules)
    peaks = edge_peak_occupancy(env, graph, schedules)
    assert len(peaks) == len(graph.edges)
    for peak, count in zip(peaks, counts):
        assert 0 <= peak <= count

    # A single train alone on the network has a peak of exactly 1 wherever
    # it drives and 0 elsewhere.
    solo = edge_peak_occupancy(env, graph, schedules[:1])
    assert set(solo) <= {0, 1}
    assert 1 in solo

    # Holding one train long enough separates it in time from the others:
    # total time on shared edges can only stay or drop, never rise.
    delayed = [schedules[0]] + [
        TrainSchedule(
            s.handle,
            [ScheduleEntry(s.entries[0].node_id, 500)] + list(s.entries[1:]),
        )
        for s in schedules[1:]
    ]
    shifted = edge_peak_occupancy(env, graph, delayed)
    assert all(after <= before or before == 0
               for after, before in zip(shifted, peaks))

    # encode_sample writes it into the fifth edge column, normalised.
    sample = encode_sample(env, graph, 0, schedules)
    for position, peak in enumerate(peaks):
        assert sample.edge_features[position][4] == pytest.approx(peak / MAX_TRAINS)


def test_train_scalars_carry_planned_duration_and_slack():
    """Scalar columns: departure, deadline, planned duration, slack, total
    hold — each a fraction of the horizon, with slack the identity
    deadline - departure - planned duration."""
    from app.policies.goal_based_policies.dataset import _schedule_edges

    layout, env, graph, schedules = _scenario(trains=3)
    sample = encode_sample(env, graph, layout.index, schedules)
    horizon = float(env._max_episode_steps)

    for row, schedule in enumerate(schedules):
        agent = env.agents[schedule.handle]
        departure, deadline, duration, slack, hold = sample.train_scalars[row]
        assert departure == pytest.approx(float(agent.earliest_departure) / horizon)
        assert deadline == pytest.approx(float(agent.latest_arrival) / horizon)
        run = sum(e.travel_time for e in _schedule_edges(env, graph, schedule))
        waits = sum(e.wait for e in schedule.entries)
        assert duration == pytest.approx((run + waits) / horizon)
        assert hold == pytest.approx(waits / horizon)
        assert slack == pytest.approx(deadline - departure - duration, abs=1e-5)

    # Holding a train lengthens its plan and eats its slack, one for one.
    held = [
        TrainSchedule(
            schedules[0].handle,
            [ScheduleEntry(schedules[0].entries[0].node_id, 10)]
            + list(schedules[0].entries[1:]),
        )
    ] + list(schedules[1:])
    held_sample = encode_sample(env, graph, layout.index, held)
    assert held_sample.train_scalars[0][2] - sample.train_scalars[0][2] == (
        pytest.approx(10 / horizon)
    )
    assert sample.train_scalars[0][3] - held_sample.train_scalars[0][3] == (
        pytest.approx(10 / horizon)
    )


def test_graph_encoding_refuses_to_truncate_a_network():
    from app.policies.goal_based_policies import dataset as dataset_module

    _, env, graph, _ = _scenario(trains=3)
    original = dataset_module.MAX_NODES
    dataset_module.MAX_NODES = 4
    try:
        with pytest.raises(ValueError, match="exceeds MAX_NODES"):
            encode_graph(env, graph)
    finally:
        dataset_module.MAX_NODES = original


# ── encoding ─────────────────────────────────────────────────────────

def test_encoding_shapes_and_masking():
    layout, env, graph, schedules = _scenario(trains=3)
    sample = encode_sample(env, graph, layout.index, schedules)

    assert sample.schedule_nodes.shape == (MAX_TRAINS, MAX_SCHEDULE_NODES)
    assert sample.waits.shape == (MAX_TRAINS, MAX_SCHEDULE_NODES)
    assert sample.node_mask.shape == (MAX_TRAINS, MAX_SCHEDULE_NODES)
    assert sample.train_scalars.shape == (MAX_TRAINS, TRAIN_SCALARS)
    assert sample.train_mask.sum() == len(schedules)
    assert np.all(sample.schedule_nodes[len(schedules):] == 0)

    ordered = sorted(graph.nodes)
    for row, schedule in enumerate(schedules):
        length = len(schedule.entries)
        assert sample.node_mask[row].sum() == length
        # Schedules index into this scenario's graph, so each entry must
        # resolve back to the cell the schedule actually names.
        for column, entry in enumerate(schedule.entries):
            assert ordered[sample.schedule_nodes[row, column]] == graph.cell_of(
                entry.node_id
            )


def test_encoding_carries_the_waits():
    layout, env, graph, schedules = _scenario(trains=2)
    held = [
        TrainSchedule(s.handle, [ScheduleEntry(e.node_id, 6) for e in s.entries])
        for s in schedules
    ]
    sample = encode_sample(env, graph, layout.index, held)
    length = len(held[0].entries)
    horizon = float(env._max_episode_steps)
    assert np.allclose(sample.waits[0][:length], 6.0 / horizon)
    assert np.all(sample.waits[0][length:] == 0.0)


def test_encoding_refuses_to_silently_drop_trains():
    layout, env, graph, schedules = _scenario(trains=3)
    too_many = list(schedules) * 4
    with pytest.raises(ValueError, match="exceeds MAX_TRAINS"):
        encode_sample(env, graph, layout.index, too_many)


def test_perturb_waits_keeps_the_node_sequence():
    import random

    _, env, graph, schedules = _scenario(trains=2)
    perturbed = perturb_waits(schedules, random.Random(0))
    for before, after in zip(schedules, perturbed):
        assert [e.node_id for e in before.entries] == [e.node_id for e in after.entries]
        assert all(e.wait >= 0 for e in after.entries)


# ── overlap-avoiding planner ─────────────────────────────────────────

def test_overlap_planner_only_adds_waits():
    """It may hold trains but must never reroute them."""
    _, env, graph, schedules = _scenario(trains=4)
    planned = plan_avoiding_overlaps(env, graph, schedules)
    assert len(planned) == len(schedules)
    for before, after in zip(schedules, planned):
        assert after.handle == before.handle
        assert [e.node_id for e in after.entries] == [e.node_id for e in before.entries]
        assert all(a.wait >= b.wait for a, b in zip(after.entries, before.entries))


def test_overlap_planner_output_is_runnable():
    _, env, graph, schedules = _scenario(trains=4)
    planned = plan_avoiding_overlaps(env, graph, schedules)
    result = run_schedules(env, graph, planned)
    assert result.steps > 0
    assert set(result.delays) == {s.handle for s in schedules}


# ── model ────────────────────────────────────────────────────────────

def _graph_batch(num_nodes=5, num_edges=6, trains=2, steps=4):
    """A tiny hand-made graph plus schedules on it."""
    graph_nodes = torch.zeros(1, MAX_NODES, NODE_FEATURES)
    graph_nodes[0, :num_nodes] = torch.rand(num_nodes, NODE_FEATURES)
    graph_node_mask = torch.zeros(1, MAX_NODES)
    graph_node_mask[0, :num_nodes] = 1.0
    edge_index = torch.zeros(1, MAX_EDGES, 2, dtype=torch.long)
    for e in range(num_edges):
        edge_index[0, e] = torch.tensor([e % num_nodes, (e + 1) % num_nodes])
    edge_features = torch.zeros(1, MAX_EDGES, EDGE_FEATURES)
    edge_features[0, :num_edges] = 0.25
    edge_mask = torch.zeros(1, MAX_EDGES)
    edge_mask[0, :num_edges] = 1.0

    schedule_nodes = torch.zeros(1, MAX_TRAINS, MAX_SCHEDULE_NODES, dtype=torch.long)
    waits = torch.zeros(1, MAX_TRAINS, MAX_SCHEDULE_NODES)
    node_mask = torch.zeros(1, MAX_TRAINS, MAX_SCHEDULE_NODES)
    for t in range(trains):
        schedule_nodes[0, t, :steps] = torch.arange(steps) % num_nodes
        node_mask[0, t, :steps] = 1.0
    stop_flags = torch.zeros(1, MAX_TRAINS, MAX_SCHEDULE_NODES, STOP_FLAGS)
    for t in range(trains):
        stop_flags[0, t, steps - 1, 0] = 1.0   # last visited node is a stop
        stop_flags[0, t, steps - 1, 1] = 1.0   # and it is the terminus
    train_scalars = torch.zeros(1, MAX_TRAINS, TRAIN_SCALARS)
    train_scalars[0, :trains] = 0.5
    train_mask = torch.zeros(1, MAX_TRAINS)
    train_mask[0, :trains] = 1.0
    return [graph_nodes, graph_node_mask, edge_index, edge_features, edge_mask,
            schedule_nodes, waits, node_mask, stop_flags, train_scalars, train_mask]


def test_graph_encoder_output_shape_and_padding_is_zeroed():
    encoder = GraphEncoder()
    batch = _graph_batch(num_nodes=5, num_edges=6)
    embeddings = encoder(*batch[:5])
    assert embeddings.shape == (1, MAX_NODES, encoder.hidden)
    # Nodes that do not exist must stay zero so pooling ignores them.
    assert torch.count_nonzero(embeddings[0, 5:]) == 0


def test_graph_encoder_propagates_along_edges():
    """A node's vector must depend on its neighbours, not just itself —
    otherwise message passing is not doing anything."""
    torch.manual_seed(0)
    encoder = GraphEncoder()
    batch = _graph_batch(num_nodes=5, num_edges=6)
    connected = encoder(*batch[:5])

    isolated = [t.clone() for t in batch[:5]]
    isolated[4] = torch.zeros_like(isolated[4])  # drop every edge
    detached = encoder(*isolated)
    assert not torch.allclose(connected[0, :5], detached[0, :5], atol=1e-5)


def test_model_is_indifferent_to_node_numbering():
    """The same network relabelled must give the same prediction: node
    meaning has to come from structure, not from the index."""
    torch.manual_seed(0)
    model = ScheduleEvaluator().eval()
    batch = _graph_batch(num_nodes=5, num_edges=6)
    base = model(*batch)

    permutation = torch.tensor([2, 0, 4, 1, 3])
    inverse = torch.argsort(permutation)
    shuffled = [t.clone() for t in batch]
    shuffled[0][0, :5] = batch[0][0, permutation]
    for e in range(6):
        shuffled[2][0, e] = inverse[batch[2][0, e]]
    shuffled[5][0, :, :] = inverse[batch[5][0, :, :].clamp(max=4)]
    relabelled = model(*shuffled)
    assert torch.allclose(base[0], relabelled[0], atol=1e-4)
    assert torch.allclose(base[1], relabelled[1], atol=1e-4)


def test_model_output_shapes_and_prediction():
    layout, env, graph, schedules = _scenario(trains=3)
    sample = encode_sample(env, graph, layout.index, schedules)
    model = ScheduleEvaluator()

    arrival_logit, delay_logits, connection_logit = model(*_model_inputs(sample))
    assert arrival_logit.shape == (1,)
    assert delay_logits.shape == (1, NUM_DELAY_BUCKETS)
    assert connection_logit.shape == (1,)

    prediction = model.predict(*_model_inputs(sample))
    assert torch.allclose(
        prediction["delay_bucket_probabilities"].sum(dim=-1), torch.ones(1), atol=1e-5
    )


def test_model_ignores_train_order_and_padding():
    torch.manual_seed(0)
    model = ScheduleEvaluator().eval()
    batch = _graph_batch(trains=3, steps=4)
    base = model(*batch)

    order = [2, 0, 1, 3, 4, 5, 6, 7]
    shuffled = list(batch)
    for index in (5, 6, 7, 8, 9):
        shuffled[index] = batch[index][:, order]
    assert torch.allclose(base[0], model(*shuffled)[0], atol=1e-5)

    noisy = [t.clone() for t in batch]
    noisy[5][0, 3:] = 4
    noisy[6][0, 3:] = 9.0
    assert torch.allclose(base[0], model(*noisy)[0], atol=1e-5)


def test_train_scalars_stay_bound_to_their_schedule_row():
    """Row t of every per-train tensor must describe the same train. Moving
    only the timetable rows, leaving the schedules where they are, has to
    change the prediction — if it does not, the pairing is being lost."""
    torch.manual_seed(0)
    model = ScheduleEvaluator().eval()
    batch = _graph_batch(trains=3, steps=4)
    # Give the three trains clearly different timetables and schedules.
    batch[9][0, 0] = torch.tensor([0.0, 0.4, 0.3, 0.1, 0.0])
    batch[9][0, 1] = torch.tensor([0.2, 0.7, 0.4, 0.1, 0.3])
    batch[9][0, 2] = torch.tensor([0.5, 0.95, 0.2, 0.25, 0.7])
    for t in range(3):
        batch[5][0, t, :4] = torch.tensor([t, (t + 1) % 5, (t + 2) % 5, (t + 3) % 5])
        batch[6][0, t, :4] = 0.1 * (t + 1)
    base = model(*batch)

    mismatched = [t.clone() for t in batch]
    mismatched[9][0, :3] = batch[9][0, [1, 2, 0]]  # timetables only
    assert not torch.allclose(base[0], model(*mismatched)[0], atol=1e-6), (
        "swapping timetables between trains changed nothing — rows are not bound"
    )

    # Whereas permuting *all* per-train rows together is the same scenario.
    together = [t.clone() for t in batch]
    order = [1, 2, 0, 3, 4, 5, 6, 7]
    for index in (5, 6, 7, 8, 9):
        together[index] = batch[index][:, order]
    assert torch.allclose(base[0], model(*together)[0], atol=1e-5)


def test_prediction_responds_to_the_waits():
    """A schedule full of long holds must not encode identically to one
    without them — otherwise the model cannot judge dispatching at all.

    Asserted on the schedule encoding rather than on one head's logit: in an
    untrained net the trunk attenuates the difference by an amount that
    depends on the random init, so a per-head threshold tests the draw
    rather than the wiring.
    """
    torch.manual_seed(0)
    model = ScheduleEvaluator().eval()
    batch = _graph_batch(trains=2, steps=4)
    held = [t.clone() for t in batch]
    held[6][0, :2, :4] = 1.0

    embeddings = model.graph_encoder(*batch[:5])
    without = model.schedule_encoder(embeddings, *batch[5:])
    with_waits = model.schedule_encoder(embeddings, *held[5:])
    assert not torch.allclose(without, with_waits, atol=1e-6), (
        "holding every train changed nothing in the schedule encoding"
    )

    # And it reaches the outputs: some head must move, though which one
    # moves most is an artefact of initialisation.
    before, after = model(*batch), model(*held)
    assert max((b - a).abs().max().item() for b, a in zip(before, after)) > 1e-6


def test_encoder_handles_any_graph_and_train_count():
    """Fixed-width output regardless of how big the problem is."""
    model = ScheduleEvaluator().eval()
    for nodes, edges, trains in ((3, 2, 1), (20, 40, 4), (60, 150, MAX_TRAINS)):
        batch = _graph_batch(num_nodes=nodes, num_edges=edges, trains=trains)
        arrival, delay, connection = model(*batch)
        assert arrival.shape == (1,) and delay.shape == (1, NUM_DELAY_BUCKETS)
        assert connection.shape == (1,)


def test_dropout_model_round_trips_and_regularises(tmp_path):
    """A regularised model must save/load exactly (dropout adds no
    parameters but must survive in the config) and be deterministic in
    eval mode."""
    layout, env, graph, schedules = _scenario(trains=2)
    sample = encode_sample(env, graph, layout.index, schedules)
    model = ScheduleEvaluator(dropout=0.1)
    assert model._config["dropout"] == 0.1

    before = model.predict(*_model_inputs(sample))
    again = model.predict(*_model_inputs(sample))
    assert torch.allclose(
        before["all_arrived_probability"], again["all_arrived_probability"]
    ), "eval-mode prediction must be deterministic despite dropout"

    path = tmp_path / "regularised.pt"
    model.save(path)
    restored = ScheduleEvaluator.load(path)
    assert restored._config["dropout"] == 0.1
    after = restored.predict(*_model_inputs(sample))
    assert torch.allclose(
        before["all_arrived_probability"], after["all_arrived_probability"]
    )


def test_ordinal_bucket_loss_prefers_near_misses():
    """The buckets are ordered: predicting the neighbour of the true bucket
    must cost less than predicting a distant one, and the truth least of
    all — that is the whole point of the ordinal target."""
    from app.policies.goal_based_policies.train_evaluator import OrdinalBucketLoss

    loss = OrdinalBucketLoss(torch.ones(NUM_DELAY_BUCKETS))
    target = torch.tensor([2])

    def confident(bucket):
        logits = torch.full((1, NUM_DELAY_BUCKETS), -4.0)
        logits[0, bucket] = 4.0
        return loss(logits, target).item()

    exact, near, far = confident(2), confident(3), confident(5)
    assert exact < near < far

    # Class weights follow CrossEntropyLoss semantics: upweighting a rare
    # class makes getting *its* samples wrong dominate the batch loss.
    weights = torch.ones(NUM_DELAY_BUCKETS)
    weights[5] = 10.0
    logits = torch.full((2, NUM_DELAY_BUCKETS), -4.0)
    logits[:, 1] = 4.0  # confidently predicts bucket 1 for both samples
    targets = torch.tensor([1, 5])  # right for the common, wrong for the rare
    assert OrdinalBucketLoss(weights)(logits, targets) > loss(logits, targets)


# ── data generation and training ─────────────────────────────────────

@pytest.mark.integration
def test_every_scenario_gets_its_own_network_by_default():
    """Layout diversity is what the model has to generalise over, so the
    default generator must never hand it the same network twice."""
    samples = generate_samples(12, seed=1)
    assert len({s.layout for s in samples}) == len(samples)

    # An explicit pool still reuses those networks.
    pool = default_layouts(2, seed=0)
    reused = generate_samples(8, seed=1, layouts=pool)
    assert len({s.layout for s in reused}) <= 2


def test_env_carries_no_malfunction_random_cache():
    """Flatland caches a million random draws per env (9 MB) on the first
    step even with malfunctions off. Generating tens of thousands of
    scenarios cannot afford that, and with probability 0 the cache only ever
    yields "no malfunction" — so the env must not allocate it, and must
    still never produce a malfunction."""
    from flatland.envs.malfunction_generators import NBR_CHACHED_RAND

    layout, env, graph, schedules = _scenario(trains=2)
    generator = env.malfunction_generator
    assert generator.generate().num_broken_steps == 0

    run_schedules(env, graph, schedules)
    assert generator._cached_rand is None, (
        f"env allocated the {NBR_CHACHED_RAND}-draw malfunction cache"
    )
    assert all(a.malfunction_handler.malfunction_down_counter == 0
               for a in env.agents)


@pytest.mark.integration
def test_parallel_generation_matches_a_plain_run_and_is_deterministic():
    """Workers are recycled to bound memory, so the same call twice must
    give the same dataset, and each chunk must be exactly what
    generate_samples would produce for that chunk's seed."""
    from app.policies.goal_based_policies.dataset import (
        generate_samples_parallel,
    )

    def digest(samples):
        return [(s.layout, s.source, s.all_arrived, s.bucket, s.total_delay)
                for s in samples]

    first = generate_samples_parallel(16, seed=11, workers=2, chunk_size=8)
    second = generate_samples_parallel(16, seed=11, workers=2, chunk_size=8)
    assert len(first) == 16
    assert digest(first) == digest(second)

    # Each chunk is a plain generate_samples run under a derived seed, so
    # the parallel result is the union of those — no scenario is invented
    # by the parallelism itself.
    expected = digest(generate_samples(8, seed=11 * 1_000_003 + 0)) + digest(
        generate_samples(8, seed=11 * 1_000_003 + 1)
    )
    assert sorted(map(str, digest(first))) == sorted(map(str, expected))


def test_caches_from_before_per_connection_labels_still_load(tmp_path):
    """`stack_samples` documents that older caches read as "no
    connections"; loading must accept what stacking accepts, or every
    dataset from before the connection block becomes unusable (the 30k
    evaluator cache is exactly such a file)."""
    from app.policies.goal_based_policies.dataset import load_samples, save_samples

    samples = generate_samples(2, seed=2)
    path = str(tmp_path / "old.npz")
    save_samples(path, samples)
    with np.load(path, allow_pickle=False) as archive:
        data = {key: archive[key] for key in archive.files
                if not key.startswith("connection_")}
    np.savez_compressed(path, **data)

    restored = load_samples(path)
    assert len(restored) == len(samples)
    for sample in restored:
        assert sample.connection_features is None
        assert sample.connection_mask is None
    # And stacking still reads the absence as an all-zero mask.
    from app.policies.goal_based_policies.dataset import stack_samples
    assert stack_samples(restored)[-1].sum() == 0


def test_dataset_cache_round_trips(tmp_path):
    """Continuing a run must train on exactly the same data, so the cache
    has to restore every field byte-for-byte."""
    from app.policies.goal_based_policies.dataset import load_samples, save_samples

    samples = generate_samples(6, seed=2)
    path = str(tmp_path / "data.npz")
    save_samples(path, samples)
    restored = load_samples(path)

    assert len(restored) == len(samples)
    # Per-connection labels must survive too: they are the whole training
    # signal for the connection model, and generation is hours long, so a
    # cache that silently dropped them would only surface far too late.
    for before, after in zip(samples, restored):
        for field in ("connection_features", "connection_index",
                      "connection_kept", "connection_mask"):
            assert np.array_equal(getattr(before, field), getattr(after, field)), (
                f"{field} did not survive the cache round-trip"
            )
        assert int(after.connection_mask.sum()) == after.connections_total
        assert int(after.connection_kept.sum()) == after.connections_kept

    for before, after in zip(samples, restored):
        for field in ("graph_nodes", "graph_node_mask", "edge_index",
                      "edge_features", "edge_mask", "schedule_nodes",
                      "waits", "node_mask", "train_scalars", "train_mask"):
            assert np.array_equal(getattr(before, field), getattr(after, field))
        assert (before.all_arrived, before.bucket, before.total_delay,
                before.layout, before.source) == (
            after.all_arrived, after.bucket, after.total_delay,
            after.layout, after.source)


# ── scenario mixes ───────────────────────────────────────────────────

@pytest.mark.integration
def test_the_default_mix_is_the_one_the_shipped_models_trained_on():
    """`TRAINING_MIX` has to *be* the default, not merely describe it —
    otherwise a cached training set and a set regenerated from the named mix
    would silently be drawn from different distributions."""
    from app.policies.goal_based_policies.dataset import (
        TRAINING_MIX, ScenarioMix, generate_samples,
    )

    assert ScenarioMix() == TRAINING_MIX
    default = generate_samples(6, seed=4)
    named = generate_samples(6, seed=4, mix=TRAINING_MIX)
    assert [s.layout for s in default] == [s.layout for s in named]
    assert all(
        np.array_equal(a.graph_nodes, b.graph_nodes)
        for a, b in zip(default, named)
    )


def test_a_mix_rejects_settings_the_tensors_cannot_hold():
    """A mix asking for more trains than there are rows would not fail at
    generation — `encode_sample` would raise and the scenario would be
    skipped — so every scenario would be dropped and the caller would get a
    quietly empty set instead of an error."""
    from app.policies.goal_based_policies.dataset import MAX_TRAINS, ScenarioMix

    with pytest.raises(ValueError, match="MAX_TRAINS"):
        ScenarioMix(max_trains=MAX_TRAINS + 1)
    with pytest.raises(ValueError, match="min_trains"):
        ScenarioMix(min_trains=5, max_trains=3)
    with pytest.raises(ValueError, match="at least one size"):
        ScenarioMix(sizes=())
    with pytest.raises(ValueError, match="seed_range"):
        ScenarioMix(seed_range=(10, 5))


def test_a_mix_decides_the_scenarios_that_get_drawn():
    """The knobs have to actually reach the generator: a mix pinned to one
    seed, one size and one city count must produce one single network, and
    a pinned train count must appear in every scenario."""
    from app.policies.goal_based_policies.dataset import (
        ScenarioMix, generate_samples,
    )

    pinned = ScenarioMix(
        sizes=(30,), cities=(2,), min_trains=3, max_trains=3,
        seed_range=(4242, 4242),
    )
    samples = generate_samples(4, seed=5, mix=pinned)
    assert samples, "the pinned mix produced nothing to check"
    assert all(int(s.train_mask.sum()) == 3 for s in samples)
    first = samples[0]
    assert all(np.array_equal(s.graph_nodes, first.graph_nodes) for s in samples)


@pytest.mark.integration
def test_disjoint_seed_ranges_cannot_share_infrastructure():
    """This is what keeps an eval set honest: the guarantee that no eval
    scenario is built on a network the model trained on comes from the seed
    ranges not overlapping, not from hoping two RNG streams missed."""
    from app.policies.goal_based_policies.dataset import (
        TRAINING_MIX, ScenarioMix, generate_samples,
    )

    held_out = ScenarioMix(seed_range=(10_000_001, 20_000_000))
    assert not TRAINING_MIX.overlaps_seeds(held_out)
    assert not held_out.overlaps_seeds(TRAINING_MIX)
    assert TRAINING_MIX.overlaps_seeds(ScenarioMix(seed_range=(5_000_000, 15_000_000)))

    def networks(samples):
        return {s.graph_nodes.tobytes() for s in samples}

    trained_on = networks(generate_samples(8, seed=6))
    evaluated_on = networks(generate_samples(8, seed=6, mix=held_out))
    assert not trained_on & evaluated_on


def test_skipped_scenarios_are_counted_by_reason(monkeypatch):
    """A scenario dropped for hitting a tensor cap and one dropped because
    it could not be planned mean different things — the first says the set
    is quietly losing its hardest members — so they must not be lumped into
    one number."""
    from app.policies.goal_based_policies import dataset as dataset_module

    def refuse(*args, **kwargs):
        raise ValueError("nodes exceed MAX_NODES")

    monkeypatch.setattr(dataset_module, "encode_sample", refuse)
    samples, skipped = dataset_module.generate_samples_report(3, seed=7)
    assert samples == []
    assert skipped.get("encode", 0) > 0
    assert set(skipped) == {"encode"}


@pytest.mark.integration
def test_parallel_generation_carries_the_mix_to_its_workers():
    """Workers are spawned, so a mix reaches them only if it is part of the
    job — a default-constructed one in the child would silently generate the
    training distribution instead of the requested one."""
    from app.policies.goal_based_policies.dataset import (
        ScenarioMix, generate_samples_parallel,
    )

    mix = ScenarioMix(
        sizes=(30,), cities=(2,), min_trains=4, max_trains=4,
        seed_range=(10_000_001, 20_000_000),
    )
    samples = generate_samples_parallel(4, seed=12, workers=2, chunk_size=2, mix=mix)
    assert samples
    assert all(int(s.train_mask.sum()) == 4 for s in samples)


def _synthetic_sample(layout: int) -> Sample:
    """A minimal encoded scenario — `split_samples` only permutes the list,
    so the layout field is all that has to distinguish the samples."""
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
        layout=layout,
        all_arrived=1.0,
        bucket=0,
        total_delay=0,
    )


def test_split_is_deterministic_so_resumed_scores_compare():
    from app.policies.goal_based_policies.train_evaluator import split_samples

    samples = [_synthetic_sample(layout) for layout in range(20)]
    a_train, a_val = split_samples(samples, seed=3, val_fraction=0.2)
    b_train, b_val = split_samples(samples, seed=3, val_fraction=0.2)
    assert [s.layout for s in a_val] == [s.layout for s in b_val]
    assert [s.layout for s in a_train] == [s.layout for s in b_train]


@pytest.mark.integration
def test_block_training_resumes_and_stops_when_it_stops_improving(tmp_path):
    """Blocks continue while validation improves, the checkpoint carries the
    optimiser so a resumed run picks up rather than restarting, and the
    returned model is the best one seen."""
    from app.policies.goal_based_policies.train_evaluator import (
        load_checkpoint,
        train_until_no_improvement,
        validation_score,
    )

    samples = generate_samples(120, seed=7)
    checkpoint = str(tmp_path / "run.ckpt")

    model, report = train_until_no_improvement(
        samples=samples, checkpoint_path=checkpoint, block_epochs=5,
        max_blocks=3, seed=7, verbose=False,
    )
    assert Path(checkpoint).exists()
    _, payload = load_checkpoint(checkpoint)
    assert payload["epochs_done"] >= 5
    assert payload["optimiser"]["state"], "optimiser state must be saved"
    first_epochs = payload["epochs_done"]
    first_best = payload["best_score"]

    # The returned model is the checkpointed best, not a later worse one.
    assert validation_score(report.final) == pytest.approx(first_best, abs=1e-6)

    # Resuming continues from the stored epoch count rather than from zero.
    _, resumed_report = train_until_no_improvement(
        samples=samples, checkpoint_path=checkpoint, block_epochs=5,
        max_blocks=3, seed=7, verbose=False,
    )
    _, payload2 = load_checkpoint(checkpoint)
    assert payload2["epochs_done"] >= first_epochs
    assert payload2["best_score"] >= first_best
    assert resumed_report.epochs >= first_epochs


@pytest.mark.integration
def test_resuming_on_different_data_is_refused(tmp_path):
    """A checkpoint carries a data fingerprint: continuing against a
    different dataset would compare scores across different validation
    sets, so it must fail loudly instead."""
    from app.policies.goal_based_policies.train_evaluator import (
        train_until_no_improvement,
    )

    checkpoint = str(tmp_path / "run.ckpt")
    train_until_no_improvement(
        samples=generate_samples(60, seed=8), checkpoint_path=checkpoint,
        block_epochs=2, max_blocks=1, seed=8, verbose=False,
    )
    with pytest.raises(ValueError, match="different data"):
        train_until_no_improvement(
            samples=generate_samples(80, seed=9), checkpoint_path=checkpoint,
            block_epochs=2, max_blocks=1, seed=8, verbose=False,
        )


@pytest.mark.integration
def test_generated_samples_vary_in_size_source_and_outcome():
    samples = generate_samples(80, seed=3)
    assert len(samples) == 80
    for sample in samples:
        assert sample.bucket == delay_bucket(sample.total_delay)
        assert sample.all_arrived in (0.0, 1.0)

    # Problem size varies: trains per scenario and layouts used.
    assert len({int(s.train_mask.sum()) for s in samples}) >= 4
    assert len({s.layout for s in samples}) >= 4
    # All three schedule styles appear.
    styles = {s.source.split("+")[0] for s in samples}
    assert styles == {"shortest_path", "avoidance", "overlap_plan"}
    # And the labels are not degenerate.
    assert len({s.all_arrived for s in samples}) == 2
    assert len({s.bucket for s in samples}) >= 3

    stacked = stack_samples(samples)
    assert stacked[0].shape == (80, MAX_NODES, NODE_FEATURES)      # graph nodes
    assert stacked[2].shape == (80, MAX_EDGES, 2)                  # edge index
    assert stacked[5].shape == (80, MAX_TRAINS, MAX_SCHEDULE_NODES)  # schedules
    # The three scenario targets, indexed by position rather than from the
    # end: the per-connection block sits after them, so `stacked[-1]` is a
    # connection mask and would silently stop testing what this asserts.
    assert stacked[11].shape == (80,)                              # all_arrived
    assert stacked[12].shape == (80,)                              # delay bucket
    assert stacked[13].shape == (80,)                              # kept ratio
    assert stacked[-1].shape == (80, MAX_CONNECTIONS)              # connection mask


@pytest.mark.integration
def test_training_fits_the_data_it_is_given():
    """Plumbing check: with the graph in the observation the model must be
    able to learn its training set. Held-out accuracy needs far more data
    than a test can generate, so this asserts fit, not generalisation."""
    from app.policies.goal_based_policies.train_evaluator import _tensors, evaluate

    samples = generate_samples(120, seed=5)
    # Capacity check, so regularisation is off: dropout and weight decay
    # exist to stop the model fitting its training set, which is the very
    # thing under test here.
    model, report = train_evaluator(
        samples=samples, epochs=200, val_fraction=0.02, seed=5, verbose=False,
        dropout=0.0, weight_decay=0.0,
    )

    # The connection head is a ratio fitted with BCE, so its loss cannot
    # reach zero: the target's own entropy is a floor no model can beat.
    # Measure the reduction against that floor rather than against zero.
    ratios = np.clip(
        np.array([s.connections_kept_ratio for s in samples]), 1e-6, 1 - 1e-6
    )
    floor = float(np.mean(
        -(ratios * np.log(ratios) + (1 - ratios) * np.log(1 - ratios))
    ))
    first, last = report.history[0]["loss"], report.history[-1]["loss"]
    assert last < first, "loss did not fall at all"
    assert (last - floor) < 0.65 * (first - floor), (
        f"reducible loss only fell from {first - floor:.2f} to {last - floor:.2f}"
    )

    fit = evaluate(model, _tensors(samples))
    assert fit["arrival_accuracy"] > 0.80
    assert fit["bucket_macro_recall"] > 0.5
    # And the connection head must beat predicting the mean, or it has
    # learned nothing that the other two heads did not already give it.
    assert fit["connection_r2"] > 0.4
    assert fit["connection_mae"] < 0.2


@pytest.mark.integration
def test_unseen_layouts_can_be_scored():
    """The graph is an input, so a network never trained on still produces
    a usable prediction rather than an error."""
    pool = default_layouts(6, seed=0)
    train_samples = generate_samples(80, seed=5, layouts=pool[:4])
    unseen = generate_samples(20, seed=6, layouts=pool[4:])
    model, report = train_evaluator(
        samples=train_samples, epochs=30, seed=5, verbose=False, holdout=unseen
    )
    assert set(report.holdout) >= {"arrival_accuracy", "bucket_macro_recall"}
    assert 0.0 <= report.holdout["arrival_accuracy"] <= 1.0
