"""A held-out evaluation set drawn harder than the training distribution.

Both shipped models are validated on a random split of their own training
set, so every validation scenario comes from the same distribution as
training — different networks, but the same *kind* of problem. That measures
transfer across infrastructure and nothing else. It cannot answer the
question the HMI actually raises: does the prediction still hold when the
railway is busier than anything the model was fitted on?

This module builds that second set. It differs from training in two ways
that matter:

- **Disjoint by construction.** Every mix here draws its layout seeds from
  `EVAL_SEED_RANGE`, which does not intersect the range training used, so no
  eval scenario can be built on a network either model has seen. That is a
  guarantee from the generator, not an observation about two RNG streams.
- **Harder, and harder in named ways.** The set is a union of mixes, each
  turning one knob past where training went, and each sample remembers which
  mix drew it. A single aggregate number would say the model got worse
  without saying what made it worse, which is the part worth knowing.

    # build it (hours; generation is the cost, not scoring)
    python -m app.policies.goal_based_policies.eval_set \\
        --out hard_eval.npz --per-mix 500

    # score models on it
    python -m app.policies.goal_based_policies.eval_set \\
        --dataset hard_eval.npz \\
        --connection-model connection_model.pt \\
        --evaluator evaluator.pt --report eval.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.policies.goal_based_policies.dataset import (
    EVAL_MIXES,
    TRAINING_MIX,
    Sample,
    ScenarioMix,
    generate_samples_parallel_report,
    load_samples,
    save_samples,
)

# Skip reasons that mean a scenario was too big for the tensors rather than
# unplayable. These are the ones worth reporting: the scenarios that hit a
# cap are the largest and busiest, so losing them quietly would shave the
# hard tail off a set built specifically to contain it.
CAP_SKIPS = ("encode", "connections")


def mixes_by_name(names: Optional[Sequence[str]] = None) -> List[ScenarioMix]:
    """The requested eval mixes, defaulting to all of them."""
    available = {mix.name: mix for mix in EVAL_MIXES}
    if names is None:
        return list(EVAL_MIXES)
    unknown = [name for name in names if name not in available]
    if unknown:
        raise ValueError(
            f"unknown mix(es) {unknown}; available: {sorted(available)}"
        )
    return [available[name] for name in names]


def generate_eval_set(
    per_mix: int,
    seed: int = 0,
    workers: Optional[int] = None,
    chunk_size: int = 25,
    mixes: Optional[Sequence[ScenarioMix]] = None,
    verbose: bool = True,
) -> Tuple[List[Sample], Dict[str, Dict[str, int]]]:
    """`per_mix` scenarios from each mix, plus what each mix had to skip.

    Equal counts rather than proportional ones: the mixes are not samples of
    some population to be weighted, they are separate questions, and each
    needs enough scenarios to answer its own.
    """
    chosen = list(mixes) if mixes is not None else list(EVAL_MIXES)
    for mix in chosen:
        if TRAINING_MIX.overlaps_seeds(mix):
            raise ValueError(
                f"eval mix '{mix.name}' draws layout seeds from "
                f"{mix.seed_range}, which overlaps the training range "
                f"{TRAINING_MIX.seed_range}; it could be built on networks "
                "the model was trained on"
            )

    samples: List[Sample] = []
    skipped: Dict[str, Dict[str, int]] = {}
    for index, mix in enumerate(chosen):
        if verbose:
            print(f"\ngenerating {per_mix} '{mix.name}' scenarios "
                  f"({index + 1}/{len(chosen)}) ...", flush=True)
        # A seed per mix, so adding a mix later does not reshuffle the
        # scenarios already generated for the others.
        drawn, mix_skips = generate_samples_parallel_report(
            per_mix, seed=seed + 1_000 * (index + 1), workers=workers,
            chunk_size=chunk_size, mix=mix, verbose=verbose,
        )
        samples.extend(drawn)
        skipped[mix.name] = mix_skips
        capped = sum(mix_skips.get(reason, 0) for reason in CAP_SKIPS)
        if verbose and capped:
            print(f"  WARNING: {capped} '{mix.name}' scenarios exceeded a "
                  f"tensor cap and were dropped — this mix's scores are "
                  f"measured on {capped / max(1, capped + len(drawn)):.1%} "
                  "less than its hardest tail", flush=True)
    return samples, skipped


def describe(samples: Sequence[Sample]) -> Dict[str, float]:
    """What this slice of scenarios actually looks like."""
    if not samples:
        return {"scenarios": 0}
    connections = np.array(
        [int(s.connection_mask.sum()) if s.connection_mask is not None else 0
         for s in samples]
    )
    kept = float(sum(
        float(s.connection_kept.sum()) if s.connection_kept is not None else 0.0
        for s in samples
    ))
    total = int(connections.sum())
    return {
        "scenarios": len(samples),
        # Scenarios with no planned transfer still count toward the ratio
        # metric (trivially correct), so the split is worth seeing.
        "scenarios_with_connections": int((connections > 0).sum()),
        "trains_mean": float(np.mean([s.train_mask.sum() for s in samples])),
        "connections_total": total,
        "connections_per_scenario": float(connections.mean()),
        "connections_max": int(connections.max()),
        "kept_rate": kept / max(1, total),
        "all_arrived_rate": float(np.mean([s.all_arrived for s in samples])),
        "mean_bucket": float(np.mean([s.bucket for s in samples])),
    }


def score_connection_model(model, samples: Sequence[Sample]) -> Dict[str, float]:
    """Per-connection scores for the transformer, on this slice.

    Every scenario is passed, including those with no planned transfer, so
    the numbers mean the same thing they do in training: `scenario_ratio_mae`
    scores a connection-free scenario as a correct 1.0, and dropping those
    here would inflate it against the figure the model was selected on.
    Per-connection accuracy and AUC read only the real rows either way.
    """
    from app.policies.goal_based_policies.train_connection_model import (
        _tensors, evaluate,
    )

    if not samples:
        return {}
    return evaluate(model, _tensors(samples))


# Fraction of transfers kept in the training set the shipped connection
# model was fitted on (12k scenarios, 164,984 connections). A constant
# predictor calibrated on training would emit exactly this everywhere, which
# is the fair "learned nothing transferable" floor for a held-out set.
TRAINING_BASE_RATE = 0.3556


def connection_baseline(
    samples: Sequence[Sample], base_rate: float = TRAINING_BASE_RATE
) -> Dict[str, float]:
    """What a model that learned nothing transferable would score here.

    Two floors, because they answer different questions. Predicting the
    *training* base rate is what a constant model carried over from training
    does, and is directly comparable with the baseline the model was
    selected against. Predicting this slice's own majority class is the
    accuracy floor an oracle-calibrated constant reaches — and on a mix
    where only a fifth of transfers survive, that floor is high enough that
    raw accuracy stops meaning anything.
    """
    labels = np.concatenate([
        s.connection_kept[s.connection_mask > 0]
        for s in samples
        if s.connection_kept is not None and s.connection_mask is not None
        and s.connection_mask.sum() > 0
    ]) if samples else np.array([])
    if labels.size == 0:
        return {}

    ratios = np.array([
        (float(s.connection_kept.sum()) / float(s.connection_mask.sum()))
        if (s.connection_mask is not None and s.connection_mask.sum() > 0)
        else 1.0
        for s in samples
    ])
    kept = float(labels.mean())
    return {
        "kept_rate": kept,
        "majority_accuracy": float(max(kept, 1.0 - kept)),
        "training_rate_accuracy": float(
            ((base_rate >= 0.5) == (labels > 0.5)).mean()),
        "training_rate_brier": float(((base_rate - labels) ** 2).mean()),
        "training_rate_ratio_mae": float(np.abs(ratios - base_rate).mean()),
        "auc": 0.5,
    }


def score_evaluator(model, samples: Sequence[Sample]) -> Dict[str, float]:
    """Arrival, delay-bucket and aggregate-ratio scores for the delay model."""
    from app.policies.goal_based_policies.train_evaluator import (
        _tensors, evaluate,
    )

    if not samples:
        return {}
    return evaluate(model, _tensors(samples))


def report(
    samples: Sequence[Sample],
    connection_model=None,
    evaluator=None,
) -> Dict[str, object]:
    """Scores overall and per mix.

    Per mix is the point: the mixes turn different knobs, so an aggregate
    would average away exactly the signal the set was built to produce.
    """
    groups: Dict[str, List[Sample]] = {}
    for sample in samples:
        groups.setdefault(sample.mix, []).append(sample)

    def block(slice_: Sequence[Sample]) -> Dict[str, object]:
        out: Dict[str, object] = {
            "data": describe(slice_),
            "baseline": connection_baseline(slice_),
        }
        if connection_model is not None:
            out["connection_model"] = score_connection_model(connection_model, slice_)
        if evaluator is not None:
            out["evaluator"] = score_evaluator(evaluator, slice_)
        return out

    return {
        "overall": block(samples),
        "by_mix": {name: block(group) for name, group in sorted(groups.items())},
    }


def _print_table(payload: Dict[str, object]) -> None:
    """Compact per-mix view; the JSON report carries everything."""
    rows = [("overall", payload["overall"])]
    rows += sorted(payload["by_mix"].items())  # type: ignore[arg-type]
    header = (f"{'mix':<12}{'n':>6}{'conn':>7}{'kept':>7}{'arr':>6}"
              f"{'auc':>8}{'acc':>7}{'(floor)':>9}{'ratioMAE':>10}"
              f"{'(floor)':>9}{'bucket':>8}")
    print("\n" + header)
    print("-" * len(header))
    for name, block in rows:
        data = block["data"]                        # type: ignore[index]
        base = block.get("baseline") or {}          # type: ignore[union-attr]
        conn = block.get("connection_model") or {}  # type: ignore[union-attr]
        delay = block.get("evaluator") or {}        # type: ignore[union-attr]
        nan = float("nan")
        print(
            f"{name:<12}{data['scenarios']:>6}"
            f"{data.get('connections_per_scenario', 0):>7.1f}"
            f"{data.get('kept_rate', 0):>7.3f}"
            f"{data.get('all_arrived_rate', 0):>6.2f}"
            f"{conn.get('connection_auc', nan):>8.3f}"
            f"{conn.get('connection_accuracy', nan):>7.3f}"
            f"{base.get('majority_accuracy', nan):>9.3f}"
            f"{conn.get('scenario_ratio_mae', nan):>10.3f}"
            f"{base.get('training_rate_ratio_mae', nan):>9.3f}"
            f"{delay.get('bucket_accuracy', nan):>8.3f}"
        )
    print("\n'(floor)' columns are what a constant predictor scores: the "
          "majority class for accuracy,\nthe training base rate for the "
          "ratio. AUC's floor is 0.5 everywhere.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=str, default=None,
        help="eval set to score; built and cached here if it does not exist")
    parser.add_argument("--out", type=str, default=None, help="alias for --dataset")
    parser.add_argument("--per-mix", type=int, default=500)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--chunk-size", type=int, default=25)
    parser.add_argument(
        "--mix", action="append", default=None,
        help="restrict to this mix (repeatable); default is all of them")
    parser.add_argument("--connection-model", type=str, default=None)
    parser.add_argument("--evaluator", type=str, default=None)
    parser.add_argument("--report", type=str, default=None)
    args = parser.parse_args(argv)

    path = args.dataset or args.out
    if not path:
        parser.error("need --dataset (or --out) to say where the eval set lives")

    # Skips live beside the set rather than inside it: they describe
    # scenarios that are *absent*, so there is no row to attach them to, and
    # scoring a set without knowing what it lost is how a cap silently turns
    # into a flattering number.
    skips_path = Path(path).with_suffix(".skips.json")
    if Path(path).exists():
        print(f"loading eval set {path} ...", flush=True)
        samples = load_samples(path)
        skipped = (json.loads(skips_path.read_text())
                   if skips_path.exists() else {})
    else:
        samples, skipped = generate_eval_set(
            per_mix=args.per_mix, seed=args.seed, workers=args.workers,
            chunk_size=args.chunk_size, mixes=mixes_by_name(args.mix),
        )
        save_samples(path, samples)
        skips_path.write_text(json.dumps(skipped, indent=2))
        print(f"\ncached eval set to {path} (skips: {skips_path})", flush=True)

    print(f"  {len(samples)} scenarios from mixes "
          f"{sorted({s.mix for s in samples})}", flush=True)
    capped = {
        name: {r: c for r, c in reasons.items() if r in CAP_SKIPS}
        for name, reasons in skipped.items()
        if any(r in CAP_SKIPS for r in reasons)
    }
    if capped:
        print(f"  scenarios dropped for exceeding a tensor cap: {capped}",
              flush=True)

    connection_model = evaluator = None
    if args.connection_model:
        from app.policies.goal_based_policies.connection_model import (
            ConnectionTransformer,
        )
        connection_model = ConnectionTransformer.load(args.connection_model)
    if args.evaluator:
        from app.policies.goal_based_policies.evaluator import ScheduleEvaluator
        evaluator = ScheduleEvaluator.load(args.evaluator)

    payload = report(samples, connection_model, evaluator)
    payload["skipped"] = skipped
    _print_table(payload)
    if args.report:
        with open(args.report, "w") as handle:
            json.dump(payload, handle, indent=2)
        print(f"\nreport: {args.report}")
    return 0


__all__ = [
    "CAP_SKIPS",
    "TRAINING_BASE_RATE",
    "connection_baseline",
    "describe",
    "generate_eval_set",
    "mixes_by_name",
    "report",
    "score_connection_model",
    "score_evaluator",
]


if __name__ == "__main__":
    raise SystemExit(main())
