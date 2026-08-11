"""Reduced infrastructure graph containing only decision points.

Takes the setup a policy faces when solving a run in the UI — a Flatland
``RailEnv`` (as handed to ``Policy.reset(env)``) — and compresses its rail
grid into a graph with two node kinds:

- **station**: a cell where a train can stop for traffic reasons. Derived
  from the trains' origins and targets, mirroring the frontend station
  registry (SessionStore.stations()).
- **switch_decision**: the wait cells in front of a switch. A simple switch
  funnels two tracks into a third; a train coming along one of the two
  funneled tracks can stop on the tile *before* the switch and let a train
  using the other branch pass. Each switch therefore contributes one
  decision cell per funneled (trailing) approach — two for a simple switch.

Edges connect nodes a train can reach by driving normally along the track
without passing any other node *relevant for its direction of travel*.
Switch wait cells are directional — they point at their switch and only
concern trains heading into it; a train rolling over one in any other
direction (e.g. leaving the switch over the far branch) passes it without a
decision, so walks skip it. Station stops are relevant in every direction.
Edges are directed and carry the full cell path plus entry/exit headings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from flatland.envs.rail_env import RailEnv

Cell = Tuple[int, int]

# Flatland convention: 0=North, 1=East, 2=South, 3=West.
DIRECTIONS = (0, 1, 2, 3)
DIR_NAMES: Dict[int, str] = {0: "north", 1: "east", 2: "south", 3: "west"}
DIR_TO_DELTA: Dict[int, Cell] = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}
OPPOSITE: Dict[int, int] = {0: 2, 1: 3, 2: 0, 3: 1}
LEFT_OF: Dict[int, int] = {0: 3, 1: 0, 2: 1, 3: 2}
RIGHT_OF: Dict[int, int] = {0: 1, 1: 2, 2: 3, 3: 0}


def move_direction(from_cell: Cell, to_cell: Cell) -> int:
    """Absolute direction of the move between two adjacent cells."""
    delta = (to_cell[0] - from_cell[0], to_cell[1] - from_cell[1])
    for direction, offset in DIR_TO_DELTA.items():
        if offset == delta:
            return direction
    raise ValueError(f"{from_cell} and {to_cell} are not grid neighbours")


def action_for_move(heading: int, move: int) -> int:
    """Flatland action turning a train with `heading` onto absolute `move`.

    Returns a `RailEnvActions` value. A reversal is only possible on a dead
    end, where Flatland's MOVE_FORWARD follows the track back out.
    """
    from flatland.envs.rail_env_action import RailEnvActions

    if move == heading:
        return RailEnvActions.MOVE_FORWARD.value
    if move == LEFT_OF[heading]:
        return RailEnvActions.MOVE_LEFT.value
    if move == RIGHT_OF[heading]:
        return RailEnvActions.MOVE_RIGHT.value
    return RailEnvActions.MOVE_FORWARD.value


def _get_transitions(env: RailEnv, cell: Cell, heading: int) -> Tuple[int, ...]:
    """Outgoing-direction bits for a train on `cell` with `heading`."""
    r, c = int(cell[0]), int(cell[1])
    try:
        transitions = env.rail.get_transitions(((r, c), int(heading)))
    except TypeError:
        # Older Flatland signature.
        transitions = env.rail.get_transitions(r, c, int(heading))
    return tuple(int(bool(transitions[d])) for d in DIRECTIONS)


def _in_bounds(env: RailEnv, cell: Cell) -> bool:
    return 0 <= cell[0] < env.height and 0 <= cell[1] < env.width


def _has_rail(env: RailEnv, cell: Cell) -> bool:
    return _in_bounds(env, cell) and int(env.rail.grid[cell[0], cell[1]]) != 0


def _neighbor(cell: Cell, direction: int) -> Cell:
    dr, dc = DIR_TO_DELTA[direction]
    return (cell[0] + dr, cell[1] + dc)


@dataclass(frozen=True)
class SwitchApproach:
    """One funneled approach of a switch, seen from its wait cell.

    `heading` is the direction of the move from the wait cell into
    `switch_cell` (wait cell + delta(heading) == switch cell). Note this is
    the train's heading *when entering the switch* — on a curved wait cell
    its orientation while waiting differs.
    """
    switch_cell: Cell
    heading: int


@dataclass
class GraphNode:
    cell: Cell
    node_id: int = -1  # stable index, assigned by sorted cell order
    kinds: Set[str] = field(default_factory=set)  # subset of {"station", "switch_decision"}
    station_index: Optional[int] = None  # index into DecisionPointGraph.stations
    station_id: Optional[str] = None
    station_name: Optional[str] = None
    approaches: List[SwitchApproach] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "cell": list(self.cell),
            "kinds": sorted(self.kinds),
            "station_index": self.station_index,
            "station_id": self.station_id,
            "station_name": self.station_name,
            "approaches": [
                {"switch_cell": list(a.switch_cell), "heading": a.heading}
                for a in self.approaches
            ],
        }


@dataclass(frozen=True)
class GraphEdge:
    """A plain track run between two nodes, with no node in between.

    `path` lists every cell from `from_cell` to `to_cell` inclusive.
    `out_direction` is the heading when leaving the first cell,
    `in_direction` the heading when arriving on the last cell.
    """
    from_cell: Cell
    to_cell: Cell
    out_direction: int
    in_direction: int
    path: Tuple[Cell, ...]

    @property
    def length(self) -> int:
        """Number of cell-to-cell moves from `from_cell` to `to_cell`."""
        return len(self.path) - 1

    @property
    def travel_time(self) -> int:
        """Time steps to traverse the edge at one tile per step.

        A train standing on `from_cell` needs this many steps until it
        stands on `to_cell`, i.e. one step per move along `path`. Trains
        slower than one tile per step take `ceil(travel_time / speed)`;
        that scaling is left to the caller since speed is per agent, not
        a property of the infrastructure.
        """
        return self.length

    @property
    def moves(self) -> Tuple[int, ...]:
        """Absolute direction of each step along the edge (0=N, 1=E, 2=S, 3=W).

        One entry per time step, so `len(moves) == travel_time`, starting
        with `out_direction` and ending with `in_direction`.
        """
        return tuple(
            move_direction(a, b) for a, b in zip(self.path, self.path[1:])
        )

    def actions(self, entry_heading: int) -> Tuple[int, ...]:
        """Flatland actions to drive this edge, for a train oriented
        `entry_heading` while standing on `from_cell`.

        Only the first action depends on that orientation — after a move the
        train's heading is the move direction itself.
        """
        heading = int(entry_heading)
        out = []
        for move in self.moves:
            out.append(action_for_move(heading, move))
            heading = move
        return tuple(out)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": list(self.from_cell),
            "to": list(self.to_cell),
            "out_direction": self.out_direction,
            "in_direction": self.in_direction,
            "length": self.length,
            "travel_time": self.travel_time,
            "moves": list(self.moves),
            "move_names": [DIR_NAMES[m] for m in self.moves],
            "actions": list(self.actions(self.out_direction)),
            "path": [list(c) for c in self.path],
        }


def find_switch_cells(env: RailEnv) -> Dict[Cell, List[int]]:
    """All switch cells, mapped to the facing headings (>1 exit)."""
    switches: Dict[Cell, List[int]] = {}
    for r in range(env.height):
        for c in range(env.width):
            if int(env.rail.grid[r, c]) == 0:
                continue
            facing = [
                h for h in DIRECTIONS
                if sum(_get_transitions(env, (r, c), h)) > 1
            ]
            if facing:
                switches[(r, c)] = facing
    return switches


def find_switch_decision_cells(
    env: RailEnv,
    switches: Optional[Dict[Cell, List[int]]] = None,
) -> Dict[Cell, List[SwitchApproach]]:
    """The wait cells in front of each switch.

    For a switch S, an in-heading h is a funneled (trailing) approach when it
    has exactly one exit and shares that exit with another in-heading — the
    two tracks merged into one. The decision cell is the tile the train came
    from: the neighbour of S opposite to h. Diamond crossings (one exit per
    heading, nothing shared) contribute no decision cells.
    """
    if switches is None:
        switches = find_switch_cells(env)

    decision_cells: Dict[Cell, List[SwitchApproach]] = {}
    for switch_cell in switches:
        exits_by_heading = {
            h: _get_transitions(env, switch_cell, h) for h in DIRECTIONS
        }
        for h in DIRECTIONS:
            exits = exits_by_heading[h]
            if sum(exits) != 1:
                continue
            exit_dir = exits.index(1)
            merges = any(
                h2 != h and exits_by_heading[h2][exit_dir]
                for h2 in DIRECTIONS
            )
            if not merges:
                continue
            wait_cell = _neighbor(switch_cell, OPPOSITE[h])
            if not _has_rail(env, wait_cell):
                continue
            # The wait cell must actually feed into the switch with heading h.
            feeds_switch = any(
                _get_transitions(env, wait_cell, hp)[h] for hp in DIRECTIONS
            )
            if not feeds_switch:
                continue
            decision_cells.setdefault(wait_cell, []).append(
                SwitchApproach(switch_cell=switch_cell, heading=h)
            )
    return decision_cells


def station_cells_from_env(env: RailEnv) -> List[Cell]:
    """Station stops: each train's origin and target, deduped in agent order.

    Mirrors the frontend station registry (SessionStore.stations()), which
    labels these cells S1, S2, … on the map.
    """
    stations: List[Cell] = []
    seen: Set[Cell] = set()
    for agent in env.agents:
        for pos in (agent.initial_position, agent.target):
            if pos is None:
                continue
            cell = (int(pos[0]), int(pos[1]))
            if cell not in seen and _has_rail(env, cell):
                seen.add(cell)
                stations.append(cell)
    return stations


def _walk_edges_from(
    env: RailEnv,
    start: Cell,
    first_exit: int,
    node_headings: Dict[Cell, Optional[frozenset]],
) -> List[GraphEdge]:
    """Follow the track from `start` leaving in `first_exit` until nodes.

    Decision points are directional: a switch wait cell only ends the walk
    when it is reached with one of its approach headings (pointing at its
    switch). In any other direction the walk passes straight over it —
    e.g. a train leaving a switch rolls over the far branch's wait cell
    without that being a decision for it. Station stops end the walk in
    every direction (`node_headings[cell] is None`).

    Branches at facing switches (which are not nodes themselves); each branch
    ends at the first relevant node it reaches. A per-walk visited set guards
    against loops on node-free cycles.
    """
    edges: List[GraphEdge] = []
    first_cell = _neighbor(start, first_exit)
    if not _has_rail(env, first_cell):
        return edges

    max_hops = env.height * env.width * 4
    stack: List[Tuple[Cell, int, Tuple[Cell, ...]]] = [
        (first_cell, first_exit, (start, first_cell))
    ]
    visited: Set[Tuple[Cell, int]] = {(first_cell, first_exit)}

    while stack:
        cell, heading, path = stack.pop()
        stop_headings = node_headings.get(cell)
        if cell in node_headings and (
            stop_headings is None or heading in stop_headings
        ):
            edges.append(GraphEdge(
                from_cell=start,
                to_cell=cell,
                out_direction=first_exit,
                in_direction=heading,
                path=path,
            ))
            continue
        if len(path) > max_hops:
            continue
        exits = _get_transitions(env, cell, heading)
        for exit_dir in DIRECTIONS:
            if not exits[exit_dir]:
                continue
            nxt = _neighbor(cell, exit_dir)
            if not _has_rail(env, nxt):
                continue
            state = (nxt, exit_dir)
            if state in visited:
                continue
            visited.add(state)
            stack.append((nxt, exit_dir, path + (nxt,)))
    return edges


@dataclass
class DecisionPointGraph:
    nodes: Dict[Cell, GraphNode]
    edges: List[GraphEdge]
    switch_cells: Dict[Cell, List[int]]  # kept for visualization/context
    stations: List[Any] = field(default_factory=list)  # List[stations.Station]

    def edges_from(self, cell: Cell) -> List[GraphEdge]:
        """Outgoing edges of a node, indexed for repeated lookups."""
        if not hasattr(self, "_edges_by_source"):
            index: Dict[Cell, List[GraphEdge]] = {}
            for edge in self.edges:
                index.setdefault(edge.from_cell, []).append(edge)
            self._edges_by_source = index
        return self._edges_by_source.get(cell, [])

    def edges_have_alternative_route(self) -> List[bool]:
        """For each edge, whether the train could still get from its source
        node to its target node without using that edge.

        Directed reachability: remove the one edge and BFS from its source
        over the remaining edges. True means the connection survives — a
        parallel track or a detour exists — so a conflict on this edge is
        avoidable by rerouting. False marks an edge that is the only way
        across, where a block has no alternative. Computed on the graph
        alone, no rollout.
        """
        from collections import deque

        adjacency: Dict[Cell, List[Tuple[Cell, int]]] = {}
        for position, edge in enumerate(self.edges):
            adjacency.setdefault(edge.from_cell, []).append((edge.to_cell, position))

        results: List[bool] = []
        for position, edge in enumerate(self.edges):
            # The excluded edge must stay excluded for the whole search, not
            # just the first hop: a path that loops back to the source node
            # could otherwise cross it and falsely count as an alternative.
            seen: Set[Cell] = {edge.from_cell}
            queue: deque = deque([edge.from_cell])
            found = False
            while queue and not found:
                cell = queue.popleft()
                for nxt, edge_id in adjacency.get(cell, ()):
                    if edge_id == position:
                        continue
                    if nxt == edge.to_cell:
                        found = True
                        break
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
            results.append(found)
        return results

    def node_id(self, cell: Cell) -> int:
        return self.nodes[cell].node_id

    def cell_of(self, node_id: int) -> Cell:
        if not hasattr(self, "_cells_by_id"):
            self._cells_by_id = {n.node_id: c for c, n in self.nodes.items()}
        return self._cells_by_id[int(node_id)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [self.nodes[c].to_dict() for c in sorted(self.nodes)],
            "edges": [e.to_dict() for e in self.edges],
            "switch_cells": [list(c) for c in sorted(self.switch_cells)],
            "stations": [
                {
                    "id": s.id,
                    "name": s.name,
                    "stop_cells": [list(c) for c in s.stop_cells],
                    "source": s.source,
                }
                for s in self.stations
            ],
        }

    @classmethod
    def from_env(
        cls,
        env: RailEnv,
        stations: Optional[List[Any]] = None,
        extra_station_cells: Optional[Iterable[Cell]] = None,
        scenario_preset_id: Optional[str] = None,
        infrastructure_scene: Optional[Dict[str, Any]] = None,
    ) -> "DecisionPointGraph":
        # Lazy import: stations.py imports Cell/_has_rail from this module.
        from app.policies.goal_based_policies.stations import resolve_stations

        if stations is None:
            stations = resolve_stations(
                env,
                scenario_preset_id=scenario_preset_id,
                infrastructure_scene=infrastructure_scene,
            )

        switches = find_switch_cells(env)
        decision_cells = find_switch_decision_cells(env, switches)

        nodes: Dict[Cell, GraphNode] = {}
        for index, station in enumerate(stations):
            for cell in station.stop_cells:
                node = nodes.setdefault(cell, GraphNode(cell=cell))
                node.kinds.add("station")
                node.station_index = index
                node.station_id = station.id
                node.station_name = station.name
        for cell in extra_station_cells or ():
            cell = (int(cell[0]), int(cell[1]))
            if _has_rail(env, cell):
                node = nodes.setdefault(cell, GraphNode(cell=cell))
                node.kinds.add("station")
        for cell, approaches in decision_cells.items():
            node = nodes.setdefault(cell, GraphNode(cell=cell))
            node.kinds.add("switch_decision")
            node.approaches = approaches

        # Directional node map: stations stop trains in every direction
        # (None); a pure switch wait cell only in the orientations whose next
        # move leads into one of its switches. The orientation on the cell can
        # differ from the approach heading when the wait cell is a curve.
        node_headings: Dict[Cell, Optional[frozenset]] = {}
        for cell, node in nodes.items():
            if "station" in node.kinds:
                node_headings[cell] = None
                continue
            approach_dirs = {a.heading for a in node.approaches}
            node_headings[cell] = frozenset(
                orientation
                for orientation in DIRECTIONS
                if any(
                    _get_transitions(env, cell, orientation)[h]
                    for h in approach_dirs
                )
            )

        edges: List[GraphEdge] = []
        seen_paths: Set[Tuple[Cell, ...]] = set()
        for cell in nodes:
            headings = node_headings[cell]
            if headings is None:
                headings = frozenset(DIRECTIONS)
            exit_dirs: Set[int] = set()
            for heading in headings:
                transitions = _get_transitions(env, cell, heading)
                exit_dirs.update(d for d in DIRECTIONS if transitions[d])
            for exit_dir in sorted(exit_dirs):
                for edge in _walk_edges_from(env, cell, exit_dir, node_headings):
                    if edge.path not in seen_paths:
                        seen_paths.add(edge.path)
                        edges.append(edge)

        # Ids are a pure function of the cell (row-major over the grid), not
        # of which nodes happen to exist. Station nodes come from the train
        # missions, so a running index would shift every id whenever the
        # train set changes — and a model learning one embedding per node id
        # needs those ids to mean the same thing across scenarios on the
        # same infrastructure.
        for cell in sorted(nodes):
            nodes[cell].node_id = cell[0] * int(env.width) + cell[1]

        return cls(
            nodes=nodes, edges=edges, switch_cells=switches, stations=list(stations)
        )


def build_decision_point_graph(
    env: RailEnv,
    stations: Optional[List[Any]] = None,
    extra_station_cells: Optional[Iterable[Cell]] = None,
    scenario_preset_id: Optional[str] = None,
    infrastructure_scene: Optional[Dict[str, Any]] = None,
) -> DecisionPointGraph:
    """Convenience wrapper matching what a policy sees in `reset(env)`.

    Pass the session's `scenario_preset_id` or `infrastructure_scene` so
    stations come from the real infrastructure metadata (platforms) instead
    of only the train missions — see `stations.resolve_stations`.
    """
    return DecisionPointGraph.from_env(
        env,
        stations=stations,
        extra_station_cells=extra_station_cells,
        scenario_preset_id=scenario_preset_id,
        infrastructure_scene=infrastructure_scene,
    )
