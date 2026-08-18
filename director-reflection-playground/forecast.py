"""Derived, deterministic values for the Director-Mode dashboard.

Two pure helpers used by the UI:
- ``strategy_score`` turns a strategy's effect dict into a 0-100 score (as shown
  on the A/B/C cards in the MVP mockup).
- ``build_forecast`` produces the "Strategy Impact Forecast" table rows
  (Now / +10 / +20 / +30 min) for a chosen strategy.

No randomness: same inputs always give the same score/forecast.
"""

from __future__ import annotations

import re
from typing import Any

# colour tokens (kept in sync with visualizations.py)
RED = "#e5484d"
GREEN = "#30a46c"
BLUE = "#0091ff"
ORANGE = "#f76b15"
GREY = "#8b8d98"

_RISK_PENALTY = {"low": 0, "medium": 12, "high": 24, None: 8, "": 8}
_FOLLOWUP_PENALTY = {"low": 0, "medium": 10, "high": 20, None: 6, "": 6}
_CONNECTION_BONUS = {
    "protected": 10,
    "excellent": 12,
    "kept": 10,
    "fair": -2,
    "at risk": -6,
    "broken": -22,
}


def parse_delay_minutes(delay_impact: str | int | None) -> int:
    if delay_impact is None:
        return 0
    if isinstance(delay_impact, (int, float)):
        return int(delay_impact)
    match = re.search(r"-?\d+", str(delay_impact))
    return int(match.group()) if match else 0


def strategy_score(effects: dict[str, Any]) -> int:
    """Map a strategy effect dict to a 0-100 score (higher = better)."""
    delay = parse_delay_minutes(effects.get("delay_impact"))
    ripple = str(effects.get("ripple_risk", "")).lower()
    followup = str(effects.get("follow_up_conflict_risk", "")).lower()
    connection = str(effects.get("connection_impact", "")).lower()

    score = 100
    score -= delay * 7
    score -= _RISK_PENALTY.get(ripple, 8)
    score -= _FOLLOWUP_PENALTY.get(followup, 6)
    score += _CONNECTION_BONUS.get(connection, 0)
    return max(0, min(100, round(score)))


def _cell(text: str, color: str) -> dict[str, str]:
    return {"text": text, "color": color}


# how far the forecast stays reliable, by number of concurrent open problems.
# Few problems -> we can see & stabilise far ahead. Many -> the future blurs.
_RELIABLE_COLS = {0: 4, 1: 4, 2: 3, 3: 2}


def reliable_columns(open_problems: int) -> int:
    return _RELIABLE_COLS.get(open_problems, 1)


def build_forecast(
    situation: dict[str, Any],
    effects: dict[str, Any],
    open_problems: int = 0,
) -> dict[str, Any]:
    """Build the forecast table for a chosen/recommended strategy.

    ``open_problems`` couples the two mechanics: with few open problems the
    forecast is reliable far out; each additional problem shrinks the reliable
    horizon and the far columns turn "uncertain".

    Returns ``{"columns", "rows", "reliable_cols", "horizon_min", "open_problems"}``.
    """
    time_label = situation.get("time_label", "now")
    columns = [
        {"label": "Now", "sub": time_label, "confidence": "high"},
        {"label": "+10 min", "sub": "", "confidence": "high"},
        {"label": "+20 min", "sub": "", "confidence": "medium"},
        {"label": "+30 min", "sub": "", "confidence": "lower"},
    ]
    reliable = reliable_columns(open_problems)

    connection = str(effects.get("connection_impact", "")).lower()
    ripple = str(situation.get("ripple_risk", "medium")).lower()
    critical = bool(situation.get("critical_connection"))

    # Row 1: main conflict resolution
    conflict_row = {
        "label": situation.get("main_conflict", "Main conflict"),
        "icon": "⚠️",
        "cells": [
            _cell("Active", RED),
            _cell("Resolving", ORANGE),
            _cell("Resolved", GREEN),
            _cell("Stable", BLUE),
        ],
    }

    # Row 2: primary goal (critical connection)
    if critical:
        if connection in ("protected", "excellent", "kept"):
            conn_cells = [
                _cell("At risk", RED),
                _cell("Protected", GREEN),
                _cell("Kept", GREEN),
                _cell("Kept", BLUE),
            ]
        elif connection == "broken":
            conn_cells = [
                _cell("At risk", RED),
                _cell("Broken", RED),
                _cell("Broken", RED),
                _cell("Broken", RED),
            ]
        else:  # at risk / fair
            conn_cells = [
                _cell("At risk", RED),
                _cell("At risk", ORANGE),
                _cell("Uncertain", ORANGE),
                _cell("Uncertain", BLUE),
            ]
        goal_label = "Primary goal: critical connection"
    else:
        conn_cells = [_cell("n/a", GREY)] * 4
        goal_label = "Primary goal: keep schedule"

    goal_row = {"label": goal_label, "icon": "🔗", "cells": conn_cells}

    # Row 3: side effect (network load / ripple)
    if ripple == "high":
        side_cells = [
            _cell("High", RED),
            _cell("Improving", ORANGE),
            _cell("Medium", ORANGE),
            _cell("Stable", GREEN),
        ]
    elif ripple == "medium":
        side_cells = [
            _cell("Medium", ORANGE),
            _cell("Improving", ORANGE),
            _cell("Low", GREEN),
            _cell("Stable", GREEN),
        ]
    else:  # low
        side_cells = [
            _cell("Low", GREEN),
            _cell("Low", GREEN),
            _cell("Low", GREEN),
            _cell("Stable", BLUE),
        ]
    side_row = {"label": "Side effect: network load / ripple risk",
                "icon": "🌊", "cells": side_cells}

    rows = [conflict_row, goal_row, side_row]

    # Couple with system load: beyond the reliable horizon the future is unknown.
    for col_idx in range(len(columns)):
        if col_idx >= reliable:
            columns[col_idx]["confidence"] = "unknown"
            for row in rows:
                row["cells"][col_idx] = _cell("uncertain", GREY)

    horizon_min = max(0, (reliable - 1) * 10)
    return {
        "columns": columns,
        "rows": rows,
        "reliable_cols": reliable,
        "horizon_min": horizon_min,
        "open_problems": open_problems,
    }
