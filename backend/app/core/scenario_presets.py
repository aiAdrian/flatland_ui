"""Prebuilt scenarios that ship with the repo.

A preset is an environment committed to the repo and offered in the UI's
Infrastructure picker, so a fresh clone can select it without importing
anything. Two kinds, differing only in what the file holds:

- ``env`` — a pickled Flatland env (``RailEnvPersister.save`` format). Loading
  one reproduces a challenge instance exactly: network, traffic, train goals,
  intermediate stops, timetable and malfunctions. This is the ECML 2026 case
  from ``docs/plans/ecml2026-flatland-env.md``.
- ``scene`` — an Infrastructure-Builder scene (the same JSON the builder
  exports). It goes through the normal scene path in ``env_factory``, so the
  scene dict stays with the session and named stations survive; a pickled env
  would lose them, because ``RailEnvPersister`` does not persist ``stations``.

Presets are **non-editable by design**: selecting one must give every user the
same environment, so nothing here is copied into the builder's local storage.

A preset may pin the session settings that belong to the scenario rather than
to the user's Settings fields (``session`` below) — otherwise a scenario would
silently depend on those fields happening to be right.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

ENV_PRESET = "env"
SCENE_PRESET = "scene"

# Keys that are implementation detail, not part of the UI payload.
_INTERNAL_FIELDS = {"path", "kind", "session"}


# id -> metadata. `path` points at the file; width/height/agents are the loaded
# env's dimensions (shown in the UI picker before loading).
_PRESETS: dict[str, dict[str, Any]] = {
    "ecml2026-scene1-level0": {
        "id": "ecml2026-scene1-level0",
        "name": "ECML 2026 — Scene 1 (Level 0)",
        "kind": ENV_PRESET,
        "path": _FIXTURES / "ecml2026" / "ecml2026_scene1_level0.pkl",
        "width": 150,
        "height": 120,
        "agents": 6,
        "source": "flatland-association/ecml2026-starterkit",
    },
    "pf-ch-corridor": {
        "id": "pf-ch-corridor",
        "name": "PF–CH corridor (double track)",
        "kind": SCENE_PRESET,
        "path": _FIXTURES / "pf_ch" / "pf-ch-corridor.scene.json",
        "width": 191,
        "height": 9,
        "agents": 16,
        "source": "Gleisschema of the Pfäffikon SZ–Chur line",
    },
    "pf-ch-wn-wal-conflict": {
        "id": "pf-ch-wn-wal-conflict",
        "name": "PF–CH · WN↔WAL single-track conflict",
        "kind": SCENE_PRESET,
        "path": _FIXTURES / "pf_ch" / "pf-ch-wn-wal-conflict.scene.json",
        "width": 191,
        "height": 9,
        "agents": 3,
        "source": "Gleisschema of the Pfäffikon SZ–Chur line",
        # All three services are meant to be on the map from the first step;
        # Flatland's timetable generator would otherwise stagger them over the
        # first few steps and the conflict would not arise as intended.
        "session": {"latest_departure_max": 0},
    },
}


def get_preset(preset_id: str) -> dict[str, Any]:
    """Return the preset metadata (incl. `path`), or raise KeyError/FileNotFoundError."""
    preset = _PRESETS.get(preset_id)
    if preset is None:
        raise KeyError(f"Unknown scenario preset: {preset_id!r}")
    path = preset["path"]
    if not Path(path).is_file():
        raise FileNotFoundError(f"Scenario preset file missing: {path}")
    return preset


def preset_kind(preset_id: str) -> str:
    """`ENV_PRESET` for a pickled env, `SCENE_PRESET` for a builder scene."""
    return str(get_preset(preset_id).get("kind", ENV_PRESET))


def load_preset_scene(preset_id: str) -> dict[str, Any] | None:
    """The Infrastructure-Builder scene behind a scene preset, else None."""
    preset = get_preset(preset_id)
    if preset.get("kind") != SCENE_PRESET:
        return None
    return json.loads(Path(preset["path"]).read_text(encoding="utf-8"))


def preset_session_settings(preset_id: str) -> dict[str, Any]:
    """Session settings the scenario pins, e.g. `latest_departure_max`."""
    return dict(get_preset(preset_id).get("session") or {})


def list_presets() -> list[dict[str, Any]]:
    """Public listing for the UI picker (without the internal fields)."""
    return [
        {k: v for k, v in preset.items() if k not in _INTERNAL_FIELDS}
        for preset in _PRESETS.values()
    ]
