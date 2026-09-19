"""Station and place names of a scene (app/core/station_names.py, /hmi/geography)."""
import json
import warnings

import pytest
from fastapi import HTTPException

warnings.filterwarnings("ignore")

from app.api.hmi import get_geography
from app.core.scenario_presets import select_disturbances
from app.core.session_manager import session_manager
from app.core.station_names import STATION_NAMES, scene_geography

SCENE = "app/fixtures/pf_ch/pf-ch-wn-wal-long-approach.scene.json"
PRESET = "pf-ch-wn-wal-long-approach"


def _scene():
    with open(SCENE, encoding="utf-8") as f:
        return json.load(f)


def test_platform_cells_carry_proper_names():
    geo = scene_geography(_scene())

    names = {s["code"]: s["name"] for s in geo["stations"]}
    assert names["ZB"] == "Ziegelbrücke"          # ASCII in the scene, proper form here
    assert names["SCBU"] == "Schübelbach-Buttikon"
    assert len(geo["stations"]) == 32
    first = next(s for s in geo["stations"] if s["code"] == "ZB")
    assert len(first["cell"]) == 2 and first["track"] is not None


def test_places_in_line_order_with_columns_and_the_single_track_section():
    geo = scene_geography(_scene())

    codes = [loc["code"] for loc in geo["locations"]]
    assert codes[0] == "PF" and codes[-1] == "CH" and len(codes) == 23
    cols = [loc["col"] for loc in geo["locations"]]
    assert cols == sorted(cols)
    # Places without tracks are named too, not left as codes.
    assert all(loc["name"] != loc["code"] for loc in geo["locations"])
    assert geo["single_track"] == ["MH", "TIEF"]
    assert STATION_NAMES["MH"] == "Mühlehorn" and STATION_NAMES["TIEF"] == "Tiefenwinkel"


def test_no_scene_gives_empty_lists():
    assert scene_geography(None) == {"stations": [], "locations": [], "single_track": []}
    assert scene_geography({"stations": [], "metadata": {}}) == {"stations": [], "locations": [], "single_track": []}


def test_endpoint_serves_the_session_scene():
    session = session_manager.create(
        scenario_preset_id=PRESET, disturbances=select_disturbances(PRESET, []),
    )

    geo = get_geography(session.id)

    assert any(s["name"] == "Walenstadt" for s in geo["stations"])
    assert geo["single_track"] == ["MH", "TIEF"]


def test_endpoint_unknown_session_is_404():
    with pytest.raises(HTTPException) as excinfo:
        get_geography("no-such-session")
    assert excinfo.value.status_code == 404
