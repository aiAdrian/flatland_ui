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
_STRESS = Path(__file__).resolve().parent.parent / "fixtures" / "stress"


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
    # Hard *and* provably solvable, which is why it is shipped as a preset
    # rather than a seed: procedural generation is not reproducible
    # (`env_factory` leaves `RailEnv(random_seed=...)` unset), so the only way
    # to hand the same hard instance to two people is to persist the env.
    #
    # Two cities, seven trains, one bottleneck and a 49-step horizon. Measured
    # on this exact file:
    #   deadlock_avoidance (the UI default)  0/7 arrive
    #   shortest_path                        4/7 arrive
    #   Director planner (balanced dials)    7/7 arrive, 0 delay, 9/9
    #                                        connections kept, 40 steps
    # Static safety of that winning plan is 0.11 — it works, with almost no
    # room to absorb anything. Reproduce with
    # `build_demo_env(seed=9, width=30, height=30, number_of_agents=7,
    #                 max_num_cities=2, line_length=4)`.
    "stress-bottleneck-30x30-7t": {
        "id": "stress-bottleneck-30x30-7t",
        "name": "Stress — Bottleneck (30×30, 7 trains)",
        "path": _STRESS / "stress_bottleneck_30x30_7t.pkl",
        "width": 30,
        "height": 30,
        "agents": 7,
        "source": "generated: build_demo_env seed 9, 2 cities, line_length 4",
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
