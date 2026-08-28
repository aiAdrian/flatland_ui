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

A preset may also ship two further layers, both optional:

- ``plan`` — a ``*.plan.json`` giving every train's exact route and timing
  (``app.core.plans``). Selecting the scenario makes the ``plan`` policy
  available, which drives the trains along it.
- ``disturbances`` — a directory of files describing what goes wrong and when
  (``app.core.disturbances``). The user picks any subset of them at session
  start, so one scenario+plan can be run against several conditions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.disturbances import list_disturbances

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

ENV_PRESET = "env"
SCENE_PRESET = "scene"

# Keys that are implementation detail, not part of the UI payload.
_INTERNAL_FIELDS = {"path", "kind", "session", "plan", "disturbances"}


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
    "pf-ch-corridor-stops": {
        "id": "pf-ch-corridor-stops",
        "name": "PF–CH corridor (with intermediate stops)",
        "kind": SCENE_PRESET,
        "path": _FIXTURES / "pf_ch" / "pf-ch-corridor-stops.scene.json",
        "width": 191,
        "height": 9,
        "agents": 16,
        "source": "Gleisschema of the Pfäffikon SZ–Chur line",
        # The corridor variant whose trains call at stations on the way instead
        # of only at origin and destination. Without intermediate calls a
        # scenario has no train pairs meeting at a station, so
        # `planned_connections` finds nothing and any connection-based measure
        # is flat — see the E1 spec's §8 note on the trade-off axes.
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
        "plan": _FIXTURES / "pf_ch" / "pf-ch-wn-wal-conflict.plan.json",
        "disturbances": _FIXTURES / "pf_ch" / "disturbances",
        # All three services are meant to be on the map from the first step;
        # Flatland's timetable generator would otherwise stagger them over the
        # first few steps and the conflict would not arise as intended.
        # malfunction_rate is pinned because this scenario ships a plan: with
        # random breakdowns left on, the same plan and the same disturbances
        # would still give a different episode every run.
        "session": {
            "latest_departure_max": 0,
            "malfunction_rate": 0.0,
            "max_episode_steps": 140,
        },
    },
    "pf-ch-wn-wal-long-approach": {
        "id": "pf-ch-wn-wal-long-approach",
        "name": "PF–CH · WN↔WAL conflict (long approach)",
        "kind": SCENE_PRESET,
        "path": _FIXTURES / "pf_ch" / "pf-ch-wn-wal-long-approach.scene.json",
        "width": 191,
        "height": 9,
        "agents": 3,
        "source": "Gleisschema of the Pfäffikon SZ–Chur line",
        "plan": _FIXTURES / "pf_ch" / "pf-ch-wn-wal-long-approach.plan.json",
        "disturbances": _FIXTURES / "pf_ch" / "disturbances_long_approach",
        # Same network, trains and targets as the short version; both spawns
        # move one station further out (WN->ZB eastbound, WAL->FMS westbound)
        # so the conflict is visible for longer before it has to be resolved.
        #
        # Its plan is authored, not recorded. Each train is routed
        # individually, because Flatland's shortest path puts all of them on
        # row 0 even where a parallel track exists — which makes the eastbound
        # and westbound runs look like they contend for 26 columns when the
        # single-track section is really only six (cols 96-101). Routed
        # properly and with the departures spaced, all three converge on those
        # six cells within about a dozen steps and pass through in the order
        # 0, 1, 2 without any of them ever stopping.
        #
        # The single disturbance takes exactly the headway train 0 holds over
        # train 1 away again, so the two meet at the section — the one thing a
        # conflict-free plan cannot absorb, and therefore the decision the
        # operator is there to make. Only then does anything wait, and it waits
        # on the approach or at the mouth, never at a platform.
        "session": {
            "latest_departure_max": 0,
            "malfunction_rate": 0.0,
            "max_episode_steps": 180,
        },
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


def preset_plan_path(preset_id: str) -> Path | None:
    """The scenario's plan file, if it ships one and the file is there."""
    path = get_preset(preset_id).get("plan")
    if path is None or not Path(path).is_file():
        return None
    return Path(path)


def preset_disturbances(preset_id: str) -> list[dict[str, Any]]:
    """The scenario's disturbance files, parsed. Empty when it ships none."""
    return list_disturbances(get_preset(preset_id).get("disturbances"))


def select_disturbances(preset_id: str, ids: list[str] | None) -> list[dict[str, Any]]:
    """The requested disturbances, in the scenario's own order.

    An unknown id is an error rather than a silent skip: a study run that
    quietly drops a condition would look like a valid run of that condition.
    """
    if not ids:
        return []
    wanted = set(ids)
    available = preset_disturbances(preset_id)
    unknown = wanted - {d["id"] for d in available}
    if unknown:
        raise KeyError(
            f"Unknown disturbance(s) for {preset_id!r}: {', '.join(sorted(unknown))}"
        )
    return [d for d in available if d["id"] in wanted]


def list_presets() -> list[dict[str, Any]]:
    """Public listing for the UI picker.

    Internal fields are replaced by what the picker actually needs: whether a
    plan exists, and the disturbances offered alongside it.
    """
    listing = []
    for preset in _PRESETS.values():
        entry = {k: v for k, v in preset.items() if k not in _INTERNAL_FIELDS}
        entry["has_plan"] = preset_plan_path(preset["id"]) is not None
        entry["disturbances"] = [
            {"id": d["id"], "name": d["name"], "description": d["description"]}
            for d in preset_disturbances(preset["id"])
        ]
        listing.append(entry)
    return listing
