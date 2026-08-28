"""Per-session memo for the `/hmi/contentions` forecast.

`run_branch(overrides={})` forks and simulates forward to find the conflicts
ahead, so it is too costly to re-run on every poll. The result depends only
on (session_id, current_step) — the env state at that step — so one compute
per step serves every poll within that step. When the env advances, the step
key changes and a fresh compute runs.

Deliberately separate from `scenario_cache`: that cache keys on step +
override hash + KPI weights and stores Scenario/options shapes; contentions
are a different signal (forecast conflicts, not scored scenarios) and a
different invalidation rule (override-agnostic — the *predicted* course
ignores operator overrides by design, see `run_branch(overrides={})`).
"""
from typing import Any, Dict, List, Optional, Tuple


class ContentionCache:
    def __init__(self):
        # (session_id, step) -> list of contention groups.
        self._cache: Dict[Tuple[str, int], List[Any]] = {}

    def get(self, session_id: str, step: int) -> Optional[List[Any]]:
        return self._cache.get((session_id, step))

    def put(self, session_id: str, step: int, groups: List[Any]) -> None:
        # Drop stale steps for this session so the cache holds at most the
        # latest compute per session (one entry each, bounded by session count).
        self._cache = {
            k: v for k, v in self._cache.items()
            if not (k[0] == session_id and k[1] != step)
        }
        self._cache[(session_id, step)] = groups

    def clear_session(self, session_id: str) -> None:
        self._cache = {k: v for k, v in self._cache.items() if k[0] != session_id}


contention_cache = ContentionCache()
