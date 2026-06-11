"""Template for adding a custom policy.

Copy this file, rename class + module, implement act_for_handle,
and register it in app.policies.registry.REGISTRY.
"""
from flatland.core.env_observation_builder import DummyObservationBuilder, ObservationBuilder
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions

from app.policies.base import Policy


class TemplatePolicy(Policy):
    """Minimal custom policy template with lifecycle + observation hooks."""

    def __init__(self):
        self._env: RailEnv | None = None

    def reset(self, env: RailEnv) -> None:
        self._env = env

    def build_observation_builder(self) -> ObservationBuilder:
        # Replace with your own observation builder if needed.
        return DummyObservationBuilder()

    def act_for_handle(self, handle: int, observation=None, eps: float = 0.0):
        # TODO: replace with your decision logic.
        return RailEnvActions.DO_NOTHING
