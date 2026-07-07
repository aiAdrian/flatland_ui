"""Convert Infrastructure Builder scenes into Flatland rail generators."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from flatland.envs.grid.rail_env_grid import RailEnvTransitions
from flatland.envs.rail_generators import rail_from_grid_transition_map
from flatland.envs.rail_grid_transition_map import RailGridTransitionMap
from flatland.envs.rail_trainrun_data_structures import Waypoint
from flatland.envs.timetable_utils import Line

from app.core.tile_resolver import build_rail_tiles


_DIR_INDEX = {"N": 0, "E": 1, "S": 2, "W": 3}
_OPPOSITE = {"N": "S", "E": "W", "S": "N", "W": "E"}


def _cell_id(x: int, y: int) -> str:
    return f"cell_{x}_{y}"


def _transition_value(tokens: Iterable[tuple[str, str]]) -> int:
    bits = ["0"] * 16
    for in_dir, out_dir in tokens:
        bits[4 * _DIR_INDEX[in_dir] + _DIR_INDEX[out_dir]] = "1"
    return int("".join(bits), 2)


def _tokens_for_pair(first: str, second: str) -> list[tuple[str, str]]:
    if {first, second} == {"E", "W"}:
        return [("E", "E"), ("W", "W")]
    if {first, second} == {"N", "S"}:
        return [("N", "N"), ("S", "S")]
    return [(_OPPOSITE[first], second), (_OPPOSITE[second], first)]


def _tokens_for_connections(connections: list[str]) -> list[tuple[str, str]]:
    unique = [direction for direction in ["N", "E", "S", "W"] if direction in set(connections)]
    if len(unique) < 2:
        return [(_OPPOSITE[unique[0]], unique[0])] if unique else []
    if len(unique) == 4:
        return [("N", "N"), ("E", "E"), ("S", "S"), ("W", "W")]

    tokens: list[tuple[str, str]] = []
    for index, first in enumerate(unique):
        for second in unique[index + 1:]:
            tokens.extend(_tokens_for_pair(first, second))
    return tokens


def _tokens_for_switch_connections(cell: dict[str, Any]) -> list[tuple[str, str]]:
    unique = tuple(direction for direction in ["N", "E", "S", "W"] if direction in set(cell.get("connections", [])))
    reverse = cell.get("metadata", {}).get("switchFacing") == "reverse"
    switch_tokens: dict[tuple[str, ...], tuple[list[tuple[str, str]], list[tuple[str, str]]]] = {
        ("N", "E", "W"): (
            [("E", "E"), ("W", "W"), ("S", "E"), ("W", "N")],
            [("E", "E"), ("W", "W"), ("E", "N"), ("S", "W")],
        ),
        ("E", "S", "W"): (
            [("E", "E"), ("W", "W"), ("N", "E"), ("W", "S")],
            [("E", "E"), ("W", "W"), ("E", "S"), ("N", "W")],
        ),
        ("N", "E", "S"): (
            [("N", "N"), ("S", "S"), ("S", "E"), ("W", "N")],
            [("N", "N"), ("S", "S"), ("N", "E"), ("W", "S")],
        ),
        ("N", "S", "W"): (
            [("N", "N"), ("S", "S"), ("E", "N"), ("S", "W")],
            [("N", "N"), ("S", "S"), ("N", "W"), ("E", "S")],
        ),
    }
    variants = switch_tokens.get(unique)
    if variants is None:
        return _tokens_for_connections(list(unique))
    return variants[1] if reverse else variants[0]


def _tokens_for_cell(cell: dict[str, Any]) -> list[tuple[str, str]]:
    if cell.get("kind") == "switch":
        return _tokens_for_switch_connections(cell)
    return _tokens_for_connections(list(cell.get("connections", [])))


def _position_from_agent(agent: dict[str, Any], key: str, fallback_cell_id: str | None) -> tuple[int, int] | None:
    position = agent.get(key)
    if isinstance(position, dict) and "x" in position and "y" in position:
        return int(position["y"]), int(position["x"])

    if fallback_cell_id and fallback_cell_id.startswith("cell_"):
        try:
            _, x_raw, y_raw = fallback_cell_id.split("_", 2)
            return int(y_raw), int(x_raw)
        except ValueError:
            return None
    return None


def _direction_from_start_target(start: tuple[int, int], target: tuple[int, int], start_cell: dict[str, Any] | None) -> int:
    connections = start_cell.get("connections", []) if start_cell else []
    unique_connections = [direction for direction in ["N", "E", "S", "W"] if direction in set(connections)]
    if len(unique_connections) == 1:
        return _DIR_INDEX[_OPPOSITE[unique_connections[0]]]

    if target[1] > start[1]:
        return _DIR_INDEX["E"]
    if target[1] < start[1]:
        return _DIR_INDEX["W"]
    if target[0] > start[0]:
        return _DIR_INDEX["S"]
    if target[0] < start[0]:
        return _DIR_INDEX["N"]

    for direction in ["E", "S", "W", "N"]:
        if direction in connections:
            return _DIR_INDEX[direction]
    return _DIR_INDEX["E"]


def _routable_agents(scene: dict[str, Any]) -> list[tuple[dict[str, Any], tuple[int, int], tuple[int, int]]]:
    agents = [agent for agent in scene.get("agents", []) if isinstance(agent, dict)]
    routable = []
    for agent in agents:
        start = _position_from_agent(agent, "start", agent.get("startCellId"))
        target = _position_from_agent(agent, "target", agent.get("targetCellId"))
        if start is None or target is None:
            continue
        routable.append((agent, start, target))
    return routable


def count_routable_agents(scene: dict[str, Any]) -> int:
    return len(_routable_agents(scene))


def build_scene_diagnostics(scene: dict[str, Any] | None, env) -> dict[str, Any] | None:
    if not isinstance(scene, dict):
        return None

    cells = [cell for cell in scene.get("cells", []) if isinstance(cell, dict)]
    rail_grid = [[int(env.rail.grid[row, col]) for col in range(env.width)] for row in range(env.height)]
    rail_tiles = build_rail_tiles(rail_grid)
    tile_by_position = {(tile.get("r"), tile.get("c")): tile for tile in rail_tiles}
    switch_tiles = [tile for tile in rail_tiles if str(tile.get("svg", "")).startswith("Weiche_")]
    unknown_tiles = [tile for tile in rail_tiles if tile.get("unknown") is not None]
    mismatched_cells = []
    switch_cell_tiles = []

    for cell in cells:
        x = int(cell.get("x", -1))
        y = int(cell.get("y", -1))
        if x < 0 or y < 0 or x >= env.width or y >= env.height:
            mismatched_cells.append({
                "id": cell.get("id"),
                "x": x,
                "y": y,
                "kind": cell.get("kind"),
                "reason": "outside_env_grid",
            })
            continue

        expected = int(_transition_value(_tokens_for_cell(cell)))
        actual = int(env.rail.grid[y, x])
        if cell.get("kind") == "switch":
            tile = tile_by_position.get((y, x), {})
            svg = str(tile.get("svg", ""))
            if svg.startswith("Weiche_"):
                visual_kind = "switch"
            elif svg == "Gleis_Diamond_Crossing.svg":
                visual_kind = "crossing"
            else:
                visual_kind = "track"
            switch_cell_tiles.append({
                "id": cell.get("id"),
                "x": x,
                "y": y,
                "connections": list(cell.get("connections", [])),
                "switchFacing": cell.get("metadata", {}).get("switchFacing"),
                "svg": tile.get("svg"),
                "rot": tile.get("rot"),
                "visual_kind": visual_kind,
            })
        if expected != actual:
            mismatched_cells.append({
                "id": cell.get("id"),
                "x": x,
                "y": y,
                "kind": cell.get("kind"),
                "connections": list(cell.get("connections", [])),
                "expected": expected,
                "actual": actual,
            })

    return {
        "scene_cell_count": len(cells),
        "scene_switch_count": sum(1 for cell in cells if cell.get("kind") == "switch"),
        "scene_agent_count": len([agent for agent in scene.get("agents", []) if isinstance(agent, dict)]),
        "routable_agent_count": count_routable_agents(scene),
        "rail_cell_count": sum(1 for row in rail_grid for value in row if value != 0),
        "rail_tile_count": len(rail_tiles),
        "rail_switch_tile_count": len(switch_tiles),
        "switch_cell_tiles": switch_cell_tiles,
        "switch_cell_visual_counts": {
            "switch": sum(1 for tile in switch_cell_tiles if tile.get("visual_kind") == "switch"),
            "crossing": sum(1 for tile in switch_cell_tiles if tile.get("visual_kind") == "crossing"),
            "track": sum(1 for tile in switch_cell_tiles if tile.get("visual_kind") == "track"),
        },
        "unknown_tile_count": len(unknown_tiles),
        "unknown_tiles": unknown_tiles[:10],
        "mismatched_cell_count": len(mismatched_cells),
        "mismatched_cells": mismatched_cells[:20],
    }


@dataclass
class SceneLineGen:
    scene: dict[str, Any]

    def __call__(self, rail, num_agents: int, hints: dict | None = None, num_resets: int = 0, np_random=None) -> Line:
        return self.generate(rail, num_agents, hints, num_resets, np_random)

    def generate(self, rail, num_agents: int, hints: dict | None = None, num_resets: int = 0, np_random=None) -> Line:
        cells = {cell.get("id"): cell for cell in self.scene.get("cells", []) if isinstance(cell, dict)}
        waypoints: dict[int, list[list[Waypoint]]] = {}
        speeds: list[float] = []

        for handle, (agent, start, target) in enumerate(_routable_agents(self.scene)[:num_agents]):
            start_cell = cells.get(agent.get("startCellId"))
            direction = _direction_from_start_target(start, target, start_cell)
            waypoints[handle] = [
                [Waypoint(start, direction)],
                [Waypoint(target, None)],
            ]
            speeds.append(float(agent.get("speed") or 1.0))

        if not waypoints:
            return Line(agent_waypoints={}, agent_speeds=[])

        return Line(agent_waypoints=waypoints, agent_speeds=speeds)


def scene_to_rail_generator(scene: dict[str, Any]):
    grid = scene.get("grid") or {}
    width = int(grid.get("width") or 0)
    height = int(grid.get("height") or 0)
    if width < 1 or height < 1:
        raise ValueError("Infrastructure scene grid must define positive width and height.")

    rail_map = RailGridTransitionMap(width=width, height=height, transitions=RailEnvTransitions())
    for cell in scene.get("cells", []):
        if not isinstance(cell, dict):
            continue
        x = int(cell.get("x", -1))
        y = int(cell.get("y", -1))
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        value = _transition_value(_tokens_for_cell(cell))
        if value:
            rail_map.set_transitions((y, x), value)

    return rail_from_grid_transition_map(rail_map, optionals={"infrastructure_scene_id": scene.get("id")})


def scene_to_line_generator(scene: dict[str, Any]) -> SceneLineGen:
    return SceneLineGen(scene)