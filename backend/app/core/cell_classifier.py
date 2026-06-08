"""
Cell-Type Classification for Decision Points.

Portierung von DecisionPointUtils - klassifiziert Rail-Cells in:
- OUTSIDE: Agent noch nicht auf Map
- FORWARD_ONLY: Single rail path (no choice)
- MERGING: Vor Merge-Punkt (binary choice: forward or stop)
- SWITCH: Multi-choice cell (left/forward/right)
- DONE: Goal reached
"""
from typing import Dict, List, Optional, Tuple

from flatland.core.grid.grid4_utils import get_new_position
from flatland.envs.fast_methods import fast_argmax, fast_count_nonzero
from flatland.envs.step_utils.states import TrainState


# Flatland Action constants
ACTION_DO_NOTHING = 0
ACTION_MOVE_LEFT = 1
ACTION_MOVE_FORWARD = 2
ACTION_MOVE_RIGHT = 3
ACTION_STOP_MOVING = 4

ACTION_NAMES = {
    0: "DO_NOTHING",
    1: "MOVE_LEFT",
    2: "MOVE_FORWARD",
    3: "MOVE_RIGHT",
    4: "STOP_MOVING",
}

# Direction relative offsets
# 0=North, 1=East, 2=South, 3=West
LEFT_OF = {0: 3, 1: 0, 2: 1, 3: 2}    # turning left from current heading
RIGHT_OF = {0: 1, 1: 2, 2: 3, 3: 0}   # turning right


def _get_transitions(env, row: int, col: int, direction: int):
    """
    Wrapper for Flatland's get_transitions API.
    Signature: get_transitions(configuration=((row, col), direction))
    """
    return env.rail.get_transitions(((int(row), int(col)), int(direction)))


def classify_cell_type(env, agent) -> str:
    """Klassifiziert die aktuelle Cell des Agents."""
    if agent.state == TrainState.DONE:
        return "DONE"

    if agent.position is None or not agent.state.is_on_map_state():
        return "OUTSIDE"

    transitions = _get_transitions(env, agent.position[0], agent.position[1], agent.direction)
    num_transitions = fast_count_nonzero(transitions)

    if num_transitions > 1:
        return "SWITCH"

    if num_transitions == 0:
        return "DONE"

    next_dir = fast_argmax(transitions)
    next_pos = get_new_position(agent.position, next_dir)

    if (next_pos[0] < 0 or next_pos[0] >= env.height or
            next_pos[1] < 0 or next_pos[1] >= env.width):
        return "FORWARD_ONLY"

    next_transitions = _get_transitions(env, next_pos[0], next_pos[1], next_dir)
    next_num_transitions = fast_count_nonzero(next_transitions)

    opp_dir_options = 1
    for nd in range(4):
        if nd != next_dir:
            ntrans = _get_transitions(env, next_pos[0], next_pos[1], nd)
            opp_dir_options = max(opp_dir_options, fast_count_nonzero(ntrans))

    if next_num_transitions == 1 and opp_dir_options > 1:
        return "MERGING"

    return "FORWARD_ONLY"


def classify_cell_at(env, position: Tuple[int, int], direction: int) -> str:
    """Klassifiziert eine virtuelle Position+Richtung (ohne Agent)."""
    transitions = _get_transitions(env, position[0], position[1], direction)
    num_transitions = fast_count_nonzero(transitions)

    if num_transitions == 0:
        return "DONE"
    if num_transitions > 1:
        return "SWITCH"

    next_dir = fast_argmax(transitions)
    next_pos = get_new_position(position, next_dir)

    if (next_pos[0] < 0 or next_pos[0] >= env.height or
            next_pos[1] < 0 or next_pos[1] >= env.width):
        return "FORWARD_ONLY"

    next_transitions = _get_transitions(env, next_pos[0], next_pos[1], next_dir)
    next_num_transitions = fast_count_nonzero(next_transitions)

    opp_dir_options = 1
    for nd in range(4):
        if nd != next_dir:
            ntrans = _get_transitions(env, next_pos[0], next_pos[1], nd)
            opp_dir_options = max(opp_dir_options, fast_count_nonzero(ntrans))

    if next_num_transitions == 1 and opp_dir_options > 1:
        return "MERGING"

    return "FORWARD_ONLY"


def lookahead_to_decision(env, agent, max_depth: int = 30) -> Optional[Dict]:
    """
    Laeuft virtuell vorwaerts vom Agent bis zum naechsten Decision Point.
    Returns dict with path, decision_position, cell_type, options - or None.
    """
    if agent.position is None or agent.direction is None:
        return None
    if agent.state == TrainState.DONE:
        return None

    pos = (int(agent.position[0]), int(agent.position[1]))
    direction = int(agent.direction)

    path = [list(pos)]
    visited = {(pos, direction)}

    for _ in range(max_depth):
        cell_type = classify_cell_at(env, pos, direction)

        if cell_type == "SWITCH":
            return {
                "path": path,
                "decision_position": list(pos),
                "decision_direction": direction,
                "cell_type": "SWITCH",
                "options": _build_switch_options(env, pos, direction),
            }

        if cell_type == "MERGING":
            return {
                "path": path,
                "decision_position": list(pos),
                "decision_direction": direction,
                "cell_type": "MERGING",
                "options": _build_merging_options(env, pos, direction),
            }

        if cell_type == "DONE":
            return None

        transitions = _get_transitions(env, pos[0], pos[1], direction)
        if fast_count_nonzero(transitions) == 0:
            return None

        next_dir = fast_argmax(transitions)
        next_pos = get_new_position(pos, next_dir)

        if (next_pos[0] < 0 or next_pos[0] >= env.height or
                next_pos[1] < 0 or next_pos[1] >= env.width):
            return None

        next_state = (next_pos, next_dir)
        if next_state in visited:
            return None

        visited.add(next_state)
        pos = (int(next_pos[0]), int(next_pos[1]))
        direction = int(next_dir)
        path.append(list(pos))

    return None


