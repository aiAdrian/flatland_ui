"""Derived, deterministic values for the Director-Mode dashboard.

Two pure helpers used by the UI:
- ``strategy_score`` turns a strategy's effect dict into a 0-100 score (as shown
  on the A/B/C cards in the MVP mockup).
- ``build_forecast`` produces the "Strategy Impact Forecast" table rows
  (Now / +10 / +20 / +30 min) for a chosen strategy.

No randomness: same inputs always give the same score/forecast.

The forecast is a small explicit delay-propagation model, not a simulation. It
carries three quantities forward over the horizon:

* corridor delay -- starts at the delay already in the situation plus what the
  chosen strategy adds, then decays by a fixed share per 10-minute step. The
  share depends on the strategy's ripple risk: a strategy that keeps the network
  loose recovers delay faster than one that leaves it tight.
* buffer of the critical connection -- the minutes of slack left at the
  junction. A strategy that protects the connection holds it; otherwise the
  additional delay eats into it, and the buffer recovers as the delay decays.
* trains involved -- the trains named in the situation, plus the trains pulled in
  by each follow-up conflict the strategy is expected to leave behind.

Every row reports the inputs it was derived from (``driver``), so the table can
answer "why this value" without a second data source. The model assumptions are
returned in ``assumptions`` and rendered as a footnote.
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


def _cell(text: str, color: str, value: float | None = None) -> dict[str, Any]:
    return {"text": text, "color": color, "value": value}


# how far the forecast stays reliable, by number of concurrent open problems.
# Few problems -> we can see & stabilise far ahead. Many -> the future blurs.
_RELIABLE_COLS = {0: 4, 1: 4, 2: 3, 3: 2}


def reliable_columns(open_problems: int) -> int:
    return _RELIABLE_COLS.get(open_problems, 1)


# --------------------------------------------------------------------------- #
# Forecast model constants
# --------------------------------------------------------------------------- #

# Share of the remaining corridor delay recovered per 10-minute step. A strategy
# that leaves the network loose (low ripple) absorbs delay faster.
_RECOVERY_BY_RIPPLE = {"low": 0.55, "medium": 0.35, "high": 0.20}
_DEFAULT_RECOVERY = 0.35

# How many follow-up conflicts a strategy is expected to leave, when the
# scenario does not state an expected outcome.
_FOLLOWUP_RISK_TO_COUNT = {"low": 0, "medium": 1, "high": 2}

_FOLLOWUP_DELAY_MIN = 3      # minutes each follow-up conflict injects
_FOLLOWUP_AT_STEP = 2        # it materialises in the +20 min column
_TRAINS_PER_FOLLOWUP = 2     # trains pulled into each follow-up conflict

_HORIZON_STEPS = 4           # Now / +10 / +20 / +30

# Column confidence ramp, seeded by the situation's own forecast confidence.
_CONFIDENCE_RAMP = {
    "high": ["high", "high", "medium", "lower"],
    "medium": ["high", "medium", "lower", "lower"],
    "low": ["medium", "lower", "lower", "lower"],
}

_PROTECTING_CONNECTION = ("protected", "kept", "excellent")


def _delay_series(start_delay: float, recovery: float, followups: int) -> list[float]:
    """Corridor delay per horizon step."""
    series = [max(0.0, start_delay)]
    for step in range(1, _HORIZON_STEPS):
        carried = series[-1] * (1.0 - recovery)
        if step == _FOLLOWUP_AT_STEP:
            carried += _FOLLOWUP_DELAY_MIN * followups
        series.append(max(0.0, carried))
    return series


def _delay_color(minutes: float) -> str:
    if minutes <= 1:
        return GREEN
    if minutes <= 4:
        return ORANGE
    return RED


def _buffer_color(minutes: float) -> str:
    if minutes < 0:
        return RED
    if minutes < 2:
        return ORANGE
    return GREEN


def expected_followups(effects: dict[str, Any],
                       expected: dict[str, Any] | None = None) -> int:
    """How many follow-up conflicts this strategy is expected to leave."""
    if expected and expected.get("follow_up_conflicts") is not None:
        return int(expected.get("follow_up_conflicts") or 0)
    risk = str(effects.get("follow_up_conflict_risk", "")).lower()
    return _FOLLOWUP_RISK_TO_COUNT.get(risk, 0)


def build_forecast(
    situation: dict[str, Any],
    effects: dict[str, Any],
    open_problems: int = 0,
    expected: dict[str, Any] | None = None,
    strategy_label: str | None = None,
) -> dict[str, Any]:
    """Build the forecast table for a chosen/recommended strategy.

    Values are computed from the situation (delay already in the corridor,
    connection buffer, trains involved) and the strategy's effects (added delay,
    connection impact, ripple risk, follow-up risk). See the module docstring for
    the model. Each row carries a ``driver`` naming the inputs behind its values.

    ``open_problems`` couples the two mechanics: with few open problems the
    forecast is reliable far out; each additional problem shrinks the reliable
    horizon and the far columns turn "uncertain".
    """
    time_label = situation.get("time_label", "now")
    base_confidence = str(situation.get("forecast_confidence", "medium")).lower()
    ramp = _CONFIDENCE_RAMP.get(base_confidence, _CONFIDENCE_RAMP["medium"])
    columns = [
        {"label": "Now", "sub": time_label, "confidence": ramp[0]},
        {"label": "+10 min", "sub": "", "confidence": ramp[1]},
        {"label": "+20 min", "sub": "", "confidence": ramp[2]},
        {"label": "+30 min", "sub": "", "confidence": ramp[3]},
    ]
    reliable = reliable_columns(open_problems)

    connection = str(effects.get("connection_impact", "")).lower()
    # the *strategy's* ripple risk drives recovery; the situation is the fallback
    ripple = str(
        effects.get("ripple_risk") or situation.get("ripple_risk") or "medium"
    ).lower()
    critical = bool(situation.get("critical_connection"))
    current_delay = float(situation.get("current_delay_min") or 0)
    added_delay = float(parse_delay_minutes(effects.get("delay_impact")))
    recovery = _RECOVERY_BY_RIPPLE.get(ripple, _DEFAULT_RECOVERY)
    followups = expected_followups(effects, expected)
    strategy_txt = strategy_label or "this option"

    delays = _delay_series(current_delay + added_delay, recovery, followups)

    # Row 1: delay carried in the corridor
    followup_note = (
        f"; {followups} expected follow-up conflict(s) add "
        f"{_FOLLOWUP_DELAY_MIN * followups} min at +{_FOLLOWUP_AT_STEP * 10} min"
        if followups
        else "; no follow-up conflicts expected"
    )
    conflict = situation.get("main_conflict")
    conflict_row = {
        "label": "Corridor delay",
        "icon": "⚠️",
        "unit": "min",
        "driver": (
            (f"{conflict}: " if conflict else "")
            + f"{current_delay:.0f} min already in the corridor + {added_delay:.0f} min "
            f"from {strategy_txt}; {recovery * 100:.0f} % recovered per 10 min at "
            f"{ripple} ripple risk{followup_note}"
        ),
        "cells": [
            _cell(f"{d:.0f} min", _delay_color(d), round(d, 1)) for d in delays
        ],
    }

    # Row 2: slack left on the critical connection
    if critical:
        buffer0 = float(situation.get("connection_buffer_min") or 0)
        protects = connection in _PROTECTING_CONNECTION
        broken = connection == "broken"
        if broken:
            buffers = [-1.0] * _HORIZON_STEPS
            driver = (
                f"{strategy_txt} gives the connection up — the {buffer0:.0f} min "
                f"buffer is not held"
            )
        elif protects:
            buffers = [buffer0] * _HORIZON_STEPS
            driver = (
                f"{strategy_txt} holds the connection, so the {buffer0:.0f} min "
                f"buffer at the junction stays intact"
            )
        else:
            # the extra delay above the pre-decision level eats into the buffer
            buffers = [buffer0 - max(0.0, d - current_delay) for d in delays]
            driver = (
                f"{buffer0:.0f} min buffer minus the delay above the current "
                f"{current_delay:.0f} min; it recovers as the delay is absorbed"
            )
        conn_cells = [
            _cell("missed" if b < 0 else f"{b:.0f} min", _buffer_color(b), round(b, 1))
            for b in buffers
        ]
        goal_label = "Buffer: critical connection"
    else:
        conn_cells = [_cell("n/a", GREY, None) for _ in range(_HORIZON_STEPS)]
        goal_label = "Buffer: no critical connection"
        driver = "no critical connection at stake in this situation"

    goal_row = {"label": goal_label, "icon": "🔗", "unit": "min",
                "driver": driver, "cells": conn_cells}

    # Row 3: how many trains are caught up in it
    involved = len(situation.get("affected_trains") or [])
    train_counts: list[int] = []
    for step, d in enumerate(delays):
        if d <= 1:
            train_counts.append(0)
            continue
        extra = _TRAINS_PER_FOLLOWUP * followups if step >= _FOLLOWUP_AT_STEP else 0
        train_counts.append(involved + extra)
    side_cells = [
        _cell(
            f"{n}",
            GREEN if n == 0 else (ORANGE if n <= involved else RED),
            n,
        )
        for n in train_counts
    ]
    side_row = {
        "label": "Trains involved",
        "icon": "🚆",
        "unit": "",
        "driver": (
            f"{involved} train(s) named in the situation"
            + (
                f", plus {_TRAINS_PER_FOLLOWUP} per follow-up conflict from "
                f"+{_FOLLOWUP_AT_STEP * 10} min"
                if followups
                else "; clears once the delay is under 1 min"
            )
        ),
        "cells": side_cells,
    }

    rows = [conflict_row, goal_row, side_row]

    # Couple with system load: beyond the reliable horizon the future is unknown.
    for col_idx in range(len(columns)):
        if col_idx >= reliable:
            columns[col_idx]["confidence"] = "unknown"
            for row in rows:
                row["cells"][col_idx] = _cell("uncertain", GREY, None)

    horizon_min = max(0, (reliable - 1) * 10)
    return {
        "columns": columns,
        "rows": rows,
        "reliable_cols": reliable,
        "horizon_min": horizon_min,
        "open_problems": open_problems,
        "assumptions": [
            f"{recovery * 100:.0f} % of the remaining delay is recovered per 10 min "
            f"({ripple} ripple risk)",
            f"each follow-up conflict adds {_FOLLOWUP_DELAY_MIN} min and "
            f"{_TRAINS_PER_FOLLOWUP} trains from +{_FOLLOWUP_AT_STEP * 10} min",
            f"column confidence starts at '{base_confidence}' (scenario forecast "
            f"confidence)",
        ],
    }
