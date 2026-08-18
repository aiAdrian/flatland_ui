"""Value axes behind the strategies + the operator's revealed value profile.

Each strategy expresses an underlying *value* the operator is optimising for.
Reading which value dominates their deliberate decisions turns the profile from
"strategy frequency" into "value stance" — the heart of the co-learning idea and
of the goal-conflict storylines (e.g. punctuality vs. passengers).
"""

from __future__ import annotations

from typing import Any

# strategy id -> value axis
STRATEGY_VALUE = {
    "minimize_delay": "Punctuality",
    "protect_critical_connection": "Passengers & connections",
    "stabilize_network": "Network stability",
    "avoid_follow_up_conflicts": "Network stability",
    "maintain_current_plan": "Non-intervention",
}

VALUE_LABEL = {
    "Punctuality": "Punctuality-first",
    "Passengers & connections": "Passenger-first",
    "Network stability": "Stability-first",
    "Non-intervention": "Hands-off",
}

# decisions that don't count as a deliberate value signal
_NON_EVIDENCE = {"quick_accept", "deferred_to_ai"}


def value_profile(episodes: list[dict[str, Any]],
                  evidence_only: bool = True) -> dict[str, Any]:
    """Return the operator's value profile from their decisions."""
    counts: dict[str, int] = {}
    for ep in episodes:
        ud = ep.get("user_decision", {})
        if evidence_only and ud.get("confirmation_mode") in _NON_EVIDENCE:
            continue
        value = STRATEGY_VALUE.get(ud.get("selected_strategy"))
        if value:
            counts[value] = counts.get(value, 0) + 1

    total = sum(counts.values())
    if total == 0:
        return {"dominant": None, "label": "—", "dominant_pct": 0,
                "distribution": [], "total": 0}

    distribution = sorted(
        ((v, round(c / total, 3), c) for v, c in counts.items()),
        key=lambda t: t[1], reverse=True,
    )
    dominant = distribution[0][0]
    return {
        "dominant": dominant,
        "label": VALUE_LABEL.get(dominant, dominant),
        "dominant_pct": round(distribution[0][1] * 100),
        "distribution": distribution,
        "total": total,
    }
