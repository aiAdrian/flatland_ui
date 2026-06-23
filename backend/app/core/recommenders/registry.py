"""Registry of intervention recommenders (the tactical recommendation seam).

Add a new engine by registering it here; the active one is resolved by id. This
mirrors the policy registry so trained/alternative algorithms plug in without
touching the API or frontend.
"""
from __future__ import annotations

from typing import Dict, List

from app.core.recommenders.base import InterventionRecommender
from app.core.recommenders.phase1_proximity import Phase1ProximityRecommender

_REGISTRY: Dict[str, InterventionRecommender] = {}


def register(recommender: InterventionRecommender) -> None:
    _REGISTRY[recommender.id] = recommender


# Built-in recommenders.
register(Phase1ProximityRecommender())

# Default active recommender id (later: selectable per session / in settings).
_ACTIVE_ID = "proximity"


def list_recommenders() -> List[InterventionRecommender]:
    return list(_REGISTRY.values())


def get_recommender(rec_id: str) -> InterventionRecommender | None:
    return _REGISTRY.get(rec_id)


def active_recommender() -> InterventionRecommender:
    return _REGISTRY.get(_ACTIVE_ID) or next(iter(_REGISTRY.values()))
