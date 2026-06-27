import uuid
from typing import Dict, Optional
from flatland.envs.rail_env import RailEnv
from app.core.env_factory import create_env
from app.policies.registry import scenario_policy_factories, policy_specs


class Session:
    def __init__(
        self,
        session_id: str,
        env: RailEnv,
        enabled_scenario_policies: set[str] | None = None,
        enabled_policy_ids: set[str] | None = None,
    ):
        self.id = session_id
        self.env = env
        self.last_observations = None
        self.last_info = None
        # Creation seed + episode length, so reset() can replay the IDENTICAL
        # scenario (same rail, schedule, malfunctions) instead of rolling a new
        # random episode. Set by SessionManager.create.
        self.seed: int | None = None
        self.max_episode_steps: int | None = None
        # Currently active policy (used as baseline in /hmi/scenarios
        # and applied to every step unless overridden in the step request).
        self.policy: str = "deadlock_avoidance"
        # Session-scoped filter for scenario candidates (UI toggles).
        scenario_available = set(scenario_policy_factories().keys())
        scenario_enabled = enabled_scenario_policies or scenario_available
        self.enabled_scenario_policies: set[str] = set(scenario_enabled) & scenario_available
        if not self.enabled_scenario_policies:
            self.enabled_scenario_policies = scenario_available

        policy_available = {spec.id for spec in policy_specs(include_hidden=True) if spec.show_in_ui}
        policy_enabled = enabled_policy_ids or policy_available
        self.enabled_policy_ids: set[str] = set(policy_enabled) & policy_available
        if not self.enabled_policy_ids:
            self.enabled_policy_ids = policy_available

        # Real executed trajectory history for Marey.
        # Shape compatible with hmi_scenario_adapter._extract_trajectories().
        self.marey_history_snapshots: list[dict] = []


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create(self, **env_kwargs) -> Session:
        sid = str(uuid.uuid4())[:8]
        # Pull out max_episode_steps BEFORE create_env (Flatland's reset()
        # would overwrite it otherwise). We re-apply it after reset().
        max_ep_override = env_kwargs.pop("max_episode_steps", None)
        enabled_scenario_policy_ids = env_kwargs.pop("enabled_scenario_policy_ids", None)
        enabled_policy_ids = env_kwargs.pop("enabled_policy_ids", None)
        enabled_scenario_policy_set = set(enabled_scenario_policy_ids or []) if enabled_scenario_policy_ids is not None else None
        enabled_policy_set = set(enabled_policy_ids or []) if enabled_policy_ids is not None else None
        env = create_env(**env_kwargs)
        session = Session(sid, env, enabled_scenario_policy_set, enabled_policy_set)
        seed = env_kwargs.get("seed")
        session.seed = int(seed) if seed is not None else None
        session.max_episode_steps = (
            int(max_ep_override) if max_ep_override is not None and int(max_ep_override) > 0 else None
        )
        # env_factory already reset() the env (inside its retry block, so
        # IndexErrors from timetable_generator are caught). Reuse stashed
        # obs/info instead of resetting again.
        obs = getattr(env, "_initial_obs", None)
        info = getattr(env, "_initial_info", None)
        if obs is None:
            obs, info = env.reset()
        if max_ep_override is not None and int(max_ep_override) > 0:
            env._max_episode_steps = int(max_ep_override)
        session.last_observations = obs
        session.last_info = info
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def list_ids(self):
        return list(self._sessions.keys())


session_manager = SessionManager()
