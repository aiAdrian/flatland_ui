from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app


pytestmark = pytest.mark.integration


def _new_session(client: TestClient) -> str:
    resp = client.post(
        "/session",
        json={
            "width": 50,
            "height": 20,
            "number_of_agents": 3,
        },
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    sid = data.get("id") or data.get("session_id")
    assert sid, data
    return sid


def _scenario_points(scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []

    for scenario in scenarios:
        trajectories = scenario.get("trajectories") or {}
        assert isinstance(trajectories, dict)

        for handle, traj in trajectories.items():
            assert isinstance(handle, str)
            assert isinstance(traj, list)

            for point in traj:
                assert isinstance(point, dict)
                points.append(point)

    return points


def _marey_forecast_points(marey: dict[str, Any]) -> list[dict[str, Any]]:
    agents = marey.get("agents") or {}
    assert isinstance(agents, dict)

    points: list[dict[str, Any]] = []
    for _handle, agent in agents.items():
        assert isinstance(agent, dict)
        forecast = agent.get("forecast") or []
        assert isinstance(forecast, list)
        for point in forecast:
            assert isinstance(point, dict)
            points.append(point)

    return points


def _assert_enriched_points(points: list[dict[str, Any]]) -> None:
    assert points, "expected at least one trajectory/forecast point"

    required_keys = {
        "step",
        "row",
        "col",
        "dir",
        "handle",
        "agent_id",
        "marey_topology",
        "marey_svg",
        "marey_debug",
        "marey_switch",
        "marey_merge",
    }

    missing = [
        {k for k in required_keys if k not in p}
        for p in points
        if any(k not in p for k in required_keys)
    ]
    assert not missing, f"points with missing keys: {missing[:5]}"

    null_svg = [p for p in points if p.get("marey_svg") is None]
    null_topology = [p for p in points if p.get("marey_topology") is None]
    null_debug = [p for p in points if p.get("marey_debug") is None]

    assert not null_svg, f"points without marey_svg: {null_svg[:5]}"
    assert not null_topology, f"points without marey_topology: {null_topology[:5]}"
    assert not null_debug, f"points without marey_debug: {null_debug[:5]}"

    allowed_topologies = {
        "straight",
        "switch",
        "merge",
        "switch_merge",
        "diamond",
        "unknown",
    }
    bad_topologies = [
        p.get("marey_topology")
        for p in points
        if p.get("marey_topology") not in allowed_topologies
    ]
    assert not bad_topologies, f"unexpected topology values: {bad_topologies[:20]}"

    for point in points[:20]:
        debug = point["marey_debug"]
        assert isinstance(debug, dict)
        assert "classification_reason" in debug
        assert "possible_out_dirs" in debug
        assert "possible_transitions" in debug
        assert "backward_transitions" in debug
        assert "possible_in_dirs_for_out" in debug


def test_hmi_scenarios_trajectory_points_are_marey_enriched():
    client = TestClient(app)
    sid = _new_session(client)

    resp = client.get(f"/session/{sid}/hmi/scenarios")
    assert resp.status_code == 200, resp.text

    scenarios = resp.json()
    assert isinstance(scenarios, list)
    assert scenarios, "expected at least one scenario"

    points = _scenario_points(scenarios)
    _assert_enriched_points(points)


def test_hmi_marey_data_forecast_still_matches_enrichment_contract():
    client = TestClient(app)
    sid = _new_session(client)

    # Populate scenario cache first; /hmi/marey-data intentionally reuses it.
    scenarios_resp = client.get(f"/session/{sid}/hmi/scenarios")
    assert scenarios_resp.status_code == 200, scenarios_resp.text

    marey_resp = client.get(f"/session/{sid}/hmi/marey-data")
    assert marey_resp.status_code == 200, marey_resp.text

    marey = marey_resp.json()
    assert isinstance(marey, dict)
    assert marey.get("cached") is True

    points = _marey_forecast_points(marey)
    _assert_enriched_points(points)
