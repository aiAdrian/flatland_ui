"""DeadLockAvoidancePolicy — heuristic policy ported from flatland-baselines.

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

    # ── observation bundle ───────────────────────────────────────────
    def build_observation_builder(self) -> ObservationBuilder:
        # Baselines uses FullEnvObservation; we ship the same. The policy
        # itself works directly with self._env (set via reset), so this
        # builder is only relevant if the caller wires it into the env.
        return FullEnvObservation()

    # ── lifecycle ────────────────────────────────────────────────────
    def reset(self, env: RailEnv) -> None:
        self._env = env
        self._walker = DeadlockAvoidanceShortestDistanceWalker(env)
        self._agent_can_move = {}
        self._agent_positions = None

    def start_step(self, train: bool = False) -> None:
        """Recompute shortest-path maps and conflict info for all agents."""
        if self._env is None or self._walker is None:
            return
        self._build_agent_position_map()
        self._walk_all_agents()
        self._extract_agent_can_move()

    # ── action selection ─────────────────────────────────────────────
    def act_for_handle(
        self, handle: int, observation=None, eps: float = 0.0
    ) -> RailEnvActions:
        info = self._agent_can_move.get(handle)
        if info is None:
            return RailEnvActions.STOP_MOVING
        # info = (next_row, next_col, next_direction, action)
        return info[3]

    def act_many(self, handles, observations, **kwargs) -> Dict[int, RailEnvActions]:
        # If a FullEnvObservation was wired in, observations[h] is the env
        # itself — keep our reference fresh.
        if observations and isinstance(observations, list) and observations:
            first = observations[0]
            if hasattr(first, "agents") and hasattr(first, "rail"):
                if first is not self._env:
                    self.reset(first)

        # Recompute per step. Safe to call here too if caller forgot
        # to invoke start_step explicitly.
        if not self._agent_can_move:
            self.start_step()

        return {h: self.act_for_handle(h) for h in handles}

    # ── internals ────────────────────────────────────────────────────
    def _build_agent_position_map(self) -> None:
        """Mark cells currently occupied by active agents."""
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
        """Build per-agent shortest-path maps via the walker."""
        self._walker.clear(self._agent_positions)
        env = self._env
        for h in range(env.get_num_agents()):
            agent = env.agents[h]
            if agent.state <= TrainState.MALFUNCTION:
                self._walker.walk_to_target(h)

    def _extract_agent_can_move(self) -> None:
        """For each agent, decide if forward motion is safe."""
        self._agent_can_move = {}
        env = self._env
        shortest_map, full_map = self._walker.get_data()

        for h in range(env.get_num_agents()):
            agent = env.agents[h]
            if agent.state >= TrainState.DONE:
                continue

            same_agents = self._walker.same_agent_map.get(h, [])
            opp_agents = self._walker.opp_agent_map.get(h, [])

            if self._can_agent_move(h, shortest_map[h], same_agents, opp_agents, full_map):
                lookahead = self._walker.walk_one_step(h)
                if lookahead is None:
                    continue
                next_position, next_direction, action, _ = lookahead
                self._agent_can_move[h] = (
                    next_position[0],
                    next_position[1],
                    next_direction,
                    action,
                )

    def _can_agent_move(
        self,
        handle: int,
        my_shortest_walking_path: np.ndarray,
        same_agents: List[int],
        opp_agents: List[int],
        full_shortest_distance_agent_map: np.ndarray,
    ) -> bool:
        """Pairwise check: enough free buffer cells against each oncoming agent?"""
        if self._agent_positions is None:
            return True

        agent_positions_map = (self._agent_positions > -1).astype(int)
        len_opp_agents = len(opp_agents)

        for opp_a in opp_agents:
            opp = full_shortest_distance_agent_map[opp_a]
            # Cells of my safe corridor that are not on opp's path
            # and not currently occupied.
            delta = ((my_shortest_walking_path - opp - agent_positions_map) > 0).astype(int)
            sum_delta = int(np.sum(delta))
            if sum_delta < (self.min_free_cell + len_opp_agents):
                return False
        return True

    def get_name(self) -> str:
        return "DeadLockAvoidancePolicy"
