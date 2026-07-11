"""Prebuilt scenario presets (e.g. ECML 2026 challenge scenes).

A preset is a finished Flatland scenario shipped as a pickled env
(`RailEnvPersister.save` format). Loading one reproduces the challenge instance
exactly — network, traffic, train goals, intermediate stops, timetable and
malfunctions — because the whole env state is persisted. Presets are therefore
**non-editable by design**: any edit would break comparability with the source
challenge.

This is the "Preset / bundle" config family from
`docs/plans/ecml2026-flatland-env.md`, kept separate from the procedural
generator and the Infrastructure-Builder scene path in `env_factory`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "ecml2026"


# id -> metadata. `path` points at the pickled env; the width/height/agents are
# the loaded env's dimensions (shown in the UI picker before loading).
_PRESETS: dict[str, dict[str, Any]] = {
    "ecml2026-scene1-level0": {
        "id": "ecml2026-scene1-level0",
        "name": "ECML 2026 — Scene 1 (Level 0)",
        "path": _FIXTURES / "ecml2026_scene1_level0.pkl",
        "width": 150,
        "height": 120,
        "agents": 6,
        "source": "flatland-association/ecml2026-starterkit",
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


def list_presets() -> list[dict[str, Any]]:
    """Public listing for the UI picker (without the filesystem `path`)."""
    return [
        {k: v for k, v in preset.items() if k != "path"}
        for preset in _PRESETS.values()
    ]
