"""The planner as the rest of the app uses it.

One entry point for "plan this environment" and one for "re-plan it from
where it is now", both returning executable schedules plus the evidence
behind them. Everything above this line — the API, the HMI, the policy —
talks to the search only through here.

The search keeps growing for as long as it is given budget, so a plan is
never final: `plan` runs it for a while and reports the best complete run
found. `replan` roots a search on the live situation instead, and reuses
the tree it is handed when the world still matches it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from flatland.envs.rail_env import RailEnv

from app.policies.goal_based_policies.infrastructure_graph import (
    DecisionPointGraph,
)
from app.policies.goal_based_policies.schedule import TrainSchedule
from app.policies.tree_search import live, metrics as metric_model, plan as plan_model
from app.policies.tree_search.metrics import DirectorWeights
from app.policies.tree_search.scenario import Scenario
from app.policies.tree_search.search import TreeSearch

# Nodes expanded before the first plan is handed over. The search is
# anytime, so this is "how long to think before answering", not a limit on
# how much it may ever explore.
PLANNING_BUDGET = int(os.environ.get("TREE_SEARCH_BUDGET", "600"))
# Budget for a mid-episode re-plan. Smaller: the episode is waiting.
REPLAN_BUDGET = int(os.environ.get("TREE_SEARCH_REPLAN_BUDGET", "300"))

_MODELS_DIR = Path(__file__).resolve().parents[3] / "models" / "tree_search"
MODEL_DIR = os.environ.get("TREE_SEARCH_MODELS", str(_MODELS_DIR))

_LOADED: Optional[Dict[str, object]] = None


def load_models(directory: Optional[str] = None) -> Dict[str, object]:
    """Every value network installed, keyed by metric.

    An empty result is a working configuration, not a failure: the search
    then values every state alike and falls back on its own ordering, which
    is what generation zero of training does too. torch is only imported if
    there is actually a checkpoint to load.
    """
    global _LOADED
    if directory is None and _LOADED is not None:
        return _LOADED
    root = Path(directory or MODEL_DIR)
    found: Dict[str, object] = {}
    if root.is_dir():
        for metric in metric_model.METRICS:
            path = root / f"{metric}.ckpt"
            if not path.exists():
                continue
            try:
                from app.policies.tree_search.net import StateValueNet

                found[metric] = StateValueNet.load(str(path))
            except Exception:
                continue
    if directory is None:
        _LOADED = found
    return found


@dataclass
class DirectorPlan:
    """What the Director commits, and why."""
    schedules: List[TrainSchedule]
    source: str                       # "search" | "search (no solution)"
    weighted: float
    utilities: Dict[str, float]
    decisions: int
    stats: Dict[str, object] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=dict)
    unimplemented: Sequence[str] = ()
    search: Optional[TreeSearch] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "source": self.source,
            "weighted": self.weighted,
            "utilities": dict(self.utilities),
            "decisions": self.decisions,
            "weights": dict(self.weights),
            # Dials the user can set that nothing acts on yet. Reported so
            # "I turned it up and nothing happened" has an answer.
            "unimplemented_weights": list(self.unimplemented),
            "search": dict(self.stats),
            "schedules": {s.handle: s.to_flat_list() for s in self.schedules},
        }


def _result(
    scenario: Scenario, search: TreeSearch, weights: DirectorWeights
) -> DirectorPlan:
    solution = search.best_solution()
    actions = solution.actions if solution else []
    replayed = plan_model.replay(scenario, search.replay_from, actions)
    utilities = (
        solution.utilities if solution
        else metric_model.utilities(replayed.outcome)
    )
    return DirectorPlan(
        schedules=replayed.schedules,
        source="search" if solution else "search (no solution)",
        weighted=(
            solution.weighted if solution
            else metric_model.combine(utilities, weights.as_metrics())
        ),
        utilities=utilities,
        decisions=len(actions),
        stats=search.stats(),
        weights=metric_model.normalised_weights(weights.as_metrics()),
        unimplemented=weights.unimplemented(),
        search=search,
    )


def plan(
    env: RailEnv,
    graph: Optional[DecisionPointGraph] = None,
    weights: DirectorWeights = DirectorWeights(),
    budget: int = PLANNING_BUDGET,
    models: Optional[Dict[str, object]] = None,
    scenario: Optional[Scenario] = None,
) -> DirectorPlan:
    """Plan a fresh environment from the first decision onwards."""
    scenario = scenario or Scenario.build(env, graph)
    search = TreeSearch(
        scenario,
        models=load_models() if models is None else models,
        weights=weights.as_metrics(),
    )
    search.run(node_budget=budget)
    return _result(scenario, search, weights)


def replan(
    scenario: Scenario,
    env: RailEnv,
    weights: DirectorWeights = DirectorWeights(),
    budget: int = REPLAN_BUDGET,
    models: Optional[Dict[str, object]] = None,
    player=None,
    reuse: Optional[TreeSearch] = None,
) -> DirectorPlan:
    """Plan the rest of the episode from where the trains actually are.

    Pass the `SchedulePlayer` driving the episode: reading the live state
    needs it (see `live.state_from_env`).

    When the running search has already explored the live situation, its
    tree is re-rooted there and the work is kept; otherwise a fresh tree is
    started, which is what a world that diverged from the model needs.
    """
    state = live.state_from_env(scenario, env, player=player)
    search: Optional[TreeSearch] = None
    if reuse is not None and reuse.reroot_to_state(state):
        search = reuse
    if search is None:
        search = TreeSearch(
            scenario,
            models=load_models() if models is None else models,
            weights=weights.as_metrics(),
            root_state=state,
        )
    search.weights = weights.as_metrics()
    search.run(node_budget=budget)
    return _result(scenario, search, weights)


__all__ = [
    "MODEL_DIR",
    "PLANNING_BUDGET",
    "REPLAN_BUDGET",
    "DirectorPlan",
    "DirectorWeights",
    "load_models",
    "plan",
    "replan",
]
