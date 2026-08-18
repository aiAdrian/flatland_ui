"""Tests for the continuous-shift timeline engine."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation import (  # noqa: E402
    STATUS_AWAITING,
    STATUS_ENDED,
    STATUS_RUNNING,
    Shift,
    ShiftEvent,
    build_shift,
    format_clock,
    parse_time_label,
)
from scenario_engine import load_scenario  # noqa: E402


def test_parse_time_label():
    assert parse_time_label("09:54") == 9 * 60 + 54
    assert parse_time_label("00:00") == 0
    assert parse_time_label("bad") == 0


def test_format_clock():
    assert format_clock(9 * 60 + 5) == "09:05"
    assert format_clock(0) == "00:00"


def _simple_shift(speed=1.0):
    events = [
        ShiftEvent(index=0, sim_time=10, decide_s=5),
        ShiftEvent(index=1, sim_time=20, decide_s=5),
    ]
    return Shift(events=events, start_min=7, end_min=24, speed=speed)


def test_running_reaches_first_event():
    shift = _simple_shift(speed=1.0)
    assert shift.tick(2) is None          # 7 -> 9
    assert shift.status == STATUS_RUNNING
    token = shift.tick(2)                  # 9 -> 11 >= 10
    assert token == "await"
    assert shift.status == STATUS_AWAITING
    assert shift.clock_min == 10
    assert shift.pending_index == 0


def test_deadline_timeout():
    shift = _simple_shift()
    shift.tick(4)  # to 11 -> await
    assert shift.status == STATUS_AWAITING
    assert shift.tick(3) is None           # remaining 5 -> 2
    assert shift.tick(3) == "timeout"      # remaining 2 -> <=0


def test_resolve_advances_and_ends():
    shift = _simple_shift(speed=1.0)
    shift.tick(4)          # await event 0
    shift.resolve()        # back to running, next_i = 1
    assert shift.status == STATUS_RUNNING
    # advance to second event
    token = None
    for _ in range(20):
        token = shift.tick(1)
        if token:
            break
    assert token == "await"
    assert shift.pending_index == 1
    shift.resolve()
    # now run out to the end
    token = None
    for _ in range(30):
        token = shift.tick(1)
        if token == "ended":
            break
    assert shift.status == STATUS_ENDED


def test_build_shift_from_scenario():
    scenario = load_scenario("easy_morning")
    shift = build_shift(scenario, speed=2.0)
    assert len(shift.events) == len(scenario.decision_points)
    # events sorted by sim_time, start before first event
    times = [e.sim_time for e in shift.events]
    assert times == sorted(times)
    assert shift.start_min <= shift.events[0].sim_time
    assert shift.end_min >= shift.events[-1].sim_time
