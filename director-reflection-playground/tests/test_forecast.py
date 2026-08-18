"""Tests for the deterministic scoring and forecast helpers."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forecast import build_forecast, parse_delay_minutes, strategy_score  # noqa: E402


def test_parse_delay_minutes():
    assert parse_delay_minutes("+2 min") == 2
    assert parse_delay_minutes("+0 min") == 0
    assert parse_delay_minutes("-1 min") == -1
    assert parse_delay_minutes(3) == 3
    assert parse_delay_minutes(None) == 0


def test_score_is_bounded_0_100():
    bad = {"delay_impact": "+30 min", "connection_impact": "Broken",
           "ripple_risk": "high", "follow_up_conflict_risk": "high"}
    good = {"delay_impact": "+0 min", "connection_impact": "Protected",
            "ripple_risk": "low", "follow_up_conflict_risk": "low"}
    assert 0 <= strategy_score(bad) <= 100
    assert 0 <= strategy_score(good) <= 100
    assert strategy_score(good) > strategy_score(bad)


def test_protected_low_ripple_scores_high():
    eff = {"delay_impact": "+2 min", "connection_impact": "Protected",
           "ripple_risk": "low", "follow_up_conflict_risk": "low"}
    assert strategy_score(eff) >= 90


def test_score_is_deterministic():
    eff = {"delay_impact": "+1 min", "connection_impact": "At risk",
           "ripple_risk": "medium", "follow_up_conflict_risk": "low"}
    assert strategy_score(eff) == strategy_score(eff)


def test_forecast_has_three_rows_and_four_columns():
    situation = {"critical_connection": True, "ripple_risk": "high",
                 "main_conflict": "West Junction", "time_label": "09:54"}
    effects = {"connection_impact": "Protected", "ripple_risk": "low"}
    fc = build_forecast(situation, effects)
    assert len(fc["columns"]) == 4
    assert len(fc["rows"]) == 3
    for row in fc["rows"]:
        assert len(row["cells"]) == 4
        assert all("text" in c and "color" in c for c in row["cells"])


def test_forecast_protected_connection_progression():
    situation = {"critical_connection": True, "ripple_risk": "medium"}
    effects = {"connection_impact": "Protected"}
    fc = build_forecast(situation, effects)
    goal_row = fc["rows"][1]
    texts = [c["text"] for c in goal_row["cells"]]
    assert texts[0] == "At risk"
    assert "Protected" in texts


def test_open_problems_shrink_forecast_horizon():
    situation = {"critical_connection": True, "ripple_risk": "high"}
    eff = {"connection_impact": "Protected", "ripple_risk": "low"}

    fc0 = build_forecast(situation, eff, open_problems=0)
    assert fc0["reliable_cols"] == 4
    assert fc0["horizon_min"] == 30
    assert all(c["confidence"] != "unknown" for c in fc0["columns"])

    fc3 = build_forecast(situation, eff, open_problems=3)
    assert fc3["reliable_cols"] == 2
    assert fc3["horizon_min"] == 10
    assert fc3["columns"][3]["confidence"] == "unknown"
    assert all(row["cells"][3]["text"] == "uncertain" for row in fc3["rows"])

    fc_many = build_forecast(situation, eff, open_problems=5)
    assert fc_many["reliable_cols"] == 1  # only "now" is trustworthy


def test_forecast_no_critical_connection_is_na():
    situation = {"critical_connection": False, "ripple_risk": "low"}
    fc = build_forecast(situation, {"connection_impact": "At risk"})
    goal_row = fc["rows"][1]
    assert all(c["text"] == "n/a" for c in goal_row["cells"])
