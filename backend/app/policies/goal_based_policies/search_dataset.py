"""Search-generated training samples.

The search produces plans systematically unlike the shortest-path /
avoidance / noise mixture the models learned from: holds chosen by score,
detours taken on purpose, conflicts traded against slack. A value model
asked to rank such plans must have seen them labelled — so every sample
here is one scenario planned by `director_plan` under one weight setting,
run to the end, and labelled with what actually happened. That is the
supervised half of the AlphaZero loop: search proposes, the episode
labels, the models retrain on both.

`source` records provenance as `"search:<weight-setting>"`, so training
can weigh or slice by it, and the eval report can tell a search plan from
a baseline one.

Scenarios draw from the *training* seed range by default — the point is
retraining data; the eval set must stay held out.
"""
from __future__ import annotations

import json
import random
from typing import Dict, List, Optional, Sequence, Tuple

from app.policies.goal_based_policies.connections import (
    evaluate_connections,
    observed_times,
    planned_connections,
    station_watch_cells,
)
from app.policies.goal_based_policies.dataset import (
    Layout,
    Sample,
    ScenarioMix,
    TRAINING_MIX,
    build_layout_env,
    encode_connections,
    encode_sample,
    plan_all_lines,
    save_samples,
)
from app.policies.goal_based_policies.ensemble import ScenarioContext
from app.policies.goal_based_policies.eval_set import mixes_by_name
from app.policies.goal_based_policies.infrastructure_graph import (
    build_decision_point_graph,
)
from app.policies.goal_based_policies.rollout import run_schedules
from app.policies.goal_based_policies.search import (
    SWEEP_WEIGHTS,
    SearchLimits,
    director_plan,
)
from app.policies.goal_based_policies.stations import resolve_stations


def _mix_by_name(name: str) -> ScenarioMix:
    if name == "training":
        return TRAINING_MIX
    return mixes_by_name([name])[0]


def generate_search_samples_report(
    count: int,
    seed: int,
    evaluator,
    connection_model,
    mix: ScenarioMix = TRAINING_MIX,
    weight_names: Optional[Sequence[str]] = None,
    limits: SearchLimits = SearchLimits(),
    strategy: str = "greedy",
    traces: Optional[List[Dict]] = None,
    verbose: bool = False,
) -> Tuple[List[Sample], Dict[str, int]]:
    """Labelled samples of Director-planned scenarios, plus skip reasons.

    Mirrors `generate_samples_report`'s skip vocabulary (`build`, `plan`,
    `encode`, `rollout`, `connections`) and adds `search` for a planner
    failure. The weight setting is drawn per scenario so one dataset
    covers the whole slider range.

    Pass a list as `traces` to also receive one record per accepted
    sample with the search's decision trace — the training data for the
    policy prior (`priors.py`;
    greedy/MCTS traces carry per-option scores and
    the chosen index; beam traces are step summaries).
    """
    names = list(weight_names or SWEEP_WEIGHTS)
    unknown = [n for n in names if n not in SWEEP_WEIGHTS]
    if unknown:
        raise ValueError(f"unknown weight settings: {unknown}")

    rng = random.Random(seed)
    samples: List[Sample] = []
    skipped: Dict[str, int] = {}
    attempts = 0

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    while len(samples) < count and attempts < count * 6:
        attempts += 1
        layout = Layout(
            index=attempts,
            seed=rng.randint(*mix.seed_range),
            size=rng.choice(mix.sizes),
            cities=rng.choice(mix.cities),
            line_length=mix.line_length,
        )
        trains = rng.randint(mix.min_trains, mix.max_trains)
        setting = rng.choice(names)
        try:
            env = build_layout_env(layout, trains)
            graph = build_decision_point_graph(env)
            stations = resolve_stations(env)
            base = plan_all_lines(env, graph)
        except Exception:
            skip("build")
            continue
        if base is None:
            skip("plan")
            continue

        try:
            plan = director_plan(
                env, graph, SWEEP_WEIGHTS[setting], evaluator,
                connection_model, limits=limits,
                context=ScenarioContext.build(env, graph),
                strategy=strategy,
            )
        except Exception:
            skip("search")
            continue

        source = f"search:{setting}"
        try:
            sample = encode_sample(
                env, graph, layout.index, plan.schedules, source=source
            )
        except Exception:
            skip("encode")
            continue
        sample.mix = mix.name
        try:
            connections = planned_connections(env, stations)
            result = run_schedules(
                env, graph, plan.schedules,
                watch_cells=station_watch_cells(stations),
            )
            report = evaluate_connections(
                connections, observed_times(stations, result.occupancy)
            )
        except Exception:
            skip("rollout")
            continue

        sample.all_arrived = float(result.all_arrived)
        sample.bucket = int(result.bucket)
        sample.total_delay = int(result.total_delay)
        sample.connections_total = int(report.total)
        sample.connections_kept = int(report.kept)
        try:
            ordered = sorted(graph.nodes)
            local = {graph.nodes[c].node_id: i for i, c in enumerate(ordered)}
            rows = {s.handle: r for r, s in enumerate(plan.schedules)}
            (sample.connection_features, sample.connection_index,
             sample.connection_kept, sample.connection_mask) = encode_connections(
                env, graph, stations, report.outcomes, local, rows)
        except Exception:
            skip("connections")
            continue
        samples.append(sample)
        if traces is not None:
            traces.append({
                "layout_seed": layout.seed,
                "trains": trains,
                "setting": setting,
                "strategy": strategy,
                "source": plan.source,
                "trace": plan.trace,
            })
        if verbose and len(samples) % 25 == 0:
            print(f"  {len(samples)}/{count} search samples", flush=True)

    return samples, skipped


