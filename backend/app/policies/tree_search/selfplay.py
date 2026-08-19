"""Self-play: search, execute, measure, label.

The AlphaZero loop, with the simulator as the judge and no opponent. Per
scenario:

1. grow the tree for a while from the current root;
2. take the decision the search prefers, and *execute* it — the tree is
   re-rooted onto that child, so everything already explored below it is
   kept;
3. repeat until the run is over;
4. measure what that run achieved and give **every state along the way**
   that same measured value as its label.

Which is to say: a state's target is the outcome actually reached from it,
under the search's own continuation — exactly what the value network is
asked to predict at scoring time. States that were explored but never
played get no label; they were judged, not lived through.

Two things keep the loop from feeding on itself:

- **exploration** — with `temperature` above zero the executed decision is
  sampled among the root's children rather than always the best one, so the
  data covers states the current network does not already like;
- **generations** — a run is labelled by what happened, never by what the
  network predicted, so the labels stay ground truth even when the network
  guiding the search is poor.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.policies.tree_search import metrics as metric_model
from app.policies.tree_search import observation as observation_model
from app.policies.tree_search import simulator
from app.policies.tree_search.observation import Observation
from app.policies.tree_search.scenario import Scenario
from app.policies.tree_search.search import TreeSearch

# Decisions one self-play run may execute before it is abandoned. A run
# needs a few dozen; anything near this is a scenario that never resolves.
MAX_DECISIONS = 400


@dataclass
class Sample:
    """One state, with what the run it belonged to actually achieved."""
    observation: Observation
    labels: Dict[str, float]
    scenario: str = ""
    step: int = 0

    def arrays(self) -> Dict[str, np.ndarray]:
        return {
            "graph_nodes": self.observation.graph.nodes,
            "edge_index": self.observation.graph.edge_index,
            "edge_features": self.observation.graph.edge_features,
            "train_nodes": self.observation.train_nodes,
            "train_features": self.observation.train_features,
            "globals": self.observation.globals,
        }


@dataclass
class Episode:
    samples: List[Sample]
    outcome: object
    utilities: Dict[str, float]
    decisions: int
    stats: Dict[str, object] = field(default_factory=dict)


def play(
    scenario: Scenario,
    models: Optional[Dict[str, object]] = None,
    weights: Optional[Dict[str, float]] = None,
    budget: int = 64,
    temperature: float = 0.0,
    seed: int = 0,
    name: str = "",
    max_decisions: int = MAX_DECISIONS,
) -> Episode:
    """Play one scenario and return every state on the executed path."""
    rng = random.Random(seed)
    search = TreeSearch(scenario, models=models, weights=weights)
    observed: List[Observation] = []
    steps: List[int] = []
    decisions = 0

    while decisions < max_decisions:
        root = search.nodes[search.root]
        if root.terminal:
            break
        search.run(node_budget=budget)
        action = _choose(search, rng, temperature)
        if action is None:
            break
        observed.append(observation_model.encode(scenario, root.state))
        steps.append(root.state.step)
        if not search.reroot(action):
            break
        decisions += 1

    final = search.nodes[search.root].state
    # The root may stop short of the end when the budget ran out mid-run;
    # what is left is played out with the search's own preference so the
    # label is a real outcome rather than an unfinished one.
    final = _finish(scenario, final, search)
    outcome = simulator.outcome(scenario, final)
    utilities = metric_model.utilities(outcome)

    samples = [
        Sample(observation=obs, labels=dict(utilities), scenario=name, step=step)
        for obs, step in zip(observed, steps)
    ]
    return Episode(
        samples=samples, outcome=outcome, utilities=utilities,
        decisions=decisions, stats=search.stats(),
    )


# How much less likely each further-down option is to be explored, before
# the values have a say. Children are generated cheapest-route-first, so
# this makes an exploring run *mostly* sensible with occasional deviations.
# Without it, a generation whose network has nothing to say yet would weight
# every option alike — which is random driving, and random driving gridlocks
# every time, producing a whole generation of identically bad labels.
SLOT_DECAY = 0.5


def _choose(search: TreeSearch, rng: random.Random, temperature: float):
    """The decision to execute: the best one, or a sample among the root's
    children when exploring."""
    root = search.nodes[search.root]
    if not root.children:
        return None
    if temperature <= 0:
        return search.best_action()
    slots = sorted(root.children)
    weights = [
        max(1e-6, search.nodes[root.children[slot]].value)
        ** (1.0 / max(temperature, 1e-3))
        * SLOT_DECAY ** position
        for position, slot in enumerate(slots)
    ]
    total = sum(weights)
    pick = rng.random() * total
    for slot, weight in zip(slots, weights):
        pick -= weight
        if pick <= 0:
            return root.child_actions[slot]
    return root.child_actions[slots[-1]]


def _finish(scenario: Scenario, state, search: TreeSearch):
    """Play a run out to its end without growing the tree further."""
    from app.policies.tree_search import actions as action_model

    guard = 0
    while not simulator.is_terminal(scenario, state) and guard < MAX_DECISIONS:
        handles = simulator.deciding(scenario, state)
        candidates = action_model.joint_actions(scenario, state, handles)
        if not candidates:
            break
        state = action_model.apply(scenario, state, candidates[0])
        guard += 1
    return state


def collect(
    scenarios: Sequence[Tuple[str, Scenario]],
    models: Optional[Dict[str, object]] = None,
    weights: Optional[Dict[str, float]] = None,
    budget: int = 64,
    temperature: float = 0.3,
    seed: int = 0,
    verbose: bool = False,
) -> Tuple[List[Sample], List[Episode]]:
    """Play a batch of scenarios and pool their samples."""
    samples: List[Sample] = []
    episodes: List[Episode] = []
    for index, (name, scenario) in enumerate(scenarios):
        episode = play(
            scenario, models=models, weights=weights, budget=budget,
            temperature=temperature, seed=seed + index, name=name,
        )
        samples.extend(episode.samples)
        episodes.append(episode)
        if verbose:
            print(
                f"  {name}: {len(episode.samples):3d} states, "
                f"punctuality {episode.utilities['punctuality']:.3f}, "
                f"arrived {episode.outcome.arrived_fraction:.2f}",
                flush=True,
            )
    return samples, episodes


def save(path: str, samples: Sequence[Sample]) -> str:
    """Cache samples as one compressed archive."""
    payload = [
        {**sample.arrays(), "labels": sample.labels,
         "scenario": sample.scenario, "step": sample.step}
        for sample in samples
    ]
    np.savez_compressed(path, samples=np.array(payload, dtype=object))
    return path


def load(path: str) -> List[Sample]:
    from app.policies.tree_search.observation import GraphTensors

    payload = np.load(path, allow_pickle=True)["samples"]
    samples: List[Sample] = []
    for entry in payload:
        samples.append(Sample(
            observation=Observation(
                graph=GraphTensors(
                    nodes=entry["graph_nodes"],
                    edge_index=entry["edge_index"],
                    edge_features=entry["edge_features"],
                ),
                train_nodes=entry["train_nodes"],
                train_features=entry["train_features"],
                globals=entry["globals"],
            ),
            labels=dict(entry["labels"]),
            scenario=str(entry.get("scenario", "")),
            step=int(entry.get("step", 0)),
        ))
    return samples


__all__ = ["Episode", "MAX_DECISIONS", "Sample", "collect", "load", "play", "save"]
