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


def test_every_row_reports_its_driver():
    """The table has to be able to answer 'why this value' for each row."""
    situation = {"critical_connection": True, "connection_buffer_min": 4,
                 "current_delay_min": 2, "affected_trains": ["t1", "t2"]}
    fc = build_forecast(situation, {"connection_impact": "Protected",
                                    "ripple_risk": "low"})
    assert all(row["driver"] for row in fc["rows"])
    assert fc["assumptions"]


def test_delay_row_starts_at_current_plus_added_and_decays():
    situation = {"critical_connection": False, "current_delay_min": 2,
                 "affected_trains": ["t1"]}
    effects = {"delay_impact": "+3 min", "ripple_risk": "low",
               "connection_impact": "At risk", "follow_up_conflict_risk": "low"}
    delay_row = build_forecast(situation, effects)["rows"][0]
    values = [c["value"] for c in delay_row["cells"]]
    assert values[0] == 5.0  # 2 already there + 3 added by the strategy
    assert values[0] > values[1] > values[2] > values[3]  # absorbed over time


def test_low_ripple_recovers_faster_than_high_ripple():
    situation = {"critical_connection": False, "current_delay_min": 4,
                 "affected_trains": ["t1"]}
    base = {"delay_impact": "+2 min", "connection_impact": "At risk",
            "follow_up_conflict_risk": "low"}
    loose = build_forecast(situation, {**base, "ripple_risk": "low"})
    tight = build_forecast(situation, {**base, "ripple_risk": "high"})
    assert loose["rows"][0]["cells"][3]["value"] < tight["rows"][0]["cells"][3]["value"]


def test_follow_up_conflicts_inject_delay_and_trains():
    situation = {"critical_connection": False, "current_delay_min": 2,
                 "affected_trains": ["t1", "t2"]}
    clean = {"delay_impact": "+1 min", "ripple_risk": "low",
             "connection_impact": "At risk", "follow_up_conflict_risk": "low"}
    messy = {**clean, "follow_up_conflict_risk": "high"}

    fc_clean = build_forecast(situation, clean)
    fc_messy = build_forecast(situation, messy)

    # the +20 min column is where a follow-up conflict materialises
    assert fc_messy["rows"][0]["cells"][2]["value"] > fc_clean["rows"][0]["cells"][2]["value"]
    assert fc_messy["rows"][2]["cells"][2]["value"] > fc_clean["rows"][2]["cells"][2]["value"]


def test_protecting_strategy_holds_the_connection_buffer():
    situation = {"critical_connection": True, "connection_buffer_min": 4,
                 "current_delay_min": 2}
    fc = build_forecast(situation, {"connection_impact": "Protected",
                                    "delay_impact": "+3 min",
                                    "ripple_risk": "low"})
    buffers = [c["value"] for c in fc["rows"][1]["cells"]]
    assert buffers == [4.0, 4.0, 4.0, 4.0]


def test_unprotected_strategy_eats_the_buffer_and_recovers():
    situation = {"critical_connection": True, "connection_buffer_min": 4,
                 "current_delay_min": 2}
    fc = build_forecast(situation, {"connection_impact": "At risk",
                                    "delay_impact": "+3 min",
                                    "ripple_risk": "low"})
    buffers = [c["value"] for c in fc["rows"][1]["cells"]]
    assert buffers[0] == 1.0  # 4 min buffer minus the 3 min this option adds
    assert buffers[-1] > buffers[0]  # slack returns as the delay is absorbed


def test_added_delay_beyond_the_buffer_misses_the_connection():
    situation = {"critical_connection": True, "connection_buffer_min": 2,
                 "current_delay_min": 1}
    fc = build_forecast(situation, {"connection_impact": "At risk",
                                    "delay_impact": "+6 min",
                                    "ripple_risk": "medium"})
    assert fc["rows"][1]["cells"][0]["text"] == "missed"


def test_broken_connection_is_missed_across_the_horizon():
    situation = {"critical_connection": True, "connection_buffer_min": 4,
                 "current_delay_min": 2}
    fc = build_forecast(situation, {"connection_impact": "Broken",
                                    "delay_impact": "+1 min"})
    assert all(c["text"] == "missed" for c in fc["rows"][1]["cells"])


def test_expected_outcome_overrides_follow_up_risk():
    situation = {"critical_connection": False, "current_delay_min": 2,
                 "affected_trains": ["t1"]}
    effects = {"delay_impact": "+1 min", "ripple_risk": "low",
               "connection_impact": "At risk", "follow_up_conflict_risk": "low"}
    fc = build_forecast(situation, effects, expected={"follow_up_conflicts": 2})
    assert fc["rows"][0]["cells"][2]["value"] > fc["rows"][0]["cells"][1]["value"]


def test_scenario_confidence_seeds_the_column_ramp():
    situation = {"critical_connection": False, "forecast_confidence": "low"}
    fc = build_forecast(situation, {"connection_impact": "At risk"})
    assert fc["columns"][0]["confidence"] == "medium"  # never "high" when unsure


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
