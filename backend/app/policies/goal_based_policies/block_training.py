"""Resumable block-training driver shared by the two trainers.

`train_evaluator` and `train_connection_model` fit different models on
different targets, but their outer loop is the same: train in blocks of
`block_epochs`, score the held-out set after each block, overwrite the
checkpoint whenever the score improves, stop after `patience` blocks
without improvement, and hand back the best checkpointed model. This
module owns that loop; each trainer supplies its model factory, its
per-epoch step, its validation metrics, and the score that decides
whether to continue.

Checkpoints written here carry everything a resume needs — model config
and weights, optimiser and scheduler state, epoch count, best score,
per-epoch history — plus a fingerprint of the dataset and split, so a
resumed run either continues on exactly the data it was scored on or
refuses loudly.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import torch
from torch import nn

# Indices of the integer-valued fields (edge_index, schedule_nodes) in the
# `stack_samples` layout; both trainers cast these to long and everything
# else to float32.
LONG_FIELDS = frozenset({2, 5})

# Validation is scored in slices rather than one forward pass. The schedule
# encoder expands the visited node embeddings to
# (batch, trains, schedule nodes, hidden) — at a 6000-sample validation set
# that single intermediate is ~800 MB, and several exist at once, which was
# enough to drive this machine into swap. Slicing bounds it; the metrics are
# unchanged because every one of them is computed from the full
# concatenation afterwards.
EVAL_CHUNK = 256


def save_checkpoint(
    path: str,
    model: nn.Module,
    optimiser: torch.optim.Optimizer,
    scheduler,
    epochs_done: int,
    best_score: float,
    history: List[Dict[str, float]],
    fingerprint: Dict[str, object],
    extra: Optional[Dict[str, object]] = None,
) -> str:
    """Everything needed to carry on training exactly where it stopped."""
    payload = {
        "state_dict": model.state_dict(),
        "config": model._config,
        "optimiser": optimiser.state_dict(),
        "scheduler": scheduler.state_dict() if scheduler else None,
        "epochs_done": int(epochs_done),
        "best_score": float(best_score),
        "history": history,
        "fingerprint": fingerprint,
    }
    if extra:
        payload.update(extra)
    torch.save(payload, path)
    return path


def load_checkpoint(path: str, model_cls: type, device: str = "cpu"):
    """Restore model and training progress. Returns (model, payload)."""
    payload = torch.load(path, map_location=device, weights_only=False)
    model = model_cls(**payload["config"]).to(device)
    model.load_state_dict(payload["state_dict"])
    return model, payload


def train_in_blocks(
    *,
    checkpoint_path: str,
    model_cls: type,
    build_model: Callable[[], nn.Module],
    run_epoch: Callable[
        [nn.Module, torch.optim.Optimizer, np.random.Generator], float
    ],
    evaluate_model: Callable[[nn.Module], Dict[str, float]],
    validation_score: Callable[[Dict[str, float]], float],
    format_metrics: Callable[[Dict[str, float]], str],
    fingerprint: Dict[str, object],
    block_epochs: int,
    max_blocks: int,
    learning_rate: float,
    weight_decay: float,
    seed: int,
    patience: int,
    device: str = "cpu",
    resume: bool = True,
    verbose: bool = True,
    checkpoint_extra: Optional[Dict[str, object]] = None,
) -> Tuple[nn.Module, int, List[Dict[str, float]]]:
    """Train in blocks of `block_epochs`, continuing while validation improves.

    After each block the model is scored via `evaluate_model` and
    `validation_score`. If the score beats the best so far, the checkpoint
    is overwritten (the previous one is therefore discarded) and another
    block runs. If `patience` consecutive blocks fail to improve, training
    stops and the last saved checkpoint — which is the best one — is
    restored and returned.

    Regularisation: AdamW with weight decay and a cosine learning-rate
    schedule that restarts every block — each block anneals to a low rate
    and the restart gives the next block a fresh push, which fits the
    "keep going while it improves" loop.

    Returns `(model, epochs, history)`: the best model seen, the epoch
    count it was saved at, and the per-epoch validation metrics across
    every run of this checkpoint.
    """

    def build_optimiser(target):
        optimiser = torch.optim.AdamW(
            target.parameters(), lr=learning_rate, weight_decay=weight_decay
        )
        scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
            optimiser, T_0=max(1, block_epochs)
        )
        return optimiser, scheduler

    model = build_model()
    optimiser, scheduler = build_optimiser(model)
    epochs_done = 0
    best_score = -float("inf")
    history: List[Dict[str, float]] = []

    if resume and Path(checkpoint_path).exists():
        restored, payload = load_checkpoint(checkpoint_path, model_cls, device)
        stored = payload.get("fingerprint", {})
        if stored != fingerprint:
            raise ValueError(
                f"checkpoint {checkpoint_path} was trained on different data "
                f"({stored} vs {fingerprint}); continuing would compare "
                "scores across different validation sets"
            )
        model = restored
        optimiser, scheduler = build_optimiser(model)
        optimiser.load_state_dict(payload["optimiser"])
        if payload.get("scheduler"):
            scheduler.load_state_dict(payload["scheduler"])
        epochs_done = int(payload["epochs_done"])
        best_score = float(payload["best_score"])
        history = list(payload.get("history", []))
        if verbose:
            print(
                f"resuming from {checkpoint_path}: {epochs_done} epochs done, "
                f"best score {best_score:.4f}", flush=True,
            )

    stale = 0
    rng = np.random.default_rng(seed + epochs_done)
    while stale < patience and len(history) // max(1, block_epochs) < max_blocks:
        block_loss = 0.0
        for _ in range(block_epochs):
            block_loss = run_epoch(model, optimiser, rng)
            scheduler.step()
            epochs_done += 1
            metrics = evaluate_model(model)
            metrics["loss"] = block_loss
            metrics["epoch"] = epochs_done
            history.append(metrics)

        metrics = evaluate_model(model)
        score = validation_score(metrics)
        improved = score > best_score
        if verbose:
            print(
                f"block to epoch {epochs_done:4d}  loss {block_loss:.4f}  "
                f"score {score:.4f} (best {max(best_score, score):.4f})  "
                f"{format_metrics(metrics)}  "
                f"{'improved -> continue' if improved else 'no improvement'}",
                flush=True,
            )
        if improved:
            best_score = score
            stale = 0
            # Overwriting is the deletion of the older checkpoint.
            save_checkpoint(
                checkpoint_path, model, optimiser, scheduler, epochs_done,
                best_score, history, fingerprint, extra=checkpoint_extra,
            )
        else:
            stale += 1

    if Path(checkpoint_path).exists():
        model, payload = load_checkpoint(checkpoint_path, model_cls, device)
        epochs = int(payload["epochs_done"])
        if verbose:
            print(
                f"stopped; best model is from epoch {payload['epochs_done']} "
                f"(score {payload['best_score']:.4f})", flush=True,
            )
    else:
        epochs = epochs_done

    return model, epochs, history


__all__ = [
    "EVAL_CHUNK",
    "LONG_FIELDS",
    "load_checkpoint",
    "save_checkpoint",
    "train_in_blocks",
]
