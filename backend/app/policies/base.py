"""Hybrid Policy interface for the Flatland HMI backend.

Compatible with Flatland 4.2.6:
- act_many(handles, observations) matches flatland.core.policy.Policy,
  so policies can be used directly with PolicyRunner.create_from_policy
  and TrajectoryEvaluator.

Extended with:
- build_observation_builder() / build_predictor() so each policy ships
  with its matching ObservationBuilder. Inspired by flatland-baselines,
  where DeadLockAvoidancePolicy requires FullEnvObservation while
  ShortestPathPolicy works with TreeObs etc.
- Lifecycle hooks (reset/start_step/end_step/...) for stateful
  heuristics like DeadLockAvoidancePolicy which recompute distance
  maps each step.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Generic, TypeVar, Optional

from flatland.core.env_observation_builder import ObservationBuilder
from flatland.core.env_prediction_builder import PredictionBuilder
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions

T_obs = TypeVar("T_obs")


class Policy(ABC, Generic[T_obs]):
    """Hybrid policy: Flatland-compatible (act_many) + lifecycle hooks."""

    def act_many(self, handles, observations, **kwargs):
        return {
            h: self.act_for_handle(
                h, observations[h] if observations else None
            )
            for h in handles
        }

    @abstractmethod
    def act_for_handle(self, handle, observation=None, eps=0.0):
        ...

    @abstractmethod
    def build_observation_builder(self) -> ObservationBuilder:
        ...

    def build_predictor(self) -> Optional[PredictionBuilder]:
        return None

    def reset(self, env: RailEnv) -> None:
        pass

    def start_episode(self, train: bool = False) -> None:
        pass

    def start_step(self, train: bool = False) -> None:
        pass

    def end_step(self, train: bool = False) -> None:
        pass

    def end_episode(self, train: bool = False) -> None:
        pass

    def step(self, handle, state, action, reward, next_state, done) -> None:
        pass

    def get_name(self) -> str:
        return self.__class__.__name__

    def save(self, filename: str) -> None:
        pass

    def load(self, filename: str) -> None:
        pass

    def clone(self) -> "Policy":
        return self
