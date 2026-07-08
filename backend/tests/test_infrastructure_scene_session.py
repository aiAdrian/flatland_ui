import warnings

warnings.filterwarnings("ignore")

from app.core.session_manager import session_manager
from app.core.infrastructure_scene_adapter import build_scene_diagnostics, count_routable_agents, _tokens_for_cell, _transition_value
from app.core.tile_resolver import resolve_tile


def _straight_scene():
    return {
        "id": "probe_scene",
        "grid": {"width": 8, "height": 5, "cellSizePx": 28},
        "cells": [
            {"id": "cell_1_2", "x": 1, "y": 2, "kind": "track", "connections": ["E"]},
            {"id": "cell_2_2", "x": 2, "y": 2, "kind": "track", "connections": ["E", "W"]},
            {"id": "cell_3_2", "x": 3, "y": 2, "kind": "track", "connections": ["E", "W"]},
            {"id": "cell_4_2", "x": 4, "y": 2, "kind": "track", "connections": ["E", "W"]},
            {"id": "cell_5_2", "x": 5, "y": 2, "kind": "track", "connections": ["E", "W"]},
            {"id": "cell_6_2", "x": 6, "y": 2, "kind": "track", "connections": ["W"]},
        ],
        "agents": [
            {
                "id": "agent_1",
                "name": "Train 1",
                "speed": 1,
                "startCellId": "cell_1_2",
                "targetCellId": "cell_6_2",
                "start": {"x": 1, "y": 2},
                "target": {"x": 6, "y": 2},
            }
        ],
        "stations": [],
        "validation": {"valid": True, "errors": [], "warnings": []},
    }


def test_session_manager_uses_infrastructure_scene_for_env_generation():
    session = session_manager.create(
        width=30,
        height=30,
        number_of_agents=3,
        seed=42,
        max_num_cities=2,
        max_rails_between_cities=2,
        max_rail_pairs_in_city=2,
        max_episode_steps=100,
        latest_departure_max=20,
        speed_profile="uniform_1_0",
        line_length=4,
        malfunction_rate=0,
        malfunction_min_duration=5,
        malfunction_max_duration=20,
        infrastructure_scene=_straight_scene(),
    )

    assert session.infrastructure_scene_id == "probe_scene"
    assert session.env.width == 8
    assert session.env.height == 5
    assert len(session.env.agents) == 1
    assert int((session.env.rail.grid != 0).sum()) == 6


def test_infrastructure_scene_train_can_depart_from_builder_endpoint():
    session = session_manager.create(
        width=30,
        height=30,
        number_of_agents=count_routable_agents(_straight_scene()),
        seed=42,
        max_num_cities=2,
        max_rails_between_cities=2,
        max_rail_pairs_in_city=2,
        max_episode_steps=100,
        latest_departure_max=0,
        speed_profile="uniform_1_0",
        line_length=4,
        malfunction_rate=0,
        malfunction_min_duration=5,
        malfunction_max_duration=20,
        infrastructure_scene=_straight_scene(),
    )

    agent = session.env.agents[0]
    assert agent.initial_direction == 3
    assert session.env.rail.get_transitions((agent.initial_position, agent.initial_direction)) == (0, 1, 0, 0)

    session.env.step({0: 2})
    session.env.step({0: 2})
    session.env.step({0: 2})

    assert agent.position == (2, 2)
    assert agent.direction == 1
    assert getattr(agent.state, "name", str(agent.state)) == "MOVING"


def test_infrastructure_scene_skips_unrouted_agents_without_handle_gaps():
    scene = _straight_scene()
    scene["agents"] = [
        {"id": "draft_agent", "name": "Draft Train", "speed": 1},
        *scene["agents"],
    ]

    assert count_routable_agents(scene) == 1

    session = session_manager.create(
        width=30,
        height=30,
        number_of_agents=count_routable_agents(scene),
        seed=42,
        max_num_cities=2,
        max_rails_between_cities=2,
        max_rail_pairs_in_city=2,
        max_episode_steps=100,
        latest_departure_max=20,
        speed_profile="uniform_1_0",
        line_length=4,
        malfunction_rate=0,
        malfunction_min_duration=5,
        malfunction_max_duration=20,
        infrastructure_scene=scene,
    )

    assert session.infrastructure_scene_id == "probe_scene"
    assert len(session.env.agents) == 1
    assert session.env.agents[0].initial_position == (2, 1)


