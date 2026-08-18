"""Scenario loading and outcome selection.

Scenarios are plain JSON files under ``scenarios/``. The engine loads them,
exposes decision points, and picks an observed outcome deterministically from a
per-session seed so a session can be replayed identically.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCENARIOS_DIR = Path(__file__).parent / "scenarios"


@dataclass
class Scenario:
    scenario_id: str
    name: str
    difficulty: str
    description: str
    seed: int
    decision_points: list[dict[str, Any]]
    raw: dict[str, Any]
    total_steps: int = 400

    @property
    def num_decisions(self) -> int:
        return len(self.decision_points)


def list_scenarios(directory: Path | None = None) -> list[Scenario]:
    directory = directory or SCENARIOS_DIR
    scenarios: list[Scenario] = []
    for path in sorted(directory.glob("*.json")):
        scenarios.append(load_scenario_file(path))
    # keep a stable, difficulty-based ordering for the picker
    order = {"Demo": -1, "Story": -0.5, "Easy": 0, "Medium": 1, "Hard": 2, "Stress": 3}
    scenarios.sort(key=lambda s: order.get(s.difficulty, 99))
    return scenarios


def load_scenario_file(path: Path) -> Scenario:
    data = json.loads(path.read_text(encoding="utf-8"))
    return _from_dict(data)


def load_scenario(scenario_id: str, directory: Path | None = None) -> Scenario:
    directory = directory or SCENARIOS_DIR
    path = directory / f"{scenario_id}.json"
    return load_scenario_file(path)


def _from_dict(data: dict[str, Any]) -> Scenario:
    return Scenario(
        scenario_id=data["scenario_id"],
        name=data["name"],
        difficulty=data["difficulty"],
        description=data.get("description", ""),
        seed=int(data.get("seed", 42)),
        decision_points=data["decision_points"],
        raw=data,
        total_steps=int(data.get("total_steps", 400)),
    )


def select_observed_outcome(
    decision_point: dict[str, Any],
    strategy_id: str,
    seed: int,
    step: int,
) -> dict[str, Any]:
    """Pick the observed outcome for a chosen strategy, seeded and reproducible.

    ``outcomes[strategy_id]`` is expected to contain ``expected`` and a list of
    ``observed`` candidates, each optionally carrying a ``weight``. If nothing is
    defined we fall back to mirroring the expected outcome.
    """
    outcomes = decision_point.get("outcomes", {})
    entry = outcomes.get(strategy_id)
    if not entry:
        return {}

    expected = entry.get("expected", {})
    observed_candidates = entry.get("observed")
    if not observed_candidates:
        return dict(expected)

    rng = random.Random(f"{seed}-{step}-{strategy_id}")
    weights = [c.get("weight", 1.0) for c in observed_candidates]
    chosen = rng.choices(observed_candidates, weights=weights, k=1)[0]
    # candidate may wrap the actual data under "values"
    return chosen.get("values", chosen)


def classify_outcome(expected: dict[str, Any], observed: dict[str, Any]) -> str:
    """Compare expected vs observed and produce a human-readable status."""
    if not observed:
        return "No outcome data"

    keys_to_compare = [
        "connection",
        "follow_up_conflicts",
        "network_state",
    ]
    mismatches = 0
    for key in keys_to_compare:
        if key in expected and key in observed and expected[key] != observed[key]:
            mismatches += 1

    # delay tolerance: > 1 min deviation counts as unexpected
    exp_delay = expected.get("additional_delay_min")
    obs_delay = observed.get("additional_delay_min")
    if exp_delay is not None and obs_delay is not None and abs(exp_delay - obs_delay) > 1:
        mismatches += 1

    return "Mostly as expected" if mismatches == 0 else "Unexpected outcome"
