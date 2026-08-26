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

from app.utils.agent_compat import agent_direction, agent_position
from app.utils.shortest_distance_walker import ShortestDistanceWalker

Position = Tuple[int, int]


def _malfunction_remaining(agent) -> int:
    mh = getattr(agent, "malfunction_handler", None)
    return int(getattr(mh, "malfunction_down_counter", 0) or 0)


def _is_malfunctioning(agent) -> bool:
    return _malfunction_remaining(agent) > 0


class _CellStep:
    """One visited cell on the shortest path, with enough info to derive an
    alternative branch at a switch (reroute-lite)."""

    __slots__ = ("pos", "n_tr", "in_dir", "new_dir", "poss")

    def __init__(self, pos, n_tr, in_dir, new_dir, poss):
        self.pos = pos          # (row, col) reached
        self.n_tr = n_tr        # branches available at the decision cell we left
        self.in_dir = in_dir    # direction entering that decision cell
        self.new_dir = new_dir  # direction the shortest path chose
        self.poss = poss        # 4-tuple of allowed new directions at the decision


class _PathCollector(ShortestDistanceWalker):
    """Collects the shortest-path cells, switch flags, and branch directions."""

    def __init__(self, env: RailEnv):
        super().__init__(env)
        self.cells: List[Tuple[Position, int]] = []  # (position, num_transitions)
        self.steps: List[_CellStep] = []
        self._prev_dir: int | None = None

    def callback(self, handle, agent, position, direction, action, possible_transitions) -> bool:
        in_dir = self._prev_dir if self._prev_dir is not None else int(agent_direction(agent))
        n_tr = int(fast_count_nonzero(possible_transitions))
        self.cells.append((tuple(position), n_tr))
        self.steps.append(_CellStep(tuple(position), n_tr, in_dir, int(direction), tuple(possible_transitions)))
        self._prev_dir = int(direction)
        return True


def _reroute_action(step: _CellStep) -> int | None:
    """Action that takes the *alternative* branch at a switch (avoids the path
    the shortest route — toward the block — took). Returns a RailEnvActions int
    (LEFT=1, FORWARD=2, RIGHT=3) or None if there's no alternative."""
    for d in range(4):
        if step.poss[d] and d != step.new_dir:
            return int(ShortestDistanceWalker._direction_change_to_action(step.in_dir, d).value)
    return None


def compute_impact(env: RailEnv, horizon: int = 80) -> List[Dict[str, Any]]:
    """Return a list of affected-train impact items (see module docstring)."""
    if env is None:
        return []

    # 1) Blocked resources: cell -> (blocking_handle, remaining_steps).
    blocked: Dict[Position, Tuple[int, int]] = {}
    for a in env.agents:
        a_pos = agent_position(a)
        if _is_malfunctioning(a) and a_pos is not None:
            cell = tuple(a_pos)
            rem = _malfunction_remaining(a)
            # If several block the same cell, keep the longest remaining.
            if cell not in blocked or rem > blocked[cell][1]:
                blocked[cell] = (a.handle, rem)
    if not blocked:
        return []

    results: List[Dict[str, Any]] = []
    for a in env.agents:
        if agent_position(a) is None:
            continue  # off-map / not yet departed
        if getattr(a, "state", None) == TrainState.DONE:
            continue
        if _is_malfunctioning(a):
            continue  # the blocker itself

        collector = _PathCollector(env)
        collector.walk_to_target(a.handle, max_steps=horizon)

        first_switch: _CellStep | None = None  # earliest switch before the block
        for idx, step in enumerate(collector.steps, start=1):
            cell = step.pos
            if cell in blocked:
                block_handle, rem = blocked[cell]
                if idx <= rem:  # train reaches the cell before the block clears
                    # Reroute-lite: the alternative branch at the first switch the
                    # train reaches (= its next decision cell), applied as an
                    # override that fires when it gets there.
                    reroute_action = _reroute_action(first_switch) if first_switch else None
                    can_reroute = reroute_action is not None
                    recommended = "reroute" if can_reroute else "hold"
                    options = [
                        {"action": "hold", "label": "Hold", "available": True,
                         "recommended": recommended == "hold"},
                        {"action": "reroute", "label": "Reroute", "available": bool(can_reroute),
                         "recommended": recommended == "reroute"},
                        {"action": "proceed", "label": "Proceed", "available": True,
                         "recommended": False},
                    ]
                    results.append({
                        "handle": a.handle,
                        "blocked_by": block_handle,
                        "blocked_cell": [int(cell[0]), int(cell[1])],
                        "eta_steps": int(idx),
                        "clears_in_steps": int(rem),
                        "can_reroute": bool(can_reroute),
                        "reroute_action": reroute_action,
                        "reroute_cell": ([int(first_switch.pos[0]), int(first_switch.pos[1])]
                                         if first_switch else None),
                        "recommended_action": recommended,
                        "options": options,
                        "severity": "high" if idx <= max(1, rem // 2) else "medium",
                    })
                break  # only the first block on the path matters for Phase 1
            if step.n_tr > 1 and first_switch is None:
                first_switch = step

    # Most urgent first (soonest to hit the block).
    results.sort(key=lambda r: r["eta_steps"])
    return results
