"""Impact analysis (Phase 1): which trains are affected by another train's
malfunction, and a coarse recommendation per affected train.

Approach (cheap, no forward simulation):
- A malfunctioning train blocks its cell for `malfunction_down_counter` steps.
- For every other on-map train, walk its shortest path (ShortestDistanceWalker).
  If the path crosses a blocked cell *before that block clears*, the train is
  affected. ETA-to-block ≈ number of cells to reach it (speed 1 assumption).
- Recommendation: if the train passes a switch (decision point) before the block
  → "reroute" is possible; otherwise it can only "hold".

Phase 2 (later) would simulate each option and score it (delay/deadlock) for a
ranked recommendation — see docs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from flatland.envs.fast_methods import fast_count_nonzero
from flatland.envs.rail_env import RailEnv
from flatland.envs.step_utils.states import TrainState

from app.utils.shortest_distance_walker import ShortestDistanceWalker

Position = Tuple[int, int]


def _malfunction_remaining(agent) -> int:
    mh = getattr(agent, "malfunction_handler", None)
    return int(getattr(mh, "malfunction_down_counter", 0) or 0)


def _is_malfunctioning(agent) -> bool:
    return _malfunction_remaining(agent) > 0


class _PathCollector(ShortestDistanceWalker):
    """Collects the shortest-path cells and whether each cell is a switch."""

    def __init__(self, env: RailEnv):
        super().__init__(env)
        self.cells: List[Tuple[Position, int]] = []  # (position, num_transitions)

    def callback(self, handle, agent, position, direction, action, possible_transitions) -> bool:
        self.cells.append((tuple(position), int(fast_count_nonzero(possible_transitions))))
        return True


def compute_impact(env: RailEnv, horizon: int = 80) -> List[Dict[str, Any]]:
    """Return a list of affected-train impact items (see module docstring)."""
    if env is None:
        return []

    # 1) Blocked resources: cell -> (blocking_handle, remaining_steps).
    blocked: Dict[Position, Tuple[int, int]] = {}
    for a in env.agents:
        if _is_malfunctioning(a) and a.position is not None:
            cell = tuple(a.position)
            rem = _malfunction_remaining(a)
            # If several block the same cell, keep the longest remaining.
            if cell not in blocked or rem > blocked[cell][1]:
                blocked[cell] = (a.handle, rem)
    if not blocked:
        return []

    results: List[Dict[str, Any]] = []
    for a in env.agents:
        if a.position is None:
            continue  # off-map / not yet departed
        if getattr(a, "state", None) == TrainState.DONE:
            continue
        if _is_malfunctioning(a):
            continue  # the blocker itself

        collector = _PathCollector(env)
        collector.walk_to_target(a.handle, max_steps=horizon)

        switch_before = False
        for idx, (cell, n_tr) in enumerate(collector.cells, start=1):
            if cell in blocked:
                block_handle, rem = blocked[cell]
                if idx <= rem:  # train reaches the cell before the block clears
                    results.append({
                        "handle": a.handle,
                        "blocked_by": block_handle,
                        "blocked_cell": [int(cell[0]), int(cell[1])],
                        "eta_steps": int(idx),
                        "clears_in_steps": int(rem),
                        "can_reroute": bool(switch_before),
                        "recommended_action": "reroute" if switch_before else "hold",
                        "severity": "high" if idx <= max(1, rem // 2) else "medium",
                    })
                break  # only the first block on the path matters for Phase 1
            if n_tr > 1:
                switch_before = True

    # Most urgent first (soonest to hit the block).
    results.sort(key=lambda r: r["eta_steps"])
    return results
