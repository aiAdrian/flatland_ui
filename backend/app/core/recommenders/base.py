"""Intervention recommender seam.

This is the **tactical** recommendation seam — "what local action resolves this
malfunction" (reroute / hold / reorder a specific train) — as opposed to the
**strategic** policy seam (`app/policies`, "switch the whole-system policy").

Keeping this behind a stable interface means the engine that produces
interventions can be swapped freely without touching the API or the frontend:
  - Phase 1: proximity (which trains hit the block before it clears) — built.
  - Phase 2: greedy what-if (simulate + score per train) — planned.
  - Phase 2: PP replan (block the cell, re-plan affected trains coherently) — planned.
  - Later: a trained RL recommender — planned.

Data contract (per affected train) is a plain dict so the frontend stays stable:
    {
      handle, blocked_by, blocked_cell [r,c], eta_steps, clears_in_steps,
      can_reroute, recommended_action ('reroute'|'hold'|...), severity
    }
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from flatland.envs.rail_env import RailEnv


class InterventionRecommender(ABC):
    """Produces local intervention recommendations for the current env state."""

    #: stable id (used by the registry / future selection in settings)
    id: str = "base"
    #: short human label
    label: str = "Base"
    #: one-line description
    description: str = ""

    @abstractmethod
    def recommend(self, env: RailEnv) -> List[Dict[str, Any]]:
        """Return a list of affected-train intervention items (see module doc).
        Empty list when there's nothing to recommend."""
        raise NotImplementedError
