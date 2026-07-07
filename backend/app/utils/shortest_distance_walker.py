"""ShortestDistanceWalker — utility ported from flatland-baselines, adapted to Flatland 4.2.6.

Purpose
-------
Walks an agent along its shortest path to its target by querying
env.distance_map at every step. Subclasses can override ``callback``
to collect data per visited cell (used by DeadLockAvoidancePolicy in
R3 to build per-agent shortest-path maps and detect oncoming conflicts).

Reference
---------
flatland-baselines: deadlock_avoidance_heuristic/utils/shortest_distance_walker.py
adapted to Flatland 4.2.6 APIs (RailEnvActions, TrainState, malfunction_handler).
"""
from typing import Optional, Tuple

import numpy as np
from flatland.core.grid.grid4_utils import get_new_position
from flatland.envs.fast_methods import fast_count_nonzero
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.step_utils.states import TrainState

Position = Tuple[int, int]

def _get_transitions(rail, row, col, direction):
    """Compatibility wrapper for Flatland's GridTransitionMap.get_transitions.

    Flatland 4.2.6 expects a single ``configuration=((row, col), direction)``
    argument, while older versions used positional ``(row, col, direction)``.
    Try both for robustness.
    """
    # Flatland 4.2.6 style.
    try:
        return rail.get_transitions(((int(row), int(col)), int(direction)))
    except TypeError:
        pass
    # Legacy positional style.
    try:
        return rail.get_transitions(int(row), int(col), int(direction))
    except TypeError:
        pass
    # Last resort: alternative tuple shape some versions accepted.
    return rail.get_transitions((int(row), int(col), int(direction)))



class ShortestDistanceWalker:
    """Walks an agent along the shortest path defined by env.distance_map."""

    def __init__(self, env: RailEnv):
        self.env = env

    def reset(self, env: RailEnv) -> None:
        self.env = env

    # ── per-cell hook ────────────────────────────────────────────────
    def callback(
        self,
        handle: int,
        agent,
        position: Position,
        direction: int,
        action: RailEnvActions,
        possible_transitions: Tuple[int, int, int, int],
    ) -> bool:
        """Called for every visited cell. Subclasses override.
        Return False to abort the walk; True to continue."""
        return True

    # ── core: pick next direction along shortest path ───────────────
    def _walk(
        self, handle: int, position: Position, direction: int
    ) -> Optional[Tuple[Position, int, RailEnvActions, Tuple[int, int, int, int]]]:
        possible_transitions = _get_transitions(self.env.rail, position[0], position[1], direction)
        num_transitions = fast_count_nonzero(possible_transitions)
        if num_transitions == 0:
            return None

        distance_map = self.env.distance_map.get()
        min_distances = np.full(4, np.inf)
        for new_direction in range(4):
            if not possible_transitions[new_direction]:
                continue
            new_position = get_new_position(position, new_direction)
            d = distance_map[handle, new_position[0], new_position[1], new_direction]
            if d is not None and not np.isinf(d):
                min_distances[new_direction] = d

        if np.all(np.isinf(min_distances)):
            new_direction = int(np.argmax(possible_transitions))
        else:
            new_direction = int(np.argmin(min_distances))

        new_position = get_new_position(position, new_direction)
        action = self._direction_change_to_action(direction, new_direction)
        return new_position, new_direction, action, possible_transitions

    @staticmethod
    def _direction_change_to_action(
        old_direction: int, new_direction: int
    ) -> RailEnvActions:
        delta = (new_direction - old_direction) % 4
        if delta == 0:
            return RailEnvActions.MOVE_FORWARD
        if delta == 3:
            return RailEnvActions.MOVE_LEFT
        if delta == 1:
            return RailEnvActions.MOVE_RIGHT
        # delta == 2 → reversal (dead-end); Flatland uses MOVE_FORWARD.
        return RailEnvActions.MOVE_FORWARD

    # ── public API ───────────────────────────────────────────────────
    def walk_one_step(self, handle: int):
        """Lookahead one step. Returns (pos, dir, action, transitions) or None."""
        agent = self.env.agents[handle]
        position, direction = self._effective_pos_dir(agent)
        if position is None:
            return None
        return self._walk(handle, position, direction)

    def walk_to_target(self, handle: int, max_steps: Optional[int] = None) -> int:
        """Walk along shortest path to target, firing callback per cell.
        Returns number of cells walked (excluding the start cell)."""
        agent = self.env.agents[handle]
        position, direction = self._effective_pos_dir(agent)
        if position is None:
            return 0
        if max_steps is None:
            max_steps = self.env.height * self.env.width
        steps = 0
        target = agent.target
        while steps < max_steps:
            walked = self._walk(handle, position, direction)
            if walked is None:
                break
            new_position, new_direction, action, possible_transitions = walked
            cont = self.callback(
                handle, agent, new_position, new_direction, action, possible_transitions
            )
            steps += 1
            position, direction = new_position, new_direction
            if not cont:
                break
            if position == target:
                break
        return steps

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _effective_pos_dir(agent):
        """Where to walk from, based on agent state."""
        state = getattr(agent, "state", None)
        if state == TrainState.DONE:
            return None, None
        if agent.position is not None:
            return agent.position, agent.direction
        if state in (
            TrainState.WAITING,
            TrainState.READY_TO_DEPART,
            TrainState.MALFUNCTION_OFF_MAP,
        ):
            return agent.initial_position, agent.initial_direction
        return None, None
