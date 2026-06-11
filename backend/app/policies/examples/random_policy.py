"""RandomPolicy: uniformly random actions. For testing/baseline only."""
import numpy as np
from flatland.core.env_observation_builder import (
    DummyObservationBuilder, ObservationBuilder,
)
from flatland.envs.rail_env_action import RailEnvActions

from app.policies.base import Policy


class RandomPolicy(Policy):
    def __init__(self, action_size: int = 5, seed: int = 42):
        self.action_size = action_size
        self._rng = np.random.default_rng(seed)

    def act_for_handle(self, handle, observation=None, eps=0.0):
        return RailEnvActions(int(self._rng.integers(0, self.action_size)))

    def build_observation_builder(self) -> ObservationBuilder:
        return DummyObservationBuilder()
