"""Counterfactual 'AI unattended' shift.

Deterministically replays the whole scenario as if the AI had executed its own
default recommendation at every decision point (no human intervention). Used in
the debrief to show, credibly, what the operator's judgement changed — not a
game score, an operational what-if.
"""

from __future__ import annotations

from typing import Any

from scenario_engine import Scenario, select_observed_outcome


def _passengers(situation: dict[str, Any]) -> int:
    p = situation.get("passengers")
    if isinstance(p, (int, float)):
        return int(p)
    return 90 if situation.get("critical_connection") else 0


def _is_bad(observed: dict[str, Any]) -> bool:
    return (
        int(observed.get("follow_up_conflicts", 0) or 0) > 0
        or str(observed.get("connection", "")).lower() == "broken"
        or str(observed.get("network_state", "")).lower() in ("strained", "unstable")
    )


def ai_only_shift(scenario: Scenario, seed: int) -> dict[str, Any]:
    """Accumulate KPIs for a fully AI-run shift (AI always takes its own default)."""
    kpis = {
        "added_delay_min": 0,
        "connections_kept": 0,
        "connections_lost": 0,
        "passengers_affected": 0,
        "follow_up_conflicts": 0,
        "open_problems": 0,
        "network_state": "stable",
    }
    for step, dp in enumerate(scenario.decision_points):
        strat = dp.get("baseline_recommendation")  # the optimiser's default
        observed = select_observed_outcome(dp, strat, seed, step)
        if not observed:
            continue
        kpis["added_delay_min"] += int(observed.get("additional_delay_min", 0) or 0)
        connection = str(observed.get("connection", "")).lower()
        if connection in ("protected", "kept"):
            kpis["connections_kept"] += 1
        elif connection == "broken":
            kpis["connections_lost"] += 1
            kpis["passengers_affected"] += _passengers(dp.get("situation", {}))
        kpis["follow_up_conflicts"] += int(observed.get("follow_up_conflicts", 0) or 0)
        if observed.get("network_state"):
            kpis["network_state"] = observed["network_state"]
        # unattended: a bad outcome just opens another problem (never stabilised)
        if _is_bad(observed):
            kpis["open_problems"] += 1
    return kpis
