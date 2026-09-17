from app.core.scenario_presets import list_presets, select_disturbances

PRESET = "pf-ch-wn-wal-long-approach"
TOUR_ID = "interview-e1-breakdown-single-track"


def test_tour_disturbance_is_selectable_by_id():
    selected = select_disturbances(PRESET, [TOUR_ID])
    assert [d["id"] for d in selected] == [TOUR_ID]


def test_tour_disturbance_is_not_offered_in_the_picker():
    preset = next(p for p in list_presets() if p["id"] == PRESET)
    assert TOUR_ID not in {d["id"] for d in preset["disturbances"]}
    assert "tour_disturbances" not in preset


def test_study_disturbances_are_still_offered():
    preset = next(p for p in list_presets() if p["id"] == PRESET)
    assert "e1-late-into-the-section" in {d["id"] for d in preset["disturbances"]}