# One model pair per worker process; maxtasksperchild=1 recycles the
# process per chunk, so the load cost amortises over the chunk size.
_MODEL_CACHE: Dict[Tuple[str, str], Tuple[object, object]] = {}


def _load_models(evaluator_path: str, connection_model_path: str):
    key = (evaluator_path, connection_model_path)
    if key not in _MODEL_CACHE:
        import torch

        from app.policies.goal_based_policies.connection_model import (
            ConnectionTransformer,
        )
        from app.policies.goal_based_policies.evaluator import ScheduleEvaluator

        torch.set_num_threads(1)  # workers parallelise scenarios, not GEMMs
        _MODEL_CACHE[key] = (
            ScheduleEvaluator.load(evaluator_path),
            ConnectionTransformer.load(connection_model_path),
        )
    return _MODEL_CACHE[key]


def _generate_search_chunk(job):
    """One worker's share. Top level so it can be pickled to a subprocess."""
    (count, seed, mix, evaluator_path, connection_model_path,
     weight_names, limits, strategy, want_traces) = job
    evaluator, connection_model = _load_models(
        evaluator_path, connection_model_path)
    traces: Optional[List[Dict]] = [] if want_traces else None
    samples, skipped = generate_search_samples_report(
        count, seed, evaluator, connection_model, mix=mix,
        weight_names=weight_names, limits=limits, strategy=strategy,
        traces=traces,
    )
    return samples, skipped, traces or []


def generate_search_samples_parallel_report(
    count: int,
    seed: int,
    evaluator_path: str,
    connection_model_path: str,
    mix: ScenarioMix = TRAINING_MIX,
    weight_names: Optional[Sequence[str]] = None,
    limits: SearchLimits = SearchLimits(),
    strategy: str = "greedy",
    traces: Optional[List[Dict]] = None,
    workers: Optional[int] = None,
    chunk_size: int = 10,
    verbose: bool = False,
) -> Tuple[List[Sample], Dict[str, int]]:
    """Collect in recycled worker processes — same memory rationale as
    `generate_samples_parallel_report`, with a smaller default chunk
    because one search sample costs seconds, not milliseconds."""
    import multiprocessing as mp
    import os

    if workers is None:
        workers = max(1, min(4, (os.cpu_count() or 2) - 2))
    jobs = []
    remaining, index = count, 0
    while remaining > 0:
        jobs.append((
            min(chunk_size, remaining), seed * 1_000_003 + index, mix,
            evaluator_path, connection_model_path,
            tuple(weight_names) if weight_names else None, limits,
            strategy, traces is not None,
        ))
        remaining -= jobs[-1][0]
        index += 1

    samples: List[Sample] = []
    skipped: Dict[str, int] = {}
    context = mp.get_context("spawn")
    with context.Pool(processes=workers, maxtasksperchild=1) as pool:
        for done, (chunk, chunk_skips, chunk_traces) in enumerate(
            pool.imap_unordered(_generate_search_chunk, jobs), 1
        ):
            samples.extend(chunk)
            if traces is not None:
                traces.extend(chunk_traces)
            for reason, hits in chunk_skips.items():
                skipped[reason] = skipped.get(reason, 0) + hits
            if verbose:
                print(f"  {len(samples)}/{count} search samples "
                      f"({done}/{len(jobs)} chunks)", flush=True)
    return samples[:count], skipped


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Collect Director-planned, rollout-labelled samples.")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--mix", default="training")
    parser.add_argument("--evaluator", required=True)
    parser.add_argument("--connection-model", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--weights", nargs="*", default=None,
                        help=f"subset of {list(SWEEP_WEIGHTS)}")
    parser.add_argument("--strategy", default="greedy",
                        choices=("greedy", "beam", "mcts"))
    parser.add_argument("--traces-out", default=None,
                        help="also write one decision-trace record per "
                             "sample to this jsonl (policy-prior data)")
    args = parser.parse_args(argv)

    traces: Optional[List[Dict]] = [] if args.traces_out else None
    samples, skipped = generate_search_samples_parallel_report(
        count=args.count,
        seed=args.seed,
        evaluator_path=args.evaluator,
        connection_model_path=args.connection_model,
        mix=_mix_by_name(args.mix),
        weight_names=args.weights,
        strategy=args.strategy,
        traces=traces,
        workers=args.workers,
        chunk_size=args.chunk_size,
        verbose=True,
    )
    if args.traces_out and traces is not None:
        with open(args.traces_out, "w", encoding="utf-8") as handle:
            for record in traces:
                handle.write(json.dumps(record) + "\n")
        print(f"traces: {len(traces)} -> {args.traces_out}")
    save_samples(args.out, samples)
    with open(f"{args.out}.skips.json", "w", encoding="utf-8") as handle:
        json.dump(skipped, handle, indent=2)
    sources: Dict[str, int] = {}
    for sample in samples:
        sources[sample.source] = sources.get(sample.source, 0) + 1
    print(f"saved {len(samples)} samples to {args.out}")
    print(f"sources: {sources}")
    print(f"skipped: {skipped}")
    return 0


__all__ = [
    "generate_search_samples_parallel_report",
    "generate_search_samples_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
