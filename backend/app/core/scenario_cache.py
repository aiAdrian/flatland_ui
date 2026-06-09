"""Step-keyed cache for ScenarioBuilder results.

Computing 5 branches × 50 steps takes ~1s per /hmi/scenarios call.
Frontend polls every few seconds, but the env state only changes when
env._elapsed_steps advances. So we cache by (session_id, step) and
return immediately if nothing has changed.
"""
from typing import Any, Dict, List, Optional, Tuple


class ScenarioCache:
    def __init__(self):
        # (session_id, elapsed_step) -> List[Scenario]
        self._cache: Dict[Tuple[str, int], List[Any]] = {}

    def get(self, session_id: str, step: int) -> Optional[List[Any]]:
        return self._cache.get((session_id, step))

    def put(self, session_id: str, step: int, scenarios: List[Any]) -> None:
        # Drop older entries for this session to bound memory.
        self._cache = {k: v for k, v in self._cache.items() if k[0] != session_id}
        self._cache[(session_id, step)] = scenarios

    def clear_session(self, session_id: str) -> None:
        self._cache = {k: v for k, v in self._cache.items() if k[0] != session_id}


scenario_cache = ScenarioCache()
