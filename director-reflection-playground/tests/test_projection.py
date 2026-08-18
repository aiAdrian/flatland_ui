"""Tests for the what-if network projection (consequences of a strategy)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from visualizations import projected_network  # noqa: E402


def _network():
    return {
        "nodes": [
            {"id": "west", "x": 80, "y": 190, "label": "W"},
            {"id": "center", "x": 560, "y": 190, "label": "C"},
            {"id": "east", "x": 1080, "y": 190, "label": "E"},
        ],
        "edges": [
            {"from": "west", "to": "center"},
            {"from": "center", "to": "east"},
        ],
        "trains": [
            {"id": "train_5", "label": "T5", "x": 200, "y": 190},
            {"id": "train_6", "label": "T6", "x": 700, "y": 190},
        ],
        "conflict_node": "center",
        "critical_connection": ["train_5", "train_6"],
    }


def test_protected_connection_marks_downstream_protected():
    net = projected_network(
        _network(),
        {"connection_impact": "Protected", "ripple_risk": "low"},
        {"connection": "Protected", "follow_up_conflicts": 0},
    )
    downstream = [e for e in net["edges"] if e["from"] == "center"]
    assert all(e.get("status") == "protected" for e in downstream)
    assert net["projected_conflicts"] == []


def test_broken_connection_breaks_trains():
    net = projected_network(
        _network(),
        {"connection_impact": "Broken", "ripple_risk": "high"},
        {"connection": "Broken", "follow_up_conflicts": 1},
    )
    broken_trains = [t for t in net["trains"] if t.get("broken")]
    assert len(broken_trains) == 2
    assert net["critical_connection"] == []
    # follow-up conflict projected on the easternmost node
    assert "east" in net["projected_conflicts"]


def test_ripple_marks_delay_propagation():
    net = projected_network(
        _network(),
        {"connection_impact": "At risk", "ripple_risk": "high"},
        {"connection": "At risk", "follow_up_conflicts": 0},
    )
    downstream = [e for e in net["edges"] if e["from"] == "center"]
    assert all(e.get("status") == "risk" for e in downstream)


def test_original_network_not_mutated():
    original = _network()
    projected_network(original, {"connection_impact": "Broken"},
                      {"connection": "Broken", "follow_up_conflicts": 2})
    assert all("broken" not in t for t in original["trains"])
    assert original["critical_connection"] == ["train_5", "train_6"]
