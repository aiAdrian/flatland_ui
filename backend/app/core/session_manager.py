import uuid
from typing import Dict, Optional
from flatland.envs.rail_env import RailEnv
from app.core.env_factory import create_env
from app.policies.registry import scenario_policy_factories


class Session:
    def __init__(self, session_id: str, env: RailEnv):
        self.id = session_id
        self.env = env
        self.last_observations = None
        self.last_info = None
        # Currently active policy (used as baseline in /hmi/scenarios
        # and applied to every step unless overridden in the step request).
        self.policy: str = "deadlock_avoidance"
        # Session-scoped filter for scenario candidates (UI toggles).
        self.enabled_scenario_policies: set[str] = set(scenario_policy_factories().keys())


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create(self, **env_kwargs) -> Session:
        sid = str(uuid.uuid4())[:8]
        # Pull out max_episode_steps BEFORE create_env (Flatland's reset()
        # would overwrite it otherwise). We re-apply it after reset().
        max_ep_override = env_kwargs.pop("max_episode_steps", None)
        env = create_env(**env_kwargs)
        session = Session(sid, env)
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
