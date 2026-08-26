"""Train the per-connection transformer on measured transfer outcomes.

Each planned transfer is one training example, labelled by whether it
survived the rollout (`connections.evaluate_connections`). That is a much
denser signal than the delay evaluator's one-scalar-per-scenario: a
scenario with 60 connections contributes 60 labels.

    python -m app.policies.goal_based_policies.train_connection_model \
        --dataset-cache data.npz --block-epochs 25 --out connection_model.pt

Scored two ways, because they answer different questions:

- **per connection** — accuracy, and ROC AUC. AUC is the one to watch: the
  label is imbalanced and ranking which transfers are at risk is what the
  HMI actually needs, so a model that ranks well but is miscalibrated is
  still useful, while one that predicts the majority class is not.
- **per scenario** — MAE of the predicted kept-ratio against the measured
  one, so this model stays comparable with the delay evaluator's
  connection head, which predicts that ratio directly.
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
from app.policies.goal_based_policies.connection_model import ConnectionTransformer
from app.policies.goal_based_policies.dataset import (
    Sample,
    generate_samples_parallel,
    load_samples,
    save_samples,
    stack_samples,
)
from app.policies.goal_based_policies.train_evaluator import split_samples

# stack_samples order: 11 model inputs, 3 scenario targets, then the
# per-connection block. The connection model consumes the 11 inputs plus
# features/index/mask, and is trained against `kept`.
SCENARIO_INPUTS = 11
CONNECTION_FEATURES_FIELD = 14
CONNECTION_INDEX_FIELD = 15
CONNECTION_KEPT_FIELD = 16
CONNECTION_MASK_FIELD = 17


@dataclass
class ConnectionReport:
    epochs: int
    train_size: int
    val_size: int
    train_connections: int
    val_connections: int
    history: List[Dict[str, float]] = field(default_factory=list)
    final: Dict[str, float] = field(default_factory=dict)
    baseline: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "epochs": self.epochs,
            "train_size": self.train_size,
            "val_size": self.val_size,
            "train_connections": self.train_connections,
            "val_connections": self.val_connections,
            "final": self.final,
            "baseline": self.baseline,
            "history": self.history,
        }


def _tensors(samples: Sequence[Sample], device: str = "cpu"):
    """Model inputs, then (kept label, connection mask)."""
    stacked = stack_samples(samples)
    inputs = [
        torch.tensor(
            stacked[index],
            dtype=torch.long if index in LONG_FIELDS else torch.float32,
            device=device,
        )
        for index in range(SCENARIO_INPUTS)
    ]
    inputs.append(torch.tensor(
        stacked[CONNECTION_FEATURES_FIELD], dtype=torch.float32, device=device))
    inputs.append(torch.tensor(
        stacked[CONNECTION_INDEX_FIELD], dtype=torch.long, device=device))
    mask = torch.tensor(
        stacked[CONNECTION_MASK_FIELD], dtype=torch.float32, device=device)
    inputs.append(mask)
    kept = torch.tensor(
        stacked[CONNECTION_KEPT_FIELD], dtype=torch.float32, device=device)
    return tuple(inputs), kept, mask


def _roc_auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """AUC by rank, ties averaged. 0.5 means no better than chance."""
    positives = labels.sum()
    negatives = labels.size - positives
    if positives == 0 or negatives == 0:
        return 0.5
    order = scores.argsort()
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, scores.size + 1)
    # Average ranks within tied score groups, or AUC is inflated by ties.
    unique, inverse, counts = np.unique(scores, return_inverse=True, return_counts=True)
    summed = np.zeros(unique.size)
    np.add.at(summed, inverse, ranks)
    ranks = (summed / counts)[inverse]
    return float((ranks[labels > 0].sum() - positives * (positives + 1) / 2)
                 / (positives * negatives))


@torch.no_grad()
def evaluate(
    model: ConnectionTransformer, batch, chunk_size: int = EVAL_CHUNK
) -> Dict[str, float]:
    """Per-connection and per-scenario scores over real connections only."""
    inputs, kept, mask = batch
    model.eval()
    parts = []
    for start in range(0, kept.shape[0], max(1, chunk_size)):
        stop = start + max(1, chunk_size)
        parts.append(model(*(field[start:stop] for field in inputs)))
    logits = torch.cat(parts)
    probability = torch.sigmoid(logits)

    real = mask > 0
    if not real.any():
        return {"connection_accuracy": 0.0, "connection_auc": 0.5,
                "connection_brier": 0.0, "scenario_ratio_mae": 0.0}
    flat_p = probability[real].cpu().numpy()
    flat_y = kept[real].cpu().numpy()

    # Scenario ratio: mean probability over that scenario's real rows.
    counted = mask.sum(dim=1)
    predicted_ratio = torch.where(
        counted > 0, (probability * mask).sum(dim=1) / counted.clamp(min=1.0),
        torch.ones_like(counted))
    measured_ratio = torch.where(
        counted > 0, (kept * mask).sum(dim=1) / counted.clamp(min=1.0),
        torch.ones_like(counted))
    return {
        "connection_accuracy": float(((flat_p >= 0.5) == (flat_y > 0.5)).mean()),
        "connection_auc": _roc_auc(flat_p, flat_y),
        "connection_brier": float(((flat_p - flat_y) ** 2).mean()),
        "scenario_ratio_mae": float(
            (predicted_ratio - measured_ratio).abs().mean().item()),
    }


def _baseline(train_batch, val_batch) -> Dict[str, float]:
    """Always predicting the training base rate for every connection."""
    _, train_kept, train_mask = train_batch
    _, val_kept, val_mask = val_batch
    rate = float((train_kept * train_mask).sum() / train_mask.sum().clamp(min=1.0))
    real = val_mask > 0
    y = val_kept[real].cpu().numpy()
    counted = val_mask.sum(dim=1)
    measured = torch.where(
        counted > 0, (val_kept * val_mask).sum(dim=1) / counted.clamp(min=1.0),
        torch.ones_like(counted))
    return {
        "base_rate": rate,
        "connection_accuracy": float(max(y.mean(), 1 - y.mean())),
        "connection_auc": 0.5,
        "connection_brier": float(((rate - y) ** 2).mean()),
        "scenario_ratio_mae": float((measured - rate).abs().mean().item()),
    }


def _run_epoch(model, optimiser, batch, loss_fn, batch_size, rng, device) -> float:
    inputs, kept, mask = batch
    model.train()
    indices = np.arange(kept.shape[0])
    rng.shuffle(indices)
    total, seen = 0.0, 0
    for start in range(0, len(indices), batch_size):
        chunk = torch.tensor(indices[start:start + batch_size], device=device)
        logits = model(*(field[chunk] for field in inputs))
        chunk_mask = mask[chunk]
        # Mean over *real* connections: padding must not dilute the loss,
        # and a scenario with 60 transfers should weigh 60x one with 1.
        per = loss_fn(logits, kept[chunk]) * chunk_mask
        loss = per.sum() / chunk_mask.sum().clamp(min=1.0)
        optimiser.zero_grad()
        loss.backward()
        optimiser.step()
        total += loss.item() * len(chunk)
        seen += len(chunk)
    return total / max(1, seen)


def validation_score(metrics: Dict[str, float]) -> float:
    """One number to decide whether to keep training.

    AUC dominates: ranking which transfers are at risk is the useful
    output, and accuracy alone would reward predicting the majority class.
    The scenario ratio enters as `1 - MAE` to keep the aggregate honest.
    """
    return 0.7 * metrics["connection_auc"] + 0.3 * (
        1.0 - min(1.0, metrics["scenario_ratio_mae"]))


def train_connection_model(
    samples: Sequence[Sample],
    epochs: int = 50,
    batch_size: int = 32,
    learning_rate: float = 3e-4,
    weight_decay: float = 1e-4,
    dropout: float = 0.1,
    hidden: int = 96,
    layers: int = 4,
    val_fraction: float = 0.2,
    seed: int = 0,
    device: str = "cpu",
    verbose: bool = True,
) -> Tuple[ConnectionTransformer, ConnectionReport]:
    if len(samples) < 8:
        raise ValueError(f"need at least 8 samples to train, got {len(samples)}")
    torch.manual_seed(seed)
    train_samples, val_samples = split_samples(samples, seed, val_fraction)
    train_batch = _tensors(train_samples, device)
    val_batch = _tensors(val_samples, device)

    train_connections = int(train_batch[2].sum().item())
    if train_connections == 0:
        raise ValueError(
            "no connections in the training split — the dataset was built "
            "before per-connection labels existed, so there is nothing to fit"
        )

    model = ConnectionTransformer(
        hidden=hidden, layers=layers, dropout=dropout
    ).to(device)
    optimiser = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimiser, T_max=max(1, epochs))
    # `none` so padding can be masked out before reducing.
    loss_fn = nn.BCEWithLogitsLoss(reduction="none")

    report = ConnectionReport(
        epochs=epochs,
        train_size=len(train_samples),
        val_size=len(val_samples),
        train_connections=train_connections,
        val_connections=int(val_batch[2].sum().item()),
        baseline=_baseline(train_batch, val_batch),
    )

    rng = np.random.default_rng(seed)
    for epoch in range(1, epochs + 1):
        loss = _run_epoch(
            model, optimiser, train_batch, loss_fn, batch_size, rng, device)
        scheduler.step()
        metrics = evaluate(model, val_batch)
        metrics["loss"] = loss
        metrics["epoch"] = epoch
        report.history.append(metrics)
        if verbose and (epoch % 5 == 0 or epoch == 1 or epoch == epochs):
            print(
                f"epoch {epoch:3d}  loss {loss:.4f}  "
                f"auc {metrics['connection_auc']:.3f}  "
                f"acc {metrics['connection_accuracy']:.3f}  "
                f"brier {metrics['connection_brier']:.3f}  "
                f"ratio_mae {metrics['scenario_ratio_mae']:.3f}",
                flush=True,
            )
    report.final = evaluate(model, val_batch)
    return model, report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--hidden", type=int, default=96)
    parser.add_argument("--layers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--dataset-cache", type=str, default=None)
    parser.add_argument("--out", type=str, default="connection_model.pt")
    parser.add_argument("--report", type=str, default=None)
    parser.add_argument(
        "--block-epochs", type=int, default=0,
        help="train in blocks of this many epochs, continuing while the "
             "validation score improves (0 = fixed --epochs run)")
    parser.add_argument("--max-blocks", type=int, default=40)
    parser.add_argument("--patience", type=int, default=2)
    parser.add_argument("--checkpoint", type=str, default=None)
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument(
        "--generate-only", action="store_true",
        help="build and cache the dataset (hours), then stop without training",
    )
    args = parser.parse_args(argv)

    cache = args.dataset_cache
    if cache and Path(cache).exists():
        print(f"loading cached dataset {cache} ...", flush=True)
        samples = load_samples(cache)
    else:
        print(f"generating {args.samples} samples ...", flush=True)
        samples = generate_samples_parallel(
            args.samples, seed=args.seed, workers=args.workers, verbose=True)
        if cache:
            save_samples(cache, samples)
            print(f"  cached dataset to {cache}", flush=True)

    total = sum(int(s.connection_mask.sum()) for s in samples
                if s.connection_mask is not None)
    kept = sum(int(s.connection_kept.sum()) for s in samples
               if s.connection_kept is not None)
    print(f"  {len(samples)} scenarios, {total} connections, "
          f"{kept} kept ({kept / max(1, total):.1%})", flush=True)
    if total == 0:
        print("  this cache has no per-connection labels; regenerate it.")
        return 1
    if args.generate_only:
        print("  --generate-only: dataset ready, stopping before training.")
        return 0

    if args.block_epochs > 0:
        checkpoint = args.checkpoint or str(Path(args.out).with_suffix(".ckpt"))
        model, report = train_until_no_improvement(
            samples=samples, checkpoint_path=checkpoint,
            block_epochs=args.block_epochs, max_blocks=args.max_blocks,
            batch_size=args.batch_size, learning_rate=args.learning_rate,
            weight_decay=args.weight_decay, dropout=args.dropout,
            hidden=args.hidden, layers=args.layers, seed=args.seed,
            patience=args.patience, resume=not args.fresh,
        )
        print(f"\ncheckpoint: {checkpoint} (epoch {report.epochs})", flush=True)
    else:
        model, report = train_connection_model(
            samples=samples, epochs=args.epochs, batch_size=args.batch_size,
            learning_rate=args.learning_rate, weight_decay=args.weight_decay,
            dropout=args.dropout, hidden=args.hidden, layers=args.layers,
            seed=args.seed,
        )
    print("\nvalidation:", json.dumps(report.final, indent=2))
    print("baseline (always the base rate):", json.dumps(report.baseline, indent=2))
    print("saved:", model.save(args.out))
    if args.report:
        with open(args.report, "w") as handle:
            json.dump(report.to_dict(), handle, indent=2)
        print("report:", args.report)
    return 0



# ── resumable block training ─────────────────────────────────────────

def load_checkpoint(path: str, device: str = "cpu"):
    """Restore model, optimiser and progress. Returns (model, payload)."""
    return block_training.load_checkpoint(path, ConnectionTransformer, device)


def train_until_no_improvement(
    samples: Sequence[Sample],
    checkpoint_path: str,
    block_epochs: int = 25,
    max_blocks: int = 40,
    batch_size: int = 32,
    learning_rate: float = 3e-4,
    weight_decay: float = 1e-4,
    dropout: float = 0.1,
    hidden: int = 96,
    layers: int = 4,
    val_fraction: float = 0.2,
    seed: int = 0,
    device: str = "cpu",
    patience: int = 2,
    resume: bool = True,
    verbose: bool = True,
) -> Tuple[ConnectionTransformer, ConnectionReport]:
    """Resumable block training for the connection transformer.

    The loop itself — checkpoint resume, dataset-fingerprint guard, blocks
    while the validation score improves, best-checkpoint restore — lives in
    `block_training.train_in_blocks`; this wrapper supplies the masked BCE
    loss, the per-connection metrics and the AUC-led validation score.
    """
    if len(samples) < 8:
        raise ValueError(f"need at least 8 samples to train, got {len(samples)}")
    torch.manual_seed(seed)
    train_samples, val_samples = split_samples(samples, seed, val_fraction)
    train_batch = _tensors(train_samples, device)
    val_batch = _tensors(val_samples, device)

    train_connections = int(train_batch[2].sum().item())
    if train_connections == 0:
        raise ValueError(
            "no connections in the training split — the dataset was built "
            "before per-connection labels existed, so there is nothing to fit"
        )

    fingerprint = {
        "samples": len(samples),
        "seed": seed,
        "val_fraction": val_fraction,
        "connections": train_connections,
    }

    loss_fn = nn.BCEWithLogitsLoss(reduction="none")
    model, epochs, history = block_training.train_in_blocks(
        checkpoint_path=checkpoint_path,
        model_cls=ConnectionTransformer,
        build_model=lambda: ConnectionTransformer(
            hidden=hidden, layers=layers, dropout=dropout).to(device),
        run_epoch=lambda net, optimiser, rng: _run_epoch(
            net, optimiser, train_batch, loss_fn, batch_size, rng, device),
        evaluate_model=lambda net: evaluate(net, val_batch),
        validation_score=validation_score,
        format_metrics=lambda m: (
            f"auc {m['connection_auc']:.3f}  "
            f"acc {m['connection_accuracy']:.3f}  "
            f"brier {m['connection_brier']:.3f}  "
            f"ratio_mae {m['scenario_ratio_mae']:.3f}"
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
    )

    report = ConnectionReport(
        epochs=epochs,
        train_size=len(train_samples),
        val_size=len(val_samples),
        train_connections=train_connections,
        val_connections=int(val_batch[2].sum().item()),
        baseline=_baseline(train_batch, val_batch),
    )
    report.history = history
    report.final = evaluate(model, val_batch)
    return model, report

if __name__ == "__main__":
    raise SystemExit(main())
