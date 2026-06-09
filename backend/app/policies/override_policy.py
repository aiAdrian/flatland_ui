"""OverridePolicy: wraps any inner Policy and applies user overrides
at SWITCH/MERGING cells.

Adapted to the R1 hybrid Policy interface: forwards lifecycle hooks
(reset/start_step/end_step) to the wrapped default policy, so
stateful heuristics (e.g. DeadLockAvoidance) keep working.
"""
from typing import Optional

from flatland.core.env_observation_builder import ObservationBuilder
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions

from app.core.cell_classifier import classify_cell_at as classify_cell
from app.core.override_manager import override_manager
from app.policies.base import Policy


class OverridePolicy(Policy):
    """Wraps any policy; user overrides win at SWITCH/MERGING cells."""

    def __init__(self, default: Policy, session_id: str):
        self._default = default
        self._session_id = session_id
        self._env: Optional[RailEnv] = None

    # ── lifecycle: forward to wrapped policy ─────────────────────────
    def reset(self, env: RailEnv) -> None:
        self._env = env
        self._default.reset(env)

    def start_episode(self, train: bool = False) -> None:
        self._default.start_episode(train)

    def start_step(self, train: bool = False) -> None:
        self._default.start_step(train)

    def end_step(self, train: bool = False) -> None:
        self._default.end_step(train)

    def end_episode(self, train: bool = False) -> None:
        self._default.end_episode(train)

    # ── observation belongs to the wrapped policy ───────────────────
    def build_observation_builder(self) -> ObservationBuilder:
        return self._default.build_observation_builder()

    def build_predictor(self):
        return self._default.build_predictor()

    # ── action selection ─────────────────────────────────────────────
    def act_many(self, handles, observations, **kwargs):
        # 1) Ask default policy for baseline actions.
        actions = self._default.act_many(handles, observations, **kwargs)
        # 2) Overlay user overrides where applicable, and auto-clear
        #    them once the agent reaches its decision point. The
        #    override is a *one-shot* directive: it represents the
        #    user's choice for the agent's NEXT decision point.
        #    Once that decision is made, the default policy takes
        #    over again on subsequent steps.
        env = self._env
        if env is None:
            return actions
        for h in handles:
            override = override_manager.get(self._session_id, h)
            if override is None:
                continue
            agent = env.agents[h]
            if agent.position is None:
                # Agent is off-map (WAITING / DONE) — keep the override
                # parked; it will be applied when the agent reaches
                # its first SWITCH/MERGING cell.
                continue
            cell_kind = classify_cell(env, agent.position, agent.direction)
            if cell_kind in ("SWITCH", "MERGING"):
                # Apply the override AND consume it.
                actions[h] = RailEnvActions(int(override))
                override_manager.clear(self._session_id, h)
            # If the agent is at a non-decision cell, the override
            # is parked: we keep it until the agent reaches a
            # decision point. (The user clicked early; that's OK.)
        return actions

    def act_for_handle(self, handle, observation=None, eps=0.0):
        # Single-agent path — used rarely, mainly for tests/tools.
        # Mirrors act_many: apply override at decision cells, then
        # auto-clear so it's a one-shot directive.
        action = self._default.act_for_handle(handle, observation, eps)
        env = self._env
        if env is None:
            return action
        override = override_manager.get(self._session_id, handle)
        if override is None:
            return action
        agent = env.agents[handle]
        if agent.position is None:
            return action
        cell_kind = classify_cell(env, agent.position, agent.direction)
        if cell_kind in ("SWITCH", "MERGING"):
            override_manager.clear(self._session_id, handle)
            return RailEnvActions(int(override))
        return action

    def get_name(self) -> str:
        return f"Override({self._default.get_name()})"
