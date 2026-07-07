"""Convert Infrastructure Builder scenes into Flatland rail generators."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from flatland.envs.grid.rail_env_grid import RailEnvTransitions
from flatland.envs.rail_generators import rail_from_grid_transition_map
from flatland.envs.rail_grid_transition_map import RailGridTransitionMap
from flatland.envs.rail_trainrun_data_structures import Waypoint
from flatland.envs.timetable_utils import Line


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
    if target[1] > start[1]:
        return _DIR_INDEX["E"]
    if target[1] < start[1]:
        return _DIR_INDEX["W"]
    if target[0] > start[0]:
        return _DIR_INDEX["S"]
    if target[0] < start[0]:
        return _DIR_INDEX["N"]

    connections = start_cell.get("connections", []) if start_cell else []
    for direction in ["E", "S", "W", "N"]:
        if direction in connections:
            return _DIR_INDEX[direction]
    return _DIR_INDEX["E"]


@dataclass
class SceneLineGen:
    scene: dict[str, Any]

    def __call__(self, rail, num_agents: int, hints: dict | None = None, num_resets: int = 0, np_random=None) -> Line:
        return self.generate(rail, num_agents, hints, num_resets, np_random)

    def generate(self, rail, num_agents: int, hints: dict | None = None, num_resets: int = 0, np_random=None) -> Line:
        cells = {cell.get("id"): cell for cell in self.scene.get("cells", []) if isinstance(cell, dict)}
        waypoints: dict[int, list[list[Waypoint]]] = {}
        speeds: list[float] = []
        agents = [agent for agent in self.scene.get("agents", []) if isinstance(agent, dict)]

        for handle, agent in enumerate(agents[:num_agents]):
            start = _position_from_agent(agent, "start", agent.get("startCellId"))
            target = _position_from_agent(agent, "target", agent.get("targetCellId"))
            if start is None or target is None:
                continue

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
        value = _transition_value(_tokens_for_connections(list(cell.get("connections", []))))
        if value:
            rail_map.set_transitions((y, x), value)

    return rail_from_grid_transition_map(rail_map, optionals={"infrastructure_scene_id": scene.get("id")})


def scene_to_line_generator(scene: dict[str, Any]) -> SceneLineGen:
    return SceneLineGen(scene)