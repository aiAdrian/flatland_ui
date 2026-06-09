import uuid
from typing import Dict, Optional
from flatland.envs.rail_env import RailEnv
from app.core.env_factory import create_env


class Session:
    def __init__(self, session_id: str, env: RailEnv):
        self.id = session_id
        self.env = env
        self.last_observations = None
        self.last_info = None
        # Currently active policy (used as baseline in /hmi/scenarios
        # and applied to every step unless overridden in the step request).
        self.policy: str = "deadlock_avoidance" 


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create(self, **env_kwargs) -> Session:
        sid = str(uuid.uuid4())[:8]
        env = create_env(**env_kwargs)
        session = Session(sid, env)
        obs, info = env.reset()
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