def _build_switch_options(env, position, direction) -> List[Dict]:
    transitions = _get_transitions(env, position[0], position[1], direction)
    options = []

    forward_dir = direction
    left_dir = LEFT_OF[direction]
    right_dir = RIGHT_OF[direction]

    if transitions[left_dir]:
        target = get_new_position(position, left_dir)
        options.append({
            "action": ACTION_MOVE_LEFT,
            "action_name": "MOVE_LEFT",
            "label": "← Left",
            "target_position": [int(target[0]), int(target[1])],
        })
    if transitions[forward_dir]:
        target = get_new_position(position, forward_dir)
        options.append({
            "action": ACTION_MOVE_FORWARD,
            "action_name": "MOVE_FORWARD",
            "label": "↑ Forward",
            "target_position": [int(target[0]), int(target[1])],
        })
    if transitions[right_dir]:
        target = get_new_position(position, right_dir)
        options.append({
            "action": ACTION_MOVE_RIGHT,
            "action_name": "MOVE_RIGHT",
            "label": "→ Right",
            "target_position": [int(target[0]), int(target[1])],
        })

    return options


def _build_merging_options(env, position, direction) -> List[Dict]:
    transitions = _get_transitions(env, position[0], position[1], direction)
    options = []

    if fast_count_nonzero(transitions) > 0:
        next_dir = fast_argmax(transitions)
        target = get_new_position(position, next_dir)
        options.append({
            "action": ACTION_MOVE_FORWARD,
            "action_name": "MOVE_FORWARD",
            "label": "↑ Forward",
            "target_position": [int(target[0]), int(target[1])],
        })

    options.append({
        "action": ACTION_STOP_MOVING,
        "action_name": "STOP_MOVING",
        "label": "■ Stop",
        "target_position": [int(position[0]), int(position[1])],
    })

    return options

def find_decision_cells(env) -> List[Dict]:
    """Liste aller Cells im Grid die SWITCH oder MERGING sind.

    For each cell:
      - kind = "switch" if it is a SWITCH (multi-choice for some heading)
        otherwise "merge" if it is MERGING (signal before a switch).
      - directions = list of integers 0=N, 1=E, 2=S, 3=W.

    For SWITCH cells, directions are the headings under which the cell
    behaves like a switch (used to orient the diamond marker on the map).

    For MERGE cells, directions are *only* those headings whose direct
    grid-neighbour cell is a SWITCH. This way the yellow signal arrow
    sits on the cell edge that touches the switch, pointing to it -
    which is the real-world semantic of a pre-switch signal.

    Merge cells without a direct switch neighbour are still classified
    as merge, but their `directions` list is empty - the frontend then
    skips drawing an arrow rather than guessing.
    """
    # First pass: classify every cell, collect SWITCH/MERGING headings.
    raw: Dict = {}
    for r in range(env.height):
        for c in range(env.width):
            switch_dirs: List[int] = []
            merge_dirs: List[int] = []
            for direction in range(4):
                try:
                    ct = classify_cell_at(env, (r, c), direction)
                except Exception:
                    continue
                if ct == "SWITCH":
                    switch_dirs.append(direction)
                elif ct == "MERGING":
                    merge_dirs.append(direction)
            if switch_dirs or merge_dirs:
                raw[(r, c)] = {"switch": switch_dirs, "merge": merge_dirs}

    # Quick lookup: which cells are switches?
    switch_cells = {pos for pos, info in raw.items() if info["switch"]}

    def _switch_exits(r: int, c: int, in_dirs: List[int]) -> List[int]:
        """Collect all rail directions in which the cell can be left,
        across every incoming direction that classifies as SWITCH.
        Returns a sorted, unique list of 0..3."""
        exits = set()
        for d in in_dirs:
            try:
                trans = _get_transitions(env, r, c, d)
            except Exception:
                continue
            for od in range(4):
                if trans[od]:
                    exits.add(int(od))
        return sorted(exits)

    # 0=N -> (-1,0), 1=E -> (0,+1), 2=S -> (+1,0), 3=W -> (0,-1)
    NEIGH = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}

    out: List[Dict] = []
    for (r, c), info in raw.items():
        if info["switch"]:
            out.append({
                "r": int(r),
                "c": int(c),
                "kind": "switch",
                "directions": [int(d) for d in info["switch"]],
                "switch_exits": _switch_exits(r, c, info["switch"]),
            })
        else:
            # MERGE: keep only directions whose immediate neighbour is a switch.
            ptr_dirs = []
            for d in info["merge"]:
                dr, dc = NEIGH[d]
                if (r + dr, c + dc) in switch_cells:
                    ptr_dirs.append(int(d))
            out.append({
                "r": int(r),
                "c": int(c),
                "kind": "merge",
                "directions": ptr_dirs,
            })
    return out

