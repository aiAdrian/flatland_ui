"""Scenario-quality tests: every offered option must be a real trade-off
(Pareto-optimal on at least one axis), i.e. no dominated "bad" option."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scenario_engine import list_scenarios  # noqa: E402

_CONN = {"protected": 2, "excellent": 2, "kept": 2, "fair": 1, "at risk": 1, "broken": 0}
_LVL = {"low": 2, "medium": 1, "high": 0}


def _delay(s):
    m = re.search(r"-?\d+", s or "+0")
    return int(m.group()) if m else 0


def _vec(e):
    return (
        -_delay(e.get("delay_impact", "")),                      # less delay = better
        _CONN.get(str(e.get("connection_impact", "")).lower(), 1),
        _LVL.get(str(e.get("ripple_risk", "")).lower(), 1),
        _LVL.get(str(e.get("follow_up_conflict_risk", "")).lower(), 1),
    )


def _dominates(a, b):
    return all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b))


def test_no_offered_option_is_dominated():
    offenders = []
    for sc in list_scenarios():
        for dp in sc.decision_points:
            eff = dp["strategy_effects"]
            vs = {s: _vec(eff[s]) for s in dp["strategies"] if s in eff}
            for s1 in vs:
                for s2 in vs:
                    if s1 != s2 and _dominates(vs[s2], vs[s1]):
                        offenders.append(f"{sc.scenario_id} step {dp['step']}: "
                                         f"{s1} dominated by {s2}")
    assert not offenders, "dominated options:\n" + "\n".join(offenders)


# Note: we intentionally do NOT require every option to be strictly best on some
# axis — a non-dominated *compromise* (2nd on several axes, beaten by no single
# option) is a legitimate, realistic choice. Absence of *dominated* options is
# the quality criterion.
