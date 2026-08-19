"""Everything about a scenario that never changes while the search runs.

Built once per environment and shared by every node of the tree: the
decision-point graph, each train's line and timetable, and the cost-to-go
tables the option generator needs to tell a branch that still reaches the
next stop from one that strands the train.

On the cost-to-go tables: they are *reachability and distance*, not a plan.
Nothing here completes, extends or scores a schedule — the tables answer
"can this branch still get there, and how far is it" so that illegal
branches never enter the tree and the state description can say how far a
train still has to go. The evaluation of a state remains entirely the
networks' job.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from flatland.envs.rail_env import RailEnv

from app.policies.goal_based_policies.infrastructure_graph import (
    Cell,
    DIRECTIONS,
    DecisionPointGraph,
    GraphEdge,
    _get_transitions,
    build_decision_point_graph,
)

# A train's position in the graph, orientation included: which edges a node
# offers depends on how the train stands there, and a train cannot reverse.
Situation = Tuple[Cell, int]

# Steps a train must stand at a booked intermediate stop. Flatland counts a
# stop as served only when it records both an arrival and a departure, and a
# passenger changing trains needs the train to actually stand there.
DWELL = 1


def feasible(env: RailEnv, cell: Cell, heading: int, edge: GraphEdge) -> bool:
    """Can a train oriented `heading` on `cell` take `edge`?"""
    return bool(_get_transitions(env, cell, heading)[edge.out_direction])


@dataclass(frozen=True)
class TrainPlanData:
    """The fixed facts about one train: where it must call, and when."""
    handle: int
    stops: Tuple[Cell, ...]          # origin first, terminus last
    origin: Cell
    initial_direction: int
    earliest_departure: int
    latest_arrival: int


@dataclass
class Scenario:
    """Static context for one environment."""
    env: RailEnv
    graph: DecisionPointGraph
    trains: Tuple[TrainPlanData, ...]
    horizon: int
    node_of_cell: Dict[Cell, int] = field(default_factory=dict)
    _reverse: Dict[Situation, List[Tuple[Situation, int]]] = field(
        default_factory=dict, repr=False
    )
    _cost_cache: Dict[Cell, Dict[Situation, int]] = field(
        default_factory=dict, repr=False
    )
    _options_cache: Dict[Situation, Tuple[GraphEdge, ...]] = field(
        default_factory=dict, repr=False
    )

    @classmethod
    def build(
        cls, env: RailEnv, graph: Optional[DecisionPointGraph] = None
    ) -> "Scenario":
        from app.policies.goal_based_policies.schedule import line_stops

        graph = graph or build_decision_point_graph(env)
        trains: List[TrainPlanData] = []
        horizon = int(getattr(env, "_max_episode_steps", 0) or 200)
        for handle in range(len(env.agents)):
            agent = env.agents[handle]
            stops = tuple(line_stops(env, handle))
            trains.append(TrainPlanData(
                handle=handle,
                stops=stops,
                origin=stops[0],
                initial_direction=int(agent.initial_direction),
                earliest_departure=int(
                    getattr(agent, "earliest_departure", 0) or 0),
                latest_arrival=int(
                    getattr(agent, "latest_arrival", horizon) or horizon),
            ))
        scenario = cls(
            env=env, graph=graph, trains=tuple(trains), horizon=horizon,
            node_of_cell={
                cell: index for index, cell in enumerate(sorted(graph.nodes))
            },
        )
        scenario._build_reverse()
        return scenario

    # ---------------------------------------------------------------- moves

    def onward_edges(self, cell: Cell, heading: int) -> Tuple[GraphEdge, ...]:
        """Every way onward from standing on `cell` oriented `heading`.

        One entry per distinct next node: parallel tracks between the same
        two nodes are indistinguishable to a node-based plan, so offering
        both would produce two branches that play back identically. The
        cheapest is kept, ties broken by exit direction, so the choice is
        deterministic.
        """
        key = (cell, int(heading))
        cached = self._options_cache.get(key)
        if cached is not None:
            return cached
        best: Dict[Cell, GraphEdge] = {}
        for edge in self.graph.edges_from(cell):
            if not feasible(self.env, cell, heading, edge):
                continue
            current = best.get(edge.to_cell)
            if current is None or (
                (edge.travel_time, edge.out_direction)
                < (current.travel_time, current.out_direction)
            ):
                best[edge.to_cell] = edge
        ordered = tuple(sorted(
            best.values(), key=lambda e: (e.travel_time, e.out_direction)
        ))
        self._options_cache[key] = ordered
        return ordered

    def can_hold(self, cell: Cell, heading: int) -> bool:
        """Is holding a train standing here a decision?

        True at a platform, and at a leg approach whose switch the train is
        about to enter — the two places where standing still lets another
        train past. False in front of a split: there is no other branch to
        let through, so a hold there buys nothing and is not offered.

        Read per *direction*, not per node: one plain-rail cell is commonly
        the leg approach of the switch behind it and the head approach of
        the switch ahead of it, and which of the two a train faces depends
        on the way it is heading.
        """
        node = self.graph.nodes.get(cell)
        if node is None:
            return False
        if "station" in node.kinds:
            return True
        transitions = _get_transitions(self.env, cell, int(heading))
        return any(transitions[a.heading] for a in node.approaches)

    # ------------------------------------------------------------ distances

    def _build_reverse(self) -> None:
        """Predecessor map over `(cell, heading)` situations.

        One entry per way a train could have arrived in a situation, which
        is what lets a single search from a target fill in the cost-to-go
        of every situation at once.
        """
        reverse: Dict[Situation, List[Tuple[Situation, int]]] = {}
        for edge in self.graph.edges:
            arriving = (edge.to_cell, edge.in_direction)
            for heading in DIRECTIONS:
                if not feasible(self.env, edge.from_cell, heading, edge):
                    continue
                reverse.setdefault(arriving, []).append(
                    ((edge.from_cell, heading), edge.travel_time)
                )
        self._reverse = reverse

    def _costs_to(self, target: Cell) -> Dict[Situation, int]:
        """Travel time from every situation to standing on `target`."""
        cached = self._cost_cache.get(target)
        if cached is not None:
            return cached
        best: Dict[Situation, int] = {}
        queue: List[Tuple[int, Cell, int]] = []
        for heading in DIRECTIONS:
            best[(target, heading)] = 0
            heapq.heappush(queue, (0, target, heading))
        while queue:
            cost, cell, heading = heapq.heappop(queue)
            if cost > best.get((cell, heading), cost):
                continue
            for situation, weight in self._reverse.get((cell, heading), ()):
                candidate = cost + weight
                if candidate < best.get(situation, candidate + 1):
                    best[situation] = candidate
                    heapq.heappush(queue, (candidate, situation[0], situation[1]))
        self._cost_cache[target] = best
        return best

    def cost_to_go(
        self, cell: Cell, heading: int, target: Cell
    ) -> Optional[int]:
        """Steps from here to standing on `target`, or None if unreachable."""
        if cell == target:
            return 0
        return self._costs_to(target).get((cell, int(heading)))

    def cost_between(self, start: Cell, target: Cell) -> Optional[int]:
        """Cheapest travel time between two nodes over all orientations.

        Orientation-free on purpose: it is used for the legs *after* the
        next stop, where the orientation the train will arrive in is not
        known yet, so this is a lower bound rather than a promise.
        """
        costs = self._costs_to(target)
        candidates = [
            costs[(start, heading)]
            for heading in DIRECTIONS
            if (start, heading) in costs
        ]
        return min(candidates) if candidates else None

    def remaining_distance(
        self, cell: Cell, heading: int, stops: Sequence[Cell]
    ) -> Optional[int]:
        """Lower bound on the travel still ahead: from here to the next
        stop, then stop to stop. None when some leg is unreachable."""
        if not stops:
            return 0
        total = self.cost_to_go(cell, heading, stops[0])
        if total is None:
            return None
        for first, second in zip(stops, stops[1:]):
            leg = self.cost_between(first, second)
            if leg is None:
                return None
            total += leg
        return total


__all__ = ["DWELL", "Scenario", "Situation", "TrainPlanData", "feasible"]
