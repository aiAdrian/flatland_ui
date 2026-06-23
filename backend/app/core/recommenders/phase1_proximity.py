"""Phase-1 proximity recommender: the first concrete InterventionRecommender.

Wraps the existing impact analysis (path/ETA intersection with the blocked cell +
coarse reroute/hold suggestion). Later recommenders (greedy what-if, PP replan,
RL) implement the same interface and register alongside this one.
"""
from __future__ import annotations

from typing import Any, Dict, List

from flatland.envs.rail_env import RailEnv

from app.core.impact_analysis import compute_impact
from app.core.recommenders.base import InterventionRecommender


class Phase1ProximityRecommender(InterventionRecommender):
    id = "proximity"
    label = "Proximity (Phase 1)"
    description = (
        "Flags trains whose path crosses the malfunction's blocked cell before it "
        "clears; suggests reroute (if a switch is reachable first) or hold."
    )

    def recommend(self, env: RailEnv) -> List[Dict[str, Any]]:
        return compute_impact(env)
