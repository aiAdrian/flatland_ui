"""Runtime policy wrapper for user action overrides.

Semantics:
- Setting an override does NOT execute it immediately.
- The wrapped/base policy controls the train until the agent reaches a
  decision point.
- At a decision point (SWITCH or MERGING), the override action is applied once.
- Immediately after application, the override is cleared.

UI mental model:
  "Apply my next action at the next decision point."
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

from flatland.envs.rail_env import RailEnvActions
from flatland.envs.step_utils.states import TrainState

from app.core.cell_classifier import classify_cell_at
from app.core.override_manager import override_manager


class OverridePolicy:
    """Wrap a runtime policy and delay user overrides until a decision point."""

    def __init__(self, default_policy: Any, session_id: str):
        self.default_policy = default_policy
        self.session_id = session_id
        self.env = None

    def reset(self, env) -> None:
        self.env = env
        if hasattr(self.default_policy, "reset"):
            self.default_policy.reset(env)

    def start_episode(self) -> None:
        if hasattr(self.default_policy, "start_episode"):
            self.default_policy.start_episode()

    def end_episode(self) -> None:
        if hasattr(self.default_policy, "end_episode"):
            self.default_policy.end_episode()

    def start_step(self) -> None:
        if hasattr(self.default_policy, "start_step"):
            self.default_policy.start_step()

    def end_step(self) -> None:
        if hasattr(self.default_policy, "end_step"):
            self.default_policy.end_step()

    def act_many(self, handles: Iterable[int], observations: Dict[int, Any]) -> Dict[int, Any]:
        handles = [int(h) for h in handles]

        if hasattr(self.default_policy, "act_many"):
            actions = dict(self.default_policy.act_many(handles, observations) or {})
        else:
            actions = {
                h: self.default_policy.act(h, observations.get(h))
                for h in handles
            }

        if self.env is None:
            return actions

        for h in handles:
            override_action = override_manager.get(self.session_id, h)
            if override_action is None:
                continue

            agent = self.env.agents[h]

            # Done agents do not need pending overrides anymore.
            if getattr(agent, "state", None) == TrainState.DONE:
                override_manager.clear(self.session_id, h)
                continue

            pos = getattr(agent, "position", None)
            direction = getattr(agent, "direction", None)

            # Off-map / not ready yet:
            # keep override pending, do not apply.
            if pos is None or direction is None:
                continue

            cur_pos = (int(pos[0]), int(pos[1]))

            # Core bug fix:
            # Override is only consumed at an actual decision point.
            cell_type = classify_cell_at(self.env, cur_pos, int(direction))
            if cell_type not in ("SWITCH", "MERGING"):
                continue

            # At DP: apply override.
            action = RailEnvActions(int(override_action))
            actions[h] = action

            # STOP is sticky at the decision point:
            # keep issuing STOP until the user clears/replaces the override.
            #
            # LEFT/FORWARD/RIGHT are one-shot decision actions:
            # apply once at the DP, then clear.
            if action != RailEnvActions.STOP_MOVING:
                override_manager.clear(self.session_id, h)

        return actions

    def act(self, handle: int, observation: Any = None) -> Any:
        handle = int(handle)
        return self.act_many([handle], {handle: observation}).get(handle)

    def act_for_handle(self, handle: int) -> Any:
        """Backwards-compatible helper used by tests/callers."""
        handle = int(handle)
        return self.act_many([handle], {handle: self.env}).get(handle)
