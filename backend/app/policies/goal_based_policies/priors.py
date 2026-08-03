"""A learned prior over branch options.

MCTS explores its options under a uniform prior. But which option the
weighted ensemble ends up preferring is far from uniform — the searches'
own traces show it. This module distils those traces into a tiny net over
features that are known *before* any model call:

- the option's extra hold (the wait menu value),
- its route rank (options come back cheapest-route-first),
- whether its completion is free of planned overlaps (the cheap pruner),
- how many options the decision offers.

That is deliberately all: the prior's job is to focus PUCT's first
simulations on the options that usually win, not to replace the value
ensemble — anything the models must judge stays with the models.

Status: validated as a predictor (57% top-1 vs 9% uniform), but rejected
by its gate as a PUCT prior — at practical budgets a sharp prior starves
the off-preference exploration MCTS depends on, so uniform stays the MCTS
default. The module remains for future variants (tempered priors, option
ordering) via the `mcts_search(prior=...)` hook.

Training data: trace jsonl written by `search_dataset --traces-out`
(greedy or MCTS traces — both carry per-option records and the chosen
index; beam traces do not and are skipped).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch import nn

FEATURES = 5


def option_features(
    wait: float, route_rank: int, clean: bool, n_options: int
) -> List[float]:
    """Per-option inputs, all cheap. Normalisations keep everything O(1)."""
    return [
        float(wait) / 10.0,
        float(route_rank),
        1.0 if clean else 0.0,
        1.0 if route_rank == 0 else 0.0,
        float(n_options) / 15.0,
    ]


def _route_rank(index: int, n_options: int, n_waits: int) -> int:
    """Options are generated wait-major (for each wait, every route), so
    an option's route rank is its index within its wait block."""
    routes = max(1, n_options // max(1, n_waits))
    return index % routes


class BranchPrior(nn.Module):
    """Logistic scores per option; softmax across a decision's options."""

    def __init__(self, hidden: int = 16):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(FEATURES, hidden), nn.ReLU(), nn.Linear(hidden, 1),
        )
        self._config = {"hidden": hidden}

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.net(features).squeeze(-1)

    @torch.no_grad()
    def probabilities(
        self, options: Sequence[Dict[str, object]], n_waits: int
    ) -> List[float]:
        """Prior over one decision's options, from trace-shaped dicts
        (`wait`, `clean` keys)."""
        self.eval()
        rows = [
            option_features(
                float(option["wait"]),
                _route_rank(index, len(options), n_waits),
                bool(option.get("clean", True)),
                len(options),
            )
            for index, option in enumerate(options)
        ]
        logits = self(torch.tensor(rows, dtype=torch.float32))
        return torch.softmax(logits, dim=0).tolist()

    def save(self, path: str | Path) -> str:
        torch.save({"state_dict": self.state_dict(),
                    "config": self._config}, Path(path))
        return str(path)

    @classmethod
    def load(cls, path: str | Path) -> "BranchPrior":
        payload = torch.load(path, map_location="cpu", weights_only=False)
        model = cls(**payload["config"])
        model.load_state_dict(payload["state_dict"])
        model.eval()
        return model


def load_decisions(
    paths: Sequence[str], n_waits: int = 5
) -> List[Tuple[np.ndarray, int]]:
    """(option-feature matrix, chosen index) per decision, from trace
    jsonl files. Decisions without a choice (stuck) or with one option
    are skipped — there is nothing to learn from them."""
    decisions: List[Tuple[np.ndarray, int]] = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                for entry in record.get("trace", []):
                    options = entry.get("options", [])
                    chosen = entry.get("chosen")
                    if chosen is None or len(options) < 2:
                        continue
                    rows = np.array([
                        option_features(
                            float(option["wait"]),
                            _route_rank(index, len(options), n_waits),
                            bool(option.get("clean", True)),
                            len(options),
                        )
                        for index, option in enumerate(options)
                    ], dtype=np.float32)
                    decisions.append((rows, int(chosen)))
    return decisions


def train_prior(
    decisions: Sequence[Tuple[np.ndarray, int]],
    epochs: int = 30,
    learning_rate: float = 1e-2,
    seed: int = 0,
    val_fraction: float = 0.2,
    verbose: bool = False,
) -> Tuple[BranchPrior, Dict[str, float]]:
    """Cross-entropy over each decision's options. Reports top-1 accuracy
    against the uniform baseline — the prior earns its place only by
    beating "pick any option"."""
    if len(decisions) < 10:
        raise ValueError(f"need at least 10 decisions, got {len(decisions)}")
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(decisions))
    split = max(1, int(len(decisions) * (1 - val_fraction)))
    train = [decisions[i] for i in order[:split]]
    val = [decisions[i] for i in order[split:]] or train[-1:]

    torch.manual_seed(seed)
    model = BranchPrior()
    optimiser = torch.optim.Adam(model.parameters(), lr=learning_rate)

    def accuracy(subset) -> float:
        model.eval()
        hits = 0
        with torch.no_grad():
            for rows, chosen in subset:
                logits = model(torch.tensor(rows))
                hits += int(int(logits.argmax()) == chosen)
        return hits / len(subset)

    for epoch in range(epochs):
        model.train()
        total = 0.0
        for rows, chosen in train:
            logits = model(torch.tensor(rows)).unsqueeze(0)
            loss = nn.functional.cross_entropy(
                logits, torch.tensor([chosen]))
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            total += float(loss)
        if verbose and (epoch + 1) % 10 == 0:
            print(f"  epoch {epoch + 1}: loss {total / len(train):.3f} "
                  f"val acc {accuracy(val):.3f}", flush=True)

    metrics = {
        "val_accuracy": accuracy(val),
        "uniform_accuracy": float(np.mean(
            [1.0 / len(rows) for rows, _ in val])),
        "decisions": float(len(decisions)),
    }
    return model, metrics


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+", help="trace jsonl files")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    decisions = load_decisions(args.traces)
    print(f"{len(decisions)} decisions with a real choice")
    model, metrics = train_prior(
        decisions, epochs=args.epochs, seed=args.seed, verbose=True)
    model.save(args.out)
    print(f"val top-1 {metrics['val_accuracy']:.3f} "
          f"(uniform {metrics['uniform_accuracy']:.3f}) -> {args.out}")
    return 0


__all__ = [
    "BranchPrior",
    "load_decisions",
    "option_features",
    "train_prior",
]


if __name__ == "__main__":
    raise SystemExit(main())
