"""Executed trajectory history snapshots for Marey.

The stored shape intentionally matches Scenario/Conflict snapshots:
  {"step": int, "agents": {"0": {"pos": [r, c], "dir": d, "state": "MOVING"}}}

This lets hmi_scenario_adapter._extract_trajectories(...) enrich real
history with the same classify_marey_point(...) logic used for forecasts.
"""
from __future__ import annotations

from typing import Any


def _agent_state_name(agent: Any) -> str:
    state = getattr(agent, "state", None)
    return getattr(state, "name", str(state))


def capture_marey_history_snapshot(session: Any) -> None:
    """Capture one real executed env state for Marey history."""
    env = getattr(session, "env", None)
    if env is None:
        return

    try:
        step = int(getattr(env, "_elapsed_steps", 0) or 0)
    except Exception:
        step = 0

    agents: dict[str, dict] = {}

    for handle, agent in enumerate(getattr(env, "agents", []) or []):
        pos = getattr(agent, "position", None)
        direction = getattr(agent, "direction", None)

        # Off-map agents do not have a Marey path cell yet.
        if pos is None or direction is None:
            continue

        try:
            row, col = int(pos[0]), int(pos[1])
            dir_i = int(direction)
        except Exception:
            continue

        agents[str(handle)] = {
            "pos": [row, col],
            "dir": dir_i,
            "state": _agent_state_name(agent),
        }

    snap = {"step": step, "agents": agents}

    hist = list(getattr(session, "marey_history_snapshots", []) or [])

    # Avoid duplicate snapshots for repeated state polling at the same step.
    if hist and int(hist[-1].get("step", -1)) == step:
        hist[-1] = snap
    else:
        hist.append(snap)

    session.marey_history_snapshots = hist


def reset_marey_history(session: Any) -> None:
    session.marey_history_snapshots = []
    capture_marey_history_snapshot(session)
