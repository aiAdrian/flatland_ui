"""Station extraction with their possible stop cells.

Flatland's rail *grid* carries no station concept — the grouping exists
only in the rail generator's `agents_hints`, which `RailEnv` does not
retain. Four sources, mirroring how envs are created in `env_factory`:

- **ECML presets**: the challenge ships city/platform metadata separately
  (`fixtures/ecml2026/stations.pkl`): per city its platform cells
  (`train_stations` — the possible stops) and which scenes it exists in.
- **Generator hints**: for generated networks, the same structure taken
  live from the env, retained by `StationAwareRailEnv`
  (`app.core.station_aware_env`).
- **Infrastructure-Builder scenes**: the scene dict has an explicit
  `stations` list (id, name, x, y) — one stop cell each. This never reaches
  the env, so it must be read from the scene payload.
- **Train missions** (fallback / supplement): each agent's origin and
  target, the same registry the frontend station layer derives.

`resolve_stations` combines them: the source matching the env plus mission
cells not already covered — trains must be able to stop at their own
origins and targets even when those lie outside a known station.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from flatland.envs.rail_env import RailEnv

from app.core.station_aware_env import station_hints_for
from app.policies.goal_based_policies.infrastructure_graph import (
    Cell,
    _has_rail,
    station_cells_from_env,
)

_ECML_FIXTURE = (
    Path(__file__).resolve().parent.parent.parent
    / "fixtures" / "ecml2026" / "stations.pkl"
)


@dataclass(frozen=True)
class Station:
    """A named station with the cells a train can stop on (platforms)."""
    id: str
    name: str
    stop_cells: Tuple[Cell, ...]
    center: Optional[Cell] = None
    source: str = "missions"  # "missions" | "ecml_fixture" | "scene"


def stations_from_agent_missions(env: RailEnv) -> List[Station]:
    """One single-cell station per distinct origin/target cell.

    Sorted by (row, col) so names line up with the frontend station layer
    (SessionStore.stations), which labels the same cells S1, S2, …
    """
    return [
        Station(
            id=f"mission_{r}_{c}",
            name=f"S{i + 1}",
            stop_cells=((r, c),),
            center=(r, c),
            source="missions",
        )
        for i, (r, c) in enumerate(sorted(station_cells_from_env(env)))
    ]


def _stations_from_cities(
    env: RailEnv,
    city_positions: Sequence[Any],
    train_stations: Sequence[Any],
    source: str,
) -> List[Station]:
    """City/platform groups → Stations: named S1, S2, … by (row, col) of
    the city centre for a stable, readable order; stop cells filtered to
    rail present in this env; cities without any rail stop dropped."""
    cities = list(enumerate(city_positions))
    cities.sort(key=lambda item: (int(item[1][0]), int(item[1][1])))

    stations: List[Station] = []
    for order, (i, center) in enumerate(cities):
        if i >= len(train_stations):
            continue
        stops = tuple(
            (int(cell[0]), int(cell[1]))
            for cell, _platform_idx in train_stations[i]
            if _has_rail(env, (int(cell[0]), int(cell[1])))
        )
        if not stops:
            continue
        stations.append(Station(
            id=f"city_{i}",
            name=f"S{order + 1}",
            stop_cells=stops,
            center=(int(center[0]), int(center[1])),
            source=source,
        ))
    return stations


def stations_from_ecml_fixture(
    env: RailEnv,
    fixture_path: Optional[Path] = None,
) -> List[Station]:
    """Stations for an ECML env from the challenge's stations.pkl.

    Every city whose platform cells lie on rail in the given env is
    included — the physical network is shared across the ECML scenes, so
    all stations exist in the infrastructure.
    """
    path = fixture_path or _ECML_FIXTURE
    with open(path, "rb") as f:
        data = pickle.load(f)
    return _stations_from_cities(
        env, data["city_positions"], data["train_stations"], "ecml_fixture"
    )


def stations_from_generator_hints(env: RailEnv) -> List[Station]:
    """Stations from the rail generator's own city/platform grouping.

    The same structure `stations_from_ecml_fixture` reads out of a pickle,
    but taken live from the env it was generated with — so any generated
    network gets true multi-platform stations instead of one single-cell
    station per train origin/target.

    Returns an empty list for envs not built through
    `StationAwareRailEnv` (see `app.core.station_aware_env`), which is not
    an error: `resolve_stations` then falls through to the other sources.
    """
    hints = station_hints_for(env)
    if not hints:
        return []
    return _stations_from_cities(
        env,
        hints.get("city_positions") or [],
        hints.get("train_stations") or [],
        "generator_hints",
    )


def stations_from_scene(
    scene: Dict[str, Any],
    env: Optional[RailEnv] = None,
) -> List[Station]:
    """Stations from an Infrastructure-Builder scene dict.

    Builder stations are single cells; scene coordinates are (x, y) with
    row = y, col = x (same mapping as infrastructure_scene_adapter).
    """
    stations: List[Station] = []
    for i, station in enumerate(scene.get("stations", []) or []):
        if not isinstance(station, dict):
            continue
        try:
            cell = (int(station["y"]), int(station["x"]))
        except (KeyError, TypeError, ValueError):
            continue
        if env is not None and not _has_rail(env, cell):
            continue
        stations.append(Station(
            id=str(station.get("id") or f"scene_station_{i}"),
            name=str(station.get("name") or f"S{i + 1}"),
            stop_cells=(cell,),
            center=cell,
            source="scene",
        ))
    return stations


def resolve_stations(
    env: RailEnv,
    scenario_preset_id: Optional[str] = None,
    infrastructure_scene: Optional[Dict[str, Any]] = None,
    include_agent_missions: bool = True,
) -> List[Station]:
    """Stations for the env's session context, plus uncovered mission cells.

    Pass the same `scenario_preset_id` / `infrastructure_scene` the session
    was created with (see `env_factory.create_env`). With neither, stations
    are the train missions alone.
    """
    stations: List[Station] = []
    if scenario_preset_id:
        if "ecml" in scenario_preset_id.lower() and _ECML_FIXTURE.exists():
            # All physical stations, not just the scene's scheduled subset.
            stations = stations_from_ecml_fixture(env)
    elif infrastructure_scene:
        stations = stations_from_scene(infrastructure_scene, env)

    if not stations:
        # Generated networks: the rail generator's own grouping, which beats
        # the mission fallback because it keeps a city's platforms together.
        stations = stations_from_generator_hints(env)

    if include_agent_missions or not stations:
        covered = {cell for s in stations for cell in s.stop_cells}
        extra = [
            m for m in stations_from_agent_missions(env)
            if m.stop_cells[0] not in covered
        ]
        # Re-name so labels continue after the named stations.
        offset = len(stations)
        stations = stations + [
            Station(
                id=m.id,
                name=f"S{offset + k + 1}",
                stop_cells=m.stop_cells,
                center=m.center,
                source=m.source,
            )
            for k, m in enumerate(extra)
        ]
    return stations