def test_infrastructure_scene_switch_exports_as_known_switch_tile():
    scene = _straight_scene()
    scene["cells"] = [
        {"id": "cell_1_2", "x": 1, "y": 2, "kind": "track", "connections": ["E"]},
        {"id": "cell_2_2", "x": 2, "y": 2, "kind": "track", "connections": ["E", "W"]},
        {"id": "cell_3_2", "x": 3, "y": 2, "kind": "switch", "connections": ["N", "E", "W"]},
        {"id": "cell_4_2", "x": 4, "y": 2, "kind": "track", "connections": ["E", "W"]},
        {"id": "cell_5_2", "x": 5, "y": 2, "kind": "track", "connections": ["W"]},
        {"id": "cell_3_1", "x": 3, "y": 1, "kind": "track", "connections": ["S"]},
    ]
    scene["agents"][0].update({
        "targetCellId": "cell_5_2",
        "target": {"x": 5, "y": 2},
    })

    session = session_manager.create(
        width=30,
        height=30,
        number_of_agents=count_routable_agents(scene),
        seed=42,
        max_num_cities=2,
        max_rails_between_cities=2,
        max_rail_pairs_in_city=2,
        max_episode_steps=100,
        latest_departure_max=20,
        speed_profile="uniform_1_0",
        line_length=4,
        malfunction_rate=0,
        malfunction_min_duration=5,
        malfunction_max_duration=20,
        infrastructure_scene=scene,
    )

    resolved = resolve_tile(int(session.env.rail.grid[2, 3]))
    assert resolved is not None
    assert resolved[0].startswith("Weiche_")

    diagnostics = build_scene_diagnostics(scene, session.env)
    assert diagnostics["scene_cell_count"] == 6
    assert diagnostics["rail_cell_count"] == 6
    assert diagnostics["scene_switch_count"] == 1
    assert diagnostics["rail_switch_tile_count"] == 1
    assert diagnostics["unknown_tile_count"] == 0
    assert diagnostics["mismatched_cell_count"] == 0


def test_infrastructure_scene_switch_visuals_match_builder_canvas():
    cases = [
        (["N", "E", "W"], "forward", ("Weiche_horizontal_oben_rechts.svg", 0)),
        (["N", "E", "W"], "reverse", ("Weiche_horizontal_oben_links.svg", 0)),
        (["E", "S", "W"], "forward", ("Weiche_horizontal_oben_links.svg", 180)),
        (["E", "S", "W"], "reverse", ("Weiche_horizontal_unten_links.svg", 0)),
        (["N", "E", "S"], "forward", ("Weiche_horizontal_oben_links.svg", 90)),
        (["N", "E", "S"], "reverse", ("Weiche_horizontal_oben_rechts.svg", 90)),
        (["N", "S", "W"], "forward", ("Weiche_horizontal_oben_rechts.svg", 270)),
        (["N", "S", "W"], "reverse", ("Weiche_vertikal_unten_links.svg", 0)),
    ]

    for connections, switch_facing, expected in cases:
        cell = {
            "kind": "switch",
            "connections": connections,
            "metadata": {"switchFacing": switch_facing},
        }

        assert resolve_tile(_transition_value(_tokens_for_cell(cell))) == expected


def test_session_api_uses_payload_infrastructure_scene_instead_of_random_generation():
    import pytest

    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.post("/session", json={
        "width": 30,
        "height": 30,
        "number_of_agents": 3,
        "seed": 42,
        "max_num_cities": 2,
        "infrastructure_scene": _straight_scene(),
    })

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["infrastructure_scene_id"] == "probe_scene"
    assert payload["width"] == 8
    assert payload["height"] == 5
    assert payload["num_agents"] == 1

    state_response = client.get(f"/session/{payload['id']}/state")
    assert state_response.status_code == 200, state_response.text
    state = state_response.json()
    assert state["infrastructure_scene_id"] == "probe_scene"
    assert state["infrastructure_scene_diagnostics"]["rail_cell_count"] == 6
    assert state["infrastructure_scene_diagnostics"]["routable_agent_count"] == 1