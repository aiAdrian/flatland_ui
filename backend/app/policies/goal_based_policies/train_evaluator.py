"""Train the schedule evaluator on simulated rollouts.

Targets come from actually running each schedule in Flatland
(`rollout.run_schedules`), so this is supervised training on measured
outcomes: binary cross-entropy for "all trains arrived" and an ordinal
cross-entropy over the six delay buckets — the buckets are ordered, so the
target distribution leaks a little mass to the neighbouring buckets and a
near miss costs less than a distant one.

    python -m app.policies.goal_based_policies.train_evaluator \
        --dataset-cache data.npz --block-epochs 50 --out schedule_evaluator.pt

Training runs in resumable blocks (`--block-epochs`), continuing while the
validation score improves; rerunning the same command picks up from the
checkpoint next to `--out`.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch import nn

from app.policies.goal_based_policies import block_training
from app.policies.goal_based_policies.block_training import EVAL_CHUNK, LONG_FIELDS
from app.policies.goal_based_policies.dataset import (
    Sample,
    generate_samples,
    generate_samples_parallel,
    load_samples,
    save_samples,
    stack_samples,
)
from app.policies.goal_based_policies.evaluator import ScheduleEvaluator
from app.policies.goal_based_policies.rollout import (
    DELAY_BUCKET_LABELS,
    NUM_DELAY_BUCKETS,
)


@dataclass
class TrainingReport:
    epochs: int
    train_size: int
    val_size: int
    history: List[Dict[str, float]] = field(default_factory=list)
    final: Dict[str, float] = field(default_factory=dict)
    baseline: Dict[str, float] = field(default_factory=dict)
    holdout: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "epochs": self.epochs,
            "train_size": self.train_size,
            "val_size": self.val_size,
            "final": self.final,
            "baseline": self.baseline,
            "holdout_unseen_layouts": self.holdout,
            "history": self.history,
        }


# Field order everywhere below: the model inputs, then the three targets
# (all_arrived, delay bucket, connections-kept ratio).
INPUT_FIELDS = 11


def _tensors(samples: Sequence[Sample], device: str = "cpu"):
    stacked = stack_samples(samples)
    inputs = tuple(
        torch.tensor(
            field,
            dtype=torch.long if index in LONG_FIELDS else torch.float32,
            device=device,
        )
        for index, field in enumerate(stacked[:INPUT_FIELDS])
    )
    return inputs + (
        torch.tensor(stacked[INPUT_FIELDS], dtype=torch.float32, device=device),
        torch.tensor(stacked[INPUT_FIELDS + 1], dtype=torch.long, device=device),
        torch.tensor(stacked[INPUT_FIELDS + 2], dtype=torch.float32, device=device),
    )


def _majority_baseline(
    train_samples: Sequence[Sample], val_samples: Sequence[Sample]
) -> Dict[str, float]:
    """What always predicting the training majority would score.

    Accuracy is meaningless without this: if 80% of scenarios succeed, an
    80% arrival accuracy is worth nothing.
    """
    arrived_majority = float(
        np.mean([s.all_arrived for s in train_samples]) >= 0.5
    )
    counts = np.bincount(
        [s.bucket for s in train_samples], minlength=NUM_DELAY_BUCKETS
    )
    bucket_majority = int(counts.argmax())
    val_buckets = np.array([s.bucket for s in val_samples])
    return {
        "arrival_accuracy": float(
            np.mean([s.all_arrived == arrived_majority for s in val_samples])
        ),
        "bucket_accuracy": float(np.mean(val_buckets == bucket_majority)),
        # Always guessing one class gets one class right and five wrong.
        "bucket_macro_recall": 1.0 / NUM_DELAY_BUCKETS,
        "bucket_mean_error": float(np.mean(np.abs(val_buckets - bucket_majority))),
        # Always predicting the training mean connection ratio.
        "connection_mae": float(np.mean(np.abs(
            np.array([s.connections_kept_ratio for s in val_samples])
            - float(np.mean([s.connections_kept_ratio for s in train_samples]))
        ))),
        "connection_r2": 0.0,
    }


@torch.no_grad()
def evaluate(
    model: ScheduleEvaluator, batch, chunk_size: int = EVAL_CHUNK
) -> Dict[str, float]:
    *inputs, arrived, bucket, connections = batch
    model.eval()

    arrival_parts, delay_parts, connection_parts = [], [], []
    for start in range(0, arrived.shape[0], max(1, chunk_size)):
        stop = start + max(1, chunk_size)
        a, d, c = model(*(field[start:stop] for field in inputs))
        arrival_parts.append(a)
        delay_parts.append(d)
        connection_parts.append(c)
    arrival_logit = torch.cat(arrival_parts)
    delay_logits = torch.cat(delay_parts)
    connection_logit = torch.cat(connection_parts)

    connection_pred = torch.sigmoid(connection_logit)
    arrival_pred = (torch.sigmoid(arrival_logit) >= 0.5).float()
    bucket_pred = delay_logits.argmax(dim=-1)
    distance = (bucket_pred - bucket).abs()

    # Macro recall: the losses are class weighted, so plain accuracy would
    # undersell a model that handles the rare, large-delay buckets.
    recalls = []
    for klass in range(NUM_DELAY_BUCKETS):
        present = bucket == klass
        if present.any():
            recalls.append(bucket_pred[present].eq(klass).float().mean().item())
    return {
        "arrival_accuracy": arrival_pred.eq(arrived).float().mean().item(),
        "bucket_accuracy": bucket_pred.eq(bucket).float().mean().item(),
        "bucket_within_one": (distance <= 1).float().mean().item(),
        "bucket_macro_recall": float(np.mean(recalls)) if recalls else 0.0,
        "bucket_mean_error": distance.float().mean().item(),
        # Connections kept is a ratio, so it is scored as regression: mean
        # absolute error, plus R^2 against predicting the mean, which is the
        # only way to see whether it beats a constant.
        "connection_mae": (connection_pred - connections).abs().mean().item(),
        "connection_r2": _r_squared(connection_pred, connections),
    }


def _r_squared(prediction: torch.Tensor, target: torch.Tensor) -> float:
    """1 - SSE/SST. Zero means no better than always predicting the mean."""
    total = ((target - target.mean()) ** 2).sum()
    if total.item() <= 0:
        return 0.0
    return float(1.0 - ((prediction - target) ** 2).sum() / total)


def split_samples(
    samples: Sequence[Sample], seed: int, val_fraction: float
) -> Tuple[List[Sample], List[Sample]]:
    """Deterministic train/validation split.

    Deterministic matters for resuming: a continued run must land on exactly
    the same validation set, or its scores would not be comparable with the
    ones that decided to continue.
    """
    order = np.random.default_rng(seed).permutation(len(samples))
    shuffled = [samples[i] for i in order]
    split = max(1, int(len(shuffled) * (1 - val_fraction)))
    train_samples, val_samples = shuffled[:split], shuffled[split:]
    if not val_samples:
        val_samples = train_samples[-1:]
    return train_samples, val_samples


# Probability mass the bucket target leaks to its neighbours. The buckets
# are ordered and 81% of the model's misses are off by one, so a bit of
# neighbour mass turns near misses into usable gradient instead of treating
# them like five-bucket blunders.
BUCKET_NEIGHBOUR_SMOOTHING = 0.15


class OrdinalBucketLoss(nn.Module):
    """Class-weighted cross-entropy against neighbour-smoothed targets.

    Matches `nn.CrossEntropyLoss(weight=...)` semantics — the per-sample loss
    is weighted by the true class and normalised by the summed weights — but
    the target is a distribution putting `1 - smoothing` on the true bucket
    and the rest on its immediate neighbours (all of it on the single
    neighbour at the ends of the scale).
    """

    def __init__(
        self,
        class_weights: torch.Tensor,
        smoothing: float = BUCKET_NEIGHBOUR_SMOOTHING,
    ):
        super().__init__()
        buckets = class_weights.shape[0]
        targets = torch.zeros(buckets, buckets)
        for bucket in range(buckets):
            neighbours = [n for n in (bucket - 1, bucket + 1) if 0 <= n < buckets]
            targets[bucket, bucket] = 1.0 - smoothing
            for neighbour in neighbours:
                targets[bucket, neighbour] = smoothing / len(neighbours)
        self.register_buffer("soft_targets", targets)
        self.register_buffer("class_weights", class_weights)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        log_probs = torch.log_softmax(logits, dim=-1)
        per_sample = -(self.soft_targets[targets] * log_probs).sum(dim=-1)
        weights = self.class_weights[targets]
        return (weights * per_sample).sum() / weights.sum().clamp(min=1e-8)


def _build_losses(train_batch):
    """Class-weighted losses for the three heads."""
    arrived = train_batch[INPUT_FIELDS]
    positives = arrived.sum().clamp(min=1.0)
    negatives = (1 - arrived).sum().clamp(min=1.0)
    arrival_loss = nn.BCEWithLogitsLoss(pos_weight=negatives / positives)
    counts = torch.bincount(
        train_batch[INPUT_FIELDS + 1], minlength=NUM_DELAY_BUCKETS
    ).float()
    bucket_loss = OrdinalBucketLoss(
        (counts.sum() / counts.clamp(min=1.0)).clamp(max=20.0)
    )
    # The connection target is a ratio in [0, 1], so binary cross-entropy on
    # the logit fits it directly and keeps predictions in range; no class
    # weighting, because it is not a class.
    connection_loss = nn.BCEWithLogitsLoss()
    return arrival_loss, bucket_loss, connection_loss


def _run_epoch(
    model, optimiser, train_batch, losses, batch_size, rng, device
) -> float:
    arrival_loss, bucket_loss, connection_loss = losses
    model.train()
    indices = np.arange(train_batch[0].shape[0])
    rng.shuffle(indices)
    total = 0.0
    for start in range(0, len(indices), batch_size):
        chunk = torch.tensor(indices[start:start + batch_size], device=device)
        arrival_logit, delay_logits, connection_logit = model(
            *(field[chunk] for field in train_batch[:INPUT_FIELDS])
        )
        loss = (
            arrival_loss(arrival_logit, train_batch[INPUT_FIELDS][chunk])
            + bucket_loss(delay_logits, train_batch[INPUT_FIELDS + 1][chunk])
            + connection_loss(connection_logit, train_batch[INPUT_FIELDS + 2][chunk])
        )
        optimiser.zero_grad()
        loss.backward()
        optimiser.step()
        total += loss.item() * len(chunk)
    return total / max(1, len(indices))


def validation_score(metrics: Dict[str, float]) -> float:
    """One number to decide whether to keep training.

    The model has three jobs — whether the trains arrive, how late, and
    how many passenger connections survive —
    so the score averages one metric from each head. Macro recall is used
    for the buckets because the losses are class weighted, and plain
    accuracy would let the model coast on the biggest bucket. The
    connection head contributes `1 - MAE`, putting it on the same
    higher-is-better [0, 1] scale as the other two.
    """
    return (
        metrics["arrival_accuracy"]
        + metrics["bucket_macro_recall"]
        + (1.0 - min(1.0, metrics["connection_mae"]))
    ) / 3.0


def load_checkpoint(path: str, device: str = "cpu"):
    """Restore model, optimiser and progress. Returns (model, payload)."""
    return block_training.load_checkpoint(path, ScheduleEvaluator, device)


def train_until_no_improvement(
    samples: Sequence[Sample],
    checkpoint_path: str,
    block_epochs: int = 50,
    max_blocks: int = 40,
    batch_size: int = 64,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-4,
    dropout: float = 0.1,
    val_fraction: float = 0.2,
    seed: int = 0,
    device: str = "cpu",
    patience: int = 1,
    resume: bool = True,
    verbose: bool = True,
) -> Tuple[ScheduleEvaluator, TrainingReport]:
    """Resumable block training for the evaluator.

    The loop itself — checkpoint resume, dataset-fingerprint guard, blocks
    while the validation score improves, best-checkpoint restore — lives in
    `block_training.train_in_blocks`; this wrapper supplies the evaluator's
    losses, metrics and validation score.
    """
    if len(samples) < 8:
        raise ValueError(f"need at least 8 samples to train, got {len(samples)}")

    torch.manual_seed(seed)
    train_samples, val_samples = split_samples(samples, seed, val_fraction)
    train_batch = _tensors(train_samples, device)
    val_batch = _tensors(val_samples, device)
    losses = _build_losses(train_batch)

    fingerprint = {
        "samples": len(samples),
        "seed": seed,
        "val_fraction": val_fraction,
        "edge_features": int(train_batch[3].shape[-1]),
        "stop_flags": int(train_batch[8].shape[-1]),
        "train_scalars": int(train_batch[9].shape[-1]),
    }

    model, epochs, history = block_training.train_in_blocks(
        checkpoint_path=checkpoint_path,
        model_cls=ScheduleEvaluator,
        build_model=lambda: ScheduleEvaluator(dropout=dropout).to(device),
        run_epoch=lambda net, optimiser, rng: _run_epoch(
            net, optimiser, train_batch, losses, batch_size, rng, device
        ),
        evaluate_model=lambda net: evaluate(net, val_batch),
        validation_score=validation_score,
        format_metrics=lambda m: (
            f"arrival {m['arrival_accuracy']:.3f}  "
            f"bucket {m['bucket_accuracy']:.3f}  "
            f"macro {m['bucket_macro_recall']:.3f}  "
            f"conn_mae {m['connection_mae']:.3f}  "
            f"conn_r2 {m['connection_r2']:.3f}"
        ),
        fingerprint=fingerprint,
        block_epochs=block_epochs,
        max_blocks=max_blocks,
        learning_rate=learning_rate,
        weight_decay=weight_decay,
        seed=seed,
        patience=patience,
        device=device,
        resume=resume,
        verbose=verbose,
        checkpoint_extra={"bucket_labels": list(DELAY_BUCKET_LABELS)},
    )

    report = TrainingReport(
        epochs=epochs,
        train_size=len(train_samples),
        val_size=len(val_samples),
        baseline=_majority_baseline(train_samples, val_samples),
    )
    report.history = history
    report.final = evaluate(model, val_batch)
    return model, report


def train_evaluator(
    samples: Optional[Sequence[Sample]] = None,
    sample_count: int = 2000,
    epochs: int = 30,
    batch_size: int = 64,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-4,
    dropout: float = 0.1,
    val_fraction: float = 0.2,
    seed: int = 0,
    device: str = "cpu",
    verbose: bool = True,
    holdout: Optional[Sequence[Sample]] = None,
) -> Tuple[ScheduleEvaluator, TrainingReport]:
    torch.manual_seed(seed)
    if samples is None:
        samples = generate_samples(sample_count, seed=seed)
    if len(samples) < 8:
        raise ValueError(f"need at least 8 samples to train, got {len(samples)}")

    train_samples, val_samples = split_samples(samples, seed, val_fraction)
    train_batch = _tensors(train_samples, device)
    val_batch = _tensors(val_samples, device)
    losses = _build_losses(train_batch)

    model = ScheduleEvaluator(dropout=dropout).to(device)
    optimiser = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimiser, T_max=max(1, epochs)
    )

    report = TrainingReport(
        epochs=epochs,
        train_size=len(train_samples),
        val_size=len(val_samples),
        baseline=_majority_baseline(train_samples, val_samples),
    )

    rng = np.random.default_rng(seed)
    for epoch in range(1, epochs + 1):
        epoch_loss = _run_epoch(
            model, optimiser, train_batch, losses, batch_size, rng, device
        )
        scheduler.step()
        metrics = evaluate(model, val_batch)
        metrics["loss"] = epoch_loss
        metrics["epoch"] = epoch
        report.history.append(metrics)
        if verbose and (epoch % 5 == 0 or epoch == 1 or epoch == epochs):
            print(
                f"epoch {epoch:3d}  loss {metrics['loss']:.4f}  "
                f"arrival {metrics['arrival_accuracy']:.3f}  "
                f"bucket {metrics['bucket_accuracy']:.3f}  "
                f"macro {metrics['bucket_macro_recall']:.3f}  "
                f"±1 bucket {metrics['bucket_within_one']:.3f}  "
                f"conn_mae {metrics['connection_mae']:.3f}", flush=True,
            )

    report.final = evaluate(model, val_batch)
    if holdout:
        # Scenarios on layouts the model never trained on: the real test of
        # whether the graph encoder learned structure rather than identity.
        report.holdout = evaluate(model, _tensors(holdout, device))
    return model, report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=str, default="schedule_evaluator.pt")
    parser.add_argument("--report", type=str, default=None)
    parser.add_argument(
        "--dataset-cache", type=str, default=None,
        help="npz file to store/reuse the generated scenarios, so a "
             "continued run does not rebuild them",
    )
    parser.add_argument(
        "--block-epochs", type=int, default=0,
        help="train in blocks of this many epochs, continuing while the "
             "validation score improves (0 = fixed --epochs run)",
    )
    parser.add_argument("--max-blocks", type=int, default=40)
    parser.add_argument(
        "--patience", type=int, default=1,
        help="stop after this many consecutive blocks without improvement",
    )
    parser.add_argument(
        "--checkpoint", type=str, default=None,
        help="resumable checkpoint (defaults to --out with .ckpt suffix)",
    )
    parser.add_argument("--fresh", action="store_true", help="ignore any checkpoint")
    parser.add_argument(
        "--workers", type=int, default=None,
        help="parallel generation workers (default: cores - 2, capped at 4). "
             "Each is recycled per chunk to bound memory.",
    )
    args = parser.parse_args(argv)

    # Every scenario is built on its own network, so the validation split is
    # automatically made of infrastructure the model has never trained on —
    # no separate holdout pool is needed to measure transfer.
    cache = args.dataset_cache
    if cache and Path(cache).exists():
        print(f"loading cached dataset {cache} ...")
        samples = load_samples(cache)
    else:
        print(f"generating {args.samples} samples by running schedules ...")
        samples = generate_samples_parallel(
            args.samples, seed=args.seed, workers=args.workers, verbose=True
        )
        if cache:
            save_samples(cache, samples)
            print(f"  cached dataset to {cache}")
    print(f"  {len({s.layout for s in samples})} distinct networks "
          f"across {len(samples)} scenarios")
    print(f"  got {len(samples)} labelled scenarios")
    distribution = np.bincount(
        [s.bucket for s in samples], minlength=NUM_DELAY_BUCKETS
    )
    for label, count in zip(DELAY_BUCKET_LABELS, distribution):
        print(f"  bucket {label:>6}: {count}")
    print(f"  all trains arrived: {np.mean([s.all_arrived for s in samples]):.1%}")
    sources: Dict[str, int] = {}
    for sample in samples:
        sources[sample.source] = sources.get(sample.source, 0) + 1
    for name, count in sorted(sources.items()):
        print(f"  source {name:22s}: {count}")

    if args.block_epochs > 0:
        checkpoint = args.checkpoint or (str(Path(args.out).with_suffix(".ckpt")))
        model, report = train_until_no_improvement(
            samples=samples,
            checkpoint_path=checkpoint,
            block_epochs=args.block_epochs,
            max_blocks=args.max_blocks,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            dropout=args.dropout,
            seed=args.seed,
            patience=args.patience,
            resume=not args.fresh,
        )
        print(f"\ncheckpoint: {checkpoint} (epoch {report.epochs})")
    else:
        model, report = train_evaluator(
            samples=samples,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            dropout=args.dropout,
            seed=args.seed,
        )
    print("\nvalidation (every network unseen):", json.dumps(report.final, indent=2))
    print("majority baseline:", json.dumps(report.baseline, indent=2))
    print("saved:", model.save(args.out))
    if args.report:
        with open(args.report, "w") as handle:
            json.dump(report.to_dict(), handle, indent=2)
        print("report:", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
