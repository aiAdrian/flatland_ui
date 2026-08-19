"""Fitting a value network to self-play labels, one generation at a time.

    python -m app.policies.tree_search.train --scenarios 40 --generations 3 \\
        --out backend/models/tree_search

Each generation plays a batch of scenarios with the current network,
labels every state on the path that was executed with the outcome that run
achieved, and trains on those labels pooled with the previous generations'
(a replay buffer — training on the newest data alone makes a network chase
its own tail).

A generation is only kept if it is *measured* to be better: the candidate
and the incumbent each play the same held-out scenarios, and the winner is
whichever achieves the higher outcome. Prediction error is not the test —
a network can predict a poor search's outcomes perfectly and still be
useless to a better one.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch import nn

from app.policies.tree_search import metrics as metric_model
from app.policies.tree_search import selfplay
from app.policies.tree_search.net import StateValueNet
from app.policies.tree_search.observation import LONG_SLOTS, stack
from app.policies.tree_search.scenario import Scenario
from app.policies.tree_search.selfplay import Sample

# Held-out share of the samples, split by *scenario* — states of one run
# are near-identical, so splitting them individually would put a state's
# own twin in the validation set and flatter the numbers.
VALIDATION_FRACTION = 0.2


@dataclass
class Report:
    generations: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {"generations": self.generations}


def _tensors(samples: Sequence[Sample], metric: str, device: str = "cpu"):
    arrays = stack([sample.observation for sample in samples])
    inputs = [
        torch.tensor(
            array,
            dtype=torch.long if index in LONG_SLOTS else torch.float32,
            device=device,
        )
        for index, array in enumerate(arrays)
    ]
    target = torch.tensor(
        [float(sample.labels[metric]) for sample in samples],
        dtype=torch.float32, device=device,
    )
    return inputs, target


def split(
    samples: Sequence[Sample], seed: int = 0,
    fraction: float = VALIDATION_FRACTION,
) -> Tuple[List[Sample], List[Sample]]:
    """Train/validation split by scenario."""
    names = sorted({sample.scenario for sample in samples})
    rng = random.Random(seed)
    rng.shuffle(names)
    cut = max(1, int(len(names) * fraction))
    held_out = set(names[:cut])
    train = [s for s in samples if s.scenario not in held_out]
    validation = [s for s in samples if s.scenario in held_out]
    return (train or list(samples)), (validation or list(samples))


@torch.no_grad()
def evaluate(
    model: StateValueNet, samples: Sequence[Sample], metric: str,
    batch_size: int = 64, device: str = "cpu",
) -> Dict[str, float]:
    """Mean absolute error, and R² against always predicting the mean."""
    model.eval()
    predictions, targets = [], []
    for start in range(0, len(samples), batch_size):
        chunk = samples[start:start + batch_size]
        inputs, target = _tensors(chunk, metric, device)
        predictions.append(torch.sigmoid(model(*inputs)))
        targets.append(target)
    predicted = torch.cat(predictions)
    target = torch.cat(targets)
    residual = ((predicted - target) ** 2).sum().item()
    total = ((target - target.mean()) ** 2).sum().item()
    return {
        "mae": (predicted - target).abs().mean().item(),
        "r2": 1.0 - residual / total if total > 1e-12 else 0.0,
        "samples": float(len(samples)),
    }


def fit(
    model: StateValueNet,
    samples: Sequence[Sample],
    metric: str = "punctuality",
    epochs: int = 20,
    batch_size: int = 64,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-4,
    seed: int = 0,
    device: str = "cpu",
    verbose: bool = False,
) -> Dict[str, float]:
    """Train on the labels. The target is a utility in [0, 1], so binary
    cross-entropy on the logit keeps predictions in range by construction."""
    torch.manual_seed(seed)
    train_samples, validation = split(samples, seed)
    optimiser = torch.optim.Adam(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    loss_fn = nn.BCEWithLogitsLoss()
    rng = random.Random(seed)

    for epoch in range(epochs):
        model.train()
        order = list(range(len(train_samples)))
        rng.shuffle(order)
        for start in range(0, len(order), batch_size):
            chunk = [train_samples[i] for i in order[start:start + batch_size]]
            inputs, target = _tensors(chunk, metric, device)
            loss = loss_fn(model(*inputs), target)
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
        if verbose and (epoch + 1) % 5 == 0:
            scored = evaluate(model, validation, metric, device=device)
            print(f"    epoch {epoch + 1:3d}  mae {scored['mae']:.3f}  "
                  f"r2 {scored['r2']:.3f}", flush=True)
    return evaluate(model, validation, metric, device=device)


def measure(
    scenarios: Sequence[Tuple[str, Scenario]],
    models: Optional[Dict[str, StateValueNet]],
    budget: int,
    metric: str = "punctuality",
) -> float:
    """What a network is worth where it counts: the mean outcome the search
    achieves with it, on scenarios it did not train on."""
    scores = []
    for name, scenario in scenarios:
        episode = selfplay.play(
            scenario, models=models, budget=budget, temperature=0.0, name=name)
        scores.append(episode.utilities[metric])
    return float(np.mean(scores)) if scores else 0.0


def build_scenarios(
    count: int, seed: int, trains: int = 6, size: int = 30, cities: int = 2,
    line_length: int = 2,
) -> List[Tuple[str, Scenario]]:
    """A batch of generated railways to play on."""
    from app.policies.goal_based_policies.visualization import build_demo_env

    rng = random.Random(seed)
    built: List[Tuple[str, Scenario]] = []
    attempts = 0
    while len(built) < count and attempts < count * 4:
        attempts += 1
        layout_seed = rng.randint(1, 10_000_000)
        try:
            env = build_demo_env(
                seed=layout_seed, width=size, height=size,
                number_of_agents=trains, max_num_cities=cities,
                line_length=line_length,
            )
            built.append((f"s{layout_seed}", Scenario.build(env)))
        except Exception:
            continue
    return built


def run(
    scenarios_per_generation: int = 24,
    generations: int = 3,
    budget: int = 64,
    epochs: int = 20,
    seed: int = 0,
    metric: str = "punctuality",
    out: Optional[str] = None,
    trains: int = 6,
    verbose: bool = True,
) -> Tuple[StateValueNet, Report]:
    """The loop: play, label, train, keep it only if it measures better."""
    report = Report()
    buffer: List[Sample] = []
    model: Optional[StateValueNet] = None
    holdout = build_scenarios(8, seed=seed + 99_991, trains=trains)
    incumbent_score = None

    for generation in range(generations):
        scenarios = build_scenarios(
            scenarios_per_generation, seed=seed + generation * 1_000,
            trains=trains,
        )
        models = None if model is None else {metric: model}
        if verbose:
            print(f"generation {generation}: playing "
                  f"{len(scenarios)} scenarios", flush=True)
        samples, episodes = selfplay.collect(
            scenarios, models=models, budget=budget,
            temperature=0.3, seed=seed + generation,
        )
        buffer.extend(samples)
        played = float(np.mean([e.utilities[metric] for e in episodes]))

        candidate = StateValueNet(metric=metric)
        if model is not None:
            candidate.load_state_dict(model.state_dict())
        fitted = fit(
            candidate, buffer, metric=metric, epochs=epochs,
            seed=seed + generation, verbose=verbose,
        )

        if incumbent_score is None:
            incumbent_score = measure(holdout, None, budget, metric)
        candidate_score = measure(holdout, {metric: candidate}, budget, metric)
        kept = candidate_score >= incumbent_score
        if kept:
            model = candidate
            incumbent_score = candidate_score

        entry = {
            "generation": generation,
            "samples": len(samples),
            "buffer": len(buffer),
            "self_play_score": played,
            "validation": fitted,
            "held_out_score": candidate_score,
            "incumbent_score": incumbent_score,
            "kept": kept,
        }
        report.generations.append(entry)
        if verbose:
            print(f"  played {played:.3f} | held-out {candidate_score:.3f} "
                  f"(incumbent {incumbent_score:.3f}) | "
                  f"{'kept' if kept else 'rejected'}", flush=True)

    if model is None:
        model = StateValueNet(metric=metric)
    if out:
        directory = Path(out)
        directory.mkdir(parents=True, exist_ok=True)
        model.save(directory / f"{metric}.ckpt")
        (directory / f"{metric}.report.json").write_text(
            json.dumps(report.to_dict(), indent=2))
    return model, report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=int, default=24)
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--budget", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--trains", type=int, default=6)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--metric", default="punctuality",
                        choices=sorted(metric_model.METRICS))
    parser.add_argument("--out", default="models/tree_search")
    args = parser.parse_args(argv)

    _, report = run(
        scenarios_per_generation=args.scenarios,
        generations=args.generations,
        budget=args.budget,
        epochs=args.epochs,
        seed=args.seed,
        metric=args.metric,
        out=args.out,
        trains=args.trains,
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0


__all__ = ["Report", "build_scenarios", "evaluate", "fit", "measure", "run", "split"]


if __name__ == "__main__":
    raise SystemExit(main())
