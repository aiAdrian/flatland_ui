"""DeadlockAvoidanceShortestDistanceWalker — Walker subclass that builds
per-agent shortest-path maps and detects oncoming/same-direction agents
on the path.

Adapted from flatland-baselines:
  flatland_baselines/deadlock_avoidance_heuristic/policy/deadlock_avoidance_policy.py

Used by DeadLockAvoidancePolicy (R3 Part 2) to decide whether an agent
can safely move forward or must stop to avoid a head-to-head conflict.
"""
from typing import Dict, List, Tuple

import numpy as np
from flatland.envs.fast_methods import fast_count_nonzero
from flatland.envs.rail_env import RailEnv

from app.utils.agent_compat import agent_direction
from app.utils.shortest_distance_walker import (
    ShortestDistanceWalker,
    _get_transitions,
)

Position = Tuple[int, int]


class DeadlockAvoidanceShortestDistanceWalker(ShortestDistanceWalker):
    """Walker that records per-agent path maps and conflict info.

    After ``walk_to_target`` has been called for every agent, the
    accumulated maps describe each agent's shortest path and the set
    of other agents encountered along it.
    """

    def __init__(self, env: RailEnv):
        super().__init__(env)
        self.shortest_distance_agent_map: np.ndarray | None = None
        self.full_shortest_distance_agent_map: np.ndarray | None = None
        self.agent_positions: np.ndarray | None = None
        self.opp_agent_map: Dict[int, List[int]] = {}
        self.same_agent_map: Dict[int, List[int]] = {}

    # ── lifecycle ────────────────────────────────────────────────────
    def reset(self, env: RailEnv) -> None:
        super().reset(env)
        self.shortest_distance_agent_map = None
        self.full_shortest_distance_agent_map = None
        self.agent_positions = None
        self.opp_agent_map = {}
        self.same_agent_map = {}

    def clear(self, agent_positions: np.ndarray) -> None:
        """Reset per-step buffers. Called once per env step before
        walking each agent."""
        n_agents = self.env.get_num_agents()
        h, w = self.env.height, self.env.width
        self.shortest_distance_agent_map = np.full((n_agents, h, w), -1, dtype=int)
        self.full_shortest_distance_agent_map = np.full((n_agents, h, w), -1, dtype=int)
        self.agent_positions = agent_positions
        self.opp_agent_map = {}
        self.same_agent_map = {}

    def get_data(self):
        return self.shortest_distance_agent_map, self.full_shortest_distance_agent_map

    # ── per-cell hook ────────────────────────────────────────────────
    def callback(
        self,
        handle: int,
        agent,
        position: Position,
        direction: int,
        action,
        possible_transitions,
    ) -> bool:
        """Record this cell on the agent's path and inspect any agent
        currently occupying it."""
        if self.agent_positions is None:
            return True

        opp_a = int(self.agent_positions[position])

        if opp_a != -1 and opp_a != handle:
            other = self.env.agents[opp_a]
            if agent_direction(other) != direction:
                # Oncoming agent (head-to-head).
                self.opp_agent_map.setdefault(handle, [])
                if opp_a not in self.opp_agent_map[handle]:
                    self.opp_agent_map[handle].append(opp_a)
            else:
                # Same-direction agent. Only track if no head-to-head
                # has been seen yet — head-to-head dominates.
                if not self.opp_agent_map.get(handle):
                    self.same_agent_map.setdefault(handle, [])
                    if opp_a not in self.same_agent_map[handle]:
                        self.same_agent_map[handle].append(opp_a)

        # Record path. Mark non-switch cells in the "safe corridor" map.
        if not self.opp_agent_map.get(handle):
            if self._is_no_switch_cell(position):
                self.shortest_distance_agent_map[handle, position[0], position[1]] = 1
        self.full_shortest_distance_agent_map[handle, position[0], position[1]] = 1

        return True

    # ── helper ───────────────────────────────────────────────────────
    def _is_no_switch_cell(self, position: Position) -> bool:
        """A cell is a switch if any orientation has more than one transition."""
        for new_dir in range(4):
            possible_transitions = _get_transitions(
                self.env.rail, position[0], position[1], new_dir
            )
            if fast_count_nonzero(possible_transitions) > 1:
                return False
        return True
