"""Continuous-shift timeline engine (Live Director Mode).

The railway "runs" on a simulated clock. Between director moments the clock
advances on its own; when it reaches a scheduled decision the shift enters an
``awaiting`` state with a real-time deadline. If the deadline passes the AI acts
by default (the caller handles the ``timeout``).

This module is deliberately free of Streamlit and wall-clock calls: ``tick``
takes elapsed seconds, so the whole state machine is unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Diegetic decision window in *simulated minutes* — the lead time until the train
# physically reaches the decision point (junction / scheduled departure). In real
# dispatching this is a few minutes, tighter under disruptions; it is not a fixed
# real-time budget. Fallback per pressure when a scenario doesn't specify one.
WINDOW_MIN_BY_PRESSURE = {"LOW": 6, "MEDIUM": 5, "HIGH": 3, "STRESS": 2}

# how the diegetic window maps to real seconds on screen (compressed but calm).
# Floor keeps it unhurried (never below 30s); longer lead times get more time.
SECONDS_PER_SIM_MIN = 10.0
MIN_DECIDE_S = 30.0
MAX_DECIDE_S = 60.0


def decide_seconds_for(window_min: float) -> float:
    return max(MIN_DECIDE_S, min(MAX_DECIDE_S, window_min * SECONDS_PER_SIM_MIN))

STATUS_RUNNING = "running"
STATUS_AWAITING = "awaiting"
STATUS_ENDED = "ended"


def parse_time_label(label: str) -> int:
    """Parse 'HH:MM' into minutes since midnight. Returns 0 on failure."""
    m = re.match(r"\s*(\d{1,2}):(\d{2})", str(label))
    if not m:
        return 0
    return int(m.group(1)) * 60 + int(m.group(2))


def format_clock(minutes: float) -> str:
    total = int(round(minutes))
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


@dataclass
class ShiftEvent:
    index: int          # index into scenario.decision_points
    sim_time: int       # minutes since midnight
    decide_s: float     # real seconds allowed to decide (compressed window)
    severity: str = "intervention"  # "intervention" pauses; "info" is AI-handled
    window_min: float = 5.0  # diegetic lead time in simulated minutes


@dataclass
class Shift:
    events: list[ShiftEvent]
    start_min: float
    end_min: float
    speed: float                       # sim-minutes advanced per real second
    clock_min: float = 0.0
    status: str = STATUS_RUNNING
    next_i: int = 0                    # pointer into events
    pending_index: int | None = None   # decision_point index currently awaited
    remaining_decide_s: float = 0.0

    def __post_init__(self) -> None:
        if not self.clock_min:
            self.clock_min = self.start_min

    @property
    def progress(self) -> float:
        span = self.end_min - self.start_min
        if span <= 0:
            return 1.0
        return max(0.0, min(1.0, (self.clock_min - self.start_min) / span))

    def tick(self, elapsed_s: float) -> str | None:
        """Advance by ``elapsed_s`` real seconds.

        Returns an event token: ``"await"`` (a decision is now required),
        ``"timeout"`` (decision deadline passed), ``"ended"`` (shift finished),
        or ``None``.
        """
        if self.status == STATUS_RUNNING:
            self.clock_min += elapsed_s * self.speed
            if self.next_i < len(self.events):
                nxt = self.events[self.next_i]
                if self.clock_min >= nxt.sim_time:
                    self.clock_min = nxt.sim_time
                    self.pending_index = nxt.index
                    if nxt.severity == "info":
                        # AI handles it autonomously; keep running
                        self.next_i += 1
                        return "auto"
                    self.status = STATUS_AWAITING
                    self.remaining_decide_s = nxt.decide_s
                    return "await"
            if self.clock_min >= self.end_min:
                self.clock_min = self.end_min
                self.status = STATUS_ENDED
                return "ended"
        elif self.status == STATUS_AWAITING:
            self.remaining_decide_s -= elapsed_s
            if self.remaining_decide_s <= 0:
                self.remaining_decide_s = 0.0
                return "timeout"
        return None

    def resolve(self) -> str | None:
        """Called after a decision or a timeout is handled; resume the shift."""
        self.next_i += 1
        self.pending_index = None
        if self.next_i >= len(self.events) and self.clock_min >= self.end_min:
            self.status = STATUS_ENDED
            return "ended"
        self.status = STATUS_RUNNING
        return None


def build_shift(scenario: Any, speed: float = 3.0, lead_min: int = 3,
                tail_min: int = 4) -> Shift:
    """Build a Shift from a scenario's decision points (ordered by time label)."""
    dps = scenario.decision_points
    events: list[ShiftEvent] = []
    for i, dp in enumerate(dps):
        sim_time = parse_time_label(dp.get("time_label", ""))
        situation = dp.get("situation", {})
        # diegetic window: explicit field > connection buffer > pressure default
        window_min = dp.get("decision_window_min")
        if window_min is None:
            window_min = situation.get("connection_buffer_min")
        if window_min is None:
            window_min = WINDOW_MIN_BY_PRESSURE.get(
                dp.get("operational_pressure", "MEDIUM"), 5)
        window_min = float(window_min)
        severity = dp.get("event", {}).get("severity", "intervention")
        events.append(ShiftEvent(
            index=i, sim_time=sim_time, decide_s=decide_seconds_for(window_min),
            severity=severity, window_min=window_min))
    events.sort(key=lambda e: e.sim_time)

    if events:
        start_min = events[0].sim_time - lead_min
        end_min = events[-1].sim_time + tail_min
    else:
        start_min, end_min = 0, 0
    return Shift(events=events, start_min=start_min, end_min=end_min, speed=speed,
                 clock_min=start_min)
