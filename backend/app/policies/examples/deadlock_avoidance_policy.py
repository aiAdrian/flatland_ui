"""DeadLockAvoidancePolicy - heuristic policy ported from flatland-baselines.

Algorithm
---------
For each environment step:

1. Build an occupancy map from active agents.
2. For each agent, walk its shortest path to target and record:
   - the path cells,
   - any oncoming agents on that path,
   - any same-direction agents on that path.
3. Decide per agent: can it move forward?
   An agent can move iff for every oncoming agent, there are at least
   ``min_free_cell + #oncoming`` cells in its path that are *not* shared
   with that oncoming agent's path and are *not* currently occupied.
4. If yes: take the shortest-path action. If no: STOP_MOVING.

Guarantees
----------
- Pairwise deadlock-free (under sparse_rail / no dead-ends).
- First-come-first-serve at conflicts: lower agent handle wins.

Reference
---------
flatland_baselines/deadlock_avoidance_heuristic/policy/deadlock_avoidance_policy.py
adapted to Flatland 4.2.6 + our hybrid Policy interface (R1).
"""
from typing import Dict, List, Optional

import numpy as np
from flatland.core.env_observation_builder import ObservationBuilder
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.step_utils.states import TrainState

from app.observations.full_env_observation import FullEnvObservation
from app.policies.base import Policy
from app.utils.deadlock_avoidance_walker import (
    DeadlockAvoidanceShortestDistanceWalker,
)


class DeadLockAvoidancePolicy(Policy):
    """Pairwise deadlock-free heuristic. Default policy candidate for our HMI."""

    def __init__(self, min_free_cell: int = 1):
        self.min_free_cell = min_free_cell
        self._env: Optional[RailEnv] = None
        self._walker: Optional[DeadlockAvoidanceShortestDistanceWalker] = None
        self._agent_can_move: Dict[int, tuple] = {}
        self._agent_positions: Optional[np.ndarray] = None

    # observation bundle
    def build_observation_builder(self) -> ObservationBuilder:
        return FullEnvObservation()

    # lifecycle
    def reset(self, env: RailEnv) -> None:
        self._env = env
        self._walker = DeadlockAvoidanceShortestDistanceWalker(env)
        self._agent_can_move = {}
        self._agent_positions = None

    def start_step(self, train: bool = False) -> None:
        if self._env is None or self._walker is None:
            return
        self._build_agent_position_map()
        self._walk_all_agents()
        self._extract_agent_can_move()

    # action selection
    def act_for_handle(
        self, handle: int, observation=None, eps: float = 0.0
    ) -> RailEnvActions:
        info = self._agent_can_move.get(handle)
        if info is None:
            return RailEnvActions.STOP_MOVING
        return info[3]

    def act_many(self, handles, observations, **kwargs) -> Dict[int, RailEnvActions]:
        if observations and isinstance(observations, list) and observations:
            first = observations[0]
            if hasattr(first, "agents") and hasattr(first, "rail"):
                if first is not self._env:
                    self.reset(first)

        if not self._agent_can_move:
            self.start_step()

        return {h: self.act_for_handle(h) for h in handles}

    # internals
    def _build_agent_position_map(self) -> None:
        env = self._env
        positions = np.full((env.height, env.width), -1, dtype=int)
        for h in range(env.get_num_agents()):
            agent = env.agents[h]
            if agent.state in (
                TrainState.MOVING,
                TrainState.STOPPED,
                TrainState.MALFUNCTION,
            ) and agent.position is not None:
                positions[agent.position] = h
        self._agent_positions = positions

    def _walk_all_agents(self) -> None:
        self._walker.clear(self._agent_positions)
        env = self._env
        for h in range(env.get_num_agents()):
            self._walker.walk_to_target(handle=h)

    def _extract_agent_can_move(self) -> None:
        walker = self._walker
        env = self._env
        can_move: Dict[int, tuple] = {}
        active = set()
        for h in range(env.get_num_agents()):
            a = env.agents[h]
            if a.state in (TrainState.MOVING, TrainState.STOPPED, TrainState.MALFUNCTION, TrainState.READY_TO_DEPART):
                active.add(h)

        for h in sorted(active):
            next_info = walker.get_next_positions(h)
            if next_info is None:
                can_move[h] = (None, None, None, RailEnvActions.STOP_MOVING)
                continue
            can_move[h] = next_info

        self._agent_can_move = can_move
