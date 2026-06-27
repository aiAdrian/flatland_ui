from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import hmi_scenario_adapter as adapter


class FakeGrid:
    def __getitem__(self, key):
        # key is expected to be (row, col)
        return 12345


def _fake_env():
    return SimpleNamespace(
        rail=SimpleNamespace(
            grid=FakeGrid(),
        )
    )


def test_extract_trajectories_without_env_keeps_basic_contract():
    snapshots = [
        {
            "step": 7,
            "agents": {
                "2": {"pos": [1, 2], "dir": 1},
            },
        }
    ]

    out = adapter._extract_trajectories(snapshots)

    assert set(out.keys()) == {"2"}
    assert len(out["2"]) == 1

    p = out["2"][0]
    assert p.step == 7
    assert p.row == 1
    assert p.col == 2
    assert p.dir == 1

    # handle/agent_id are useful even without env enrichment.
    assert p.handle == 2
    assert p.agent_id == 2

    # Without env, no topology enrichment is attempted.
    assert p.marey_topology is None
    assert p.marey_svg is None
    assert p.marey_debug is None
    assert p.marey_switch is None
    assert p.marey_merge is None


def test_extract_trajectories_enriches_points_with_marey_metadata(monkeypatch):
    env = _fake_env()

    snapshots = [
        {
            "step": 7,
            "agents": {
                "2": {"pos": [1, 2], "dir": 1},
            },
        },
        {
            "step": 8,
            "agents": {
                "2": {"pos": [1, 3], "dir": 1},
            },
        },
    ]

    calls = []

    def fake_resolve_tile(value):
        assert value == 12345
        return ("Weiche_horizontal_oben_links.svg", 0)

    def fake_classify_marey_point(
        env_arg,
        row,
        col,
        direction,
        *,
        step,
        handle,
        taken_out_dir,
        marey_svg,
    ):
        calls.append(
            {
                "env": env_arg,
                "row": row,
                "col": col,
                "direction": direction,
                "step": step,
                "handle": handle,
                "taken_out_dir": taken_out_dir,
                "marey_svg": marey_svg,
            }
        )
        return {
            "marey_topology": "switch",
            "marey_svg": marey_svg,
            "marey_debug": {
                "pos": [row, col],
                "dir": direction,
                "step": step,
                "handle": handle,
                "classification_reason": "unit-test",
                "possible_out_dirs": [1, 2],
                "possible_transitions": [],
                "backward_transitions": {},
                "possible_in_dirs_for_out": {},
                "transition_bits": 12345,
            },
            "marey_switch": {
                "taken": taken_out_dir,
                "not_taken": [2],
                "possible_exits": [1, 2],
            },
            "marey_merge": None,
        }

    monkeypatch.setattr(adapter, "resolve_tile", fake_resolve_tile)
    monkeypatch.setattr(adapter, "classify_marey_point", fake_classify_marey_point)

    out = adapter._extract_trajectories(snapshots, env=env)

    assert set(out.keys()) == {"2"}
    assert len(out["2"]) == 2

    first = out["2"][0]
    assert first.step == 7
    assert first.row == 1
    assert first.col == 2
    assert first.dir == 1
    assert first.handle == 2
    assert first.agent_id == 2
    assert first.marey_topology == "switch"
    assert first.marey_svg == "Weiche_horizontal_oben_links.svg"
    assert first.marey_debug is not None
    assert first.marey_debug["classification_reason"] == "unit-test"
    assert first.marey_switch is not None
    assert first.marey_switch["taken"] == 1
    assert first.marey_merge is None

    # First point moves from (1,2) to (1,3), therefore taken outgoing dir is East=1.
    assert calls[0]["taken_out_dir"] == 1

    # Last point has no next point, therefore no reliable taken_out_dir.
    assert calls[1]["taken_out_dir"] is None


def test_extract_trajectories_uses_unknown_fallback_when_enrichment_fails(monkeypatch):
    env = _fake_env()

    snapshots = [
        {
            "step": 7,
            "agents": {
                "2": {"pos": [1, 2], "dir": 1},
            },
        }
    ]

    monkeypatch.setattr(
        adapter,
        "resolve_tile",
        lambda value: ("Weiche_horizontal_oben_links.svg", 0),
    )

    def raising_classifier(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(adapter, "classify_marey_point", raising_classifier)

    out = adapter._extract_trajectories(snapshots, env=env)
    p = out["2"][0]

    assert p.step == 7
    assert p.row == 1
    assert p.col == 2
    assert p.dir == 1
    assert p.handle == 2
    assert p.agent_id == 2

    assert p.marey_topology == "unknown"
    assert p.marey_svg == "Weiche_horizontal_oben_links.svg"
    assert p.marey_debug is not None
    assert "topology enrichment failed: RuntimeError: boom" in p.marey_debug["classification_reason"]
    assert p.marey_switch is None
    assert p.marey_merge is None


def test_extract_trajectories_skips_off_map_or_invalid_points():
    snapshots = [
        {
            "step": 1,
            "agents": {
                "0": {"pos": None, "dir": 1},
                "1": {"pos": [1, 2], "dir": None},
                "2": {"pos": ["x", 2], "dir": 1},
                "3": {"pos": [3, 4], "dir": 2},
            },
        }
    ]

    out = adapter._extract_trajectories(snapshots)

    assert set(out.keys()) == {"3"}
    p = out["3"][0]
    assert p.step == 1
    assert p.row == 3
    assert p.col == 4
    assert p.dir == 2
