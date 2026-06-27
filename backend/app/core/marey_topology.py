from __future__ import annotations

"""
Marey topology classification helpers.

This module enriches trajectory points with deterministic topology/debug
metadata derived from Flatland rail transitions.

It deliberately contains no UI assumptions and no frontend heuristics.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple


DIRS = (0, 1, 2, 3)

# Flatland convention:
# 0 = North, 1 = East, 2 = South, 3 = West
DIR_TO_DELTA = {
    0: (-1, 0),
    1: (0, 1),
    2: (1, 0),
    3: (0, -1),
}


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _in_bounds(env: Any, row: int, col: int) -> bool:
    height = getattr(env, "height", None)
    width = getattr(env, "width", None)
    if height is None or width is None:
        return True
    return 0 <= int(row) < int(height) and 0 <= int(col) < int(width)


def _new_position(row: int, col: int, direction: int) -> Tuple[int, int]:
    dr, dc = DIR_TO_DELTA[int(direction)]
    return int(row) + dr, int(col) + dc


def _get_transitions(env: Any, row: int, col: int, direction: int) -> List[int]:
    """
    Flatland transition wrapper.

    Returns a four-entry list where index = outgoing direction and value is
    truthy if the transition is possible for the given incoming/current
    direction.
    """
    try:
        transitions = env.rail.get_transitions(((int(row), int(col)), int(direction)))
    except TypeError:
        # Some Flatland versions expose the older signature.
        transitions = env.rail.get_transitions(int(row), int(col), int(direction))

    return [int(bool(transitions[d])) for d in DIRS]


def _get_raw_transition_value(env: Any, row: int, col: int) -> Optional[int]:
    """
    Best-effort raw transition value for debug output.

    Flatland versions differ slightly. Prefer get_full_transitions if present,
    otherwise fall back to env.rail.grid[row, col].
    """
    rail = getattr(env, "rail", None)
    if rail is None:
        return None

    getter = getattr(rail, "get_full_transitions", None)
    if callable(getter):
        for args in ((int(row), int(col)), ((int(row), int(col)),)):
            try:
                return int(getter(*args))
            except TypeError:
                continue
            except Exception:
                break

    grid = getattr(rail, "grid", None)
    if grid is not None:
        try:
            return int(grid[int(row), int(col)])
        except Exception:
            return None

    return None


def _all_possible_transitions(env: Any, row: int, col: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for in_dir in DIRS:
        transitions = _get_transitions(env, row, col, in_dir)
        for out_dir in DIRS:
            if transitions[out_dir]:
                nr, nc = _new_position(row, col, out_dir)
                out.append(
                    {
                        "in_dir": int(in_dir),
                        "out_dir": int(out_dir),
                        "to": [int(nr), int(nc)],
                    }
                )
    return out


def _group_in_dirs_by_out_dir(possible_transitions: Iterable[Dict[str, Any]]) -> Dict[str, List[int]]:
    grouped: Dict[str, set[int]] = {}
    for transition in possible_transitions:
        out_dir = _safe_int(transition.get("out_dir"))
        in_dir = _safe_int(transition.get("in_dir"))
        if out_dir is None or in_dir is None:
            continue
        grouped.setdefault(str(out_dir), set()).add(int(in_dir))
    return {k: sorted(int(v) for v in values) for k, values in sorted(grouped.items(), key=lambda item: int(item[0]))}


def _group_out_dirs_by_in_dir(possible_transitions: Iterable[Dict[str, Any]]) -> Dict[str, List[int]]:
    grouped: Dict[str, set[int]] = {}
    for transition in possible_transitions:
        out_dir = _safe_int(transition.get("out_dir"))
        in_dir = _safe_int(transition.get("in_dir"))
        if out_dir is None or in_dir is None:
            continue
        grouped.setdefault(str(in_dir), set()).add(int(out_dir))
    return {k: sorted(int(v) for v in values) for k, values in sorted(grouped.items(), key=lambda item: int(item[0]))}


def _classify_topology(
    possible_out_dirs: List[int],
    possible_in_dirs_for_out: Dict[str, List[int]],
    possible_transitions: List[Dict[str, Any]],
    taken_out_dir: Optional[int],
) -> Tuple[str, str, bool, bool]:
    """
    Returns:
      topology, reason, is_switch, is_merge

    Definitions:
      switch: current incoming/current direction has multiple possible exits.
      merge: multiple incoming directions can lead to the selected/single exit.
      switch_merge: both.
      straight: exactly one exit for current direction and no merge.
      diamond: several inputs and several outputs exist in the cell, but the
               current direction is not a concrete switch/merge case.
      unknown: no usable transition for the current direction.
    """
    unique_inputs = sorted({int(t["in_dir"]) for t in possible_transitions if "in_dir" in t})
    unique_outputs = sorted({int(t["out_dir"]) for t in possible_transitions if "out_dir" in t})

    if not possible_out_dirs:
        return "unknown", "no outgoing transition for current direction", False, False

    is_switch = len(possible_out_dirs) > 1

    selected_out = taken_out_dir
    if selected_out is None and len(possible_out_dirs) == 1:
        selected_out = possible_out_dirs[0]

    merge_inputs: List[int] = []
    if selected_out is not None:
        merge_inputs = possible_in_dirs_for_out.get(str(int(selected_out)), [])

    is_merge = len(merge_inputs) > 1

    if is_switch and is_merge:
        return (
            "switch_merge",
            "multiple possible exits for current direction and multiple inputs for selected exit",
            True,
            True,
        )

    if is_switch:
        return "switch", "multiple possible exits for current direction", True, False

    if is_merge:
        return "merge", "multiple incoming directions can use the selected exit", False, True

    # A cell with a broader crossing-like transition structure, even if the
    # current direction itself has only one exit.
    if len(unique_inputs) >= 2 and len(unique_outputs) >= 2 and len(possible_transitions) >= 4:
        return "diamond", "multiple inputs and outputs in cell transition matrix", False, False

    if len(possible_out_dirs) == 1:
        return "straight", "single outgoing direction for current direction", False, False

    return "unknown", "unclassified transition pattern", False, False


def classify_marey_point(
    env: Any,
    row: int,
    col: int,
    direction: int,
    *,
    step: Optional[int] = None,
    handle: Optional[int] = None,
    taken_out_dir: Optional[int] = None,
    marey_svg: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build Marey topology/debug metadata for one trajectory point.

    The return value can be merged into a TrajectoryPoint or JSON dict.
    """
    row_i = int(row)
    col_i = int(col)
    dir_i = int(direction)

    if not _in_bounds(env, row_i, col_i):
        debug = {
            "pos": [row_i, col_i],
            "dir": dir_i,
            "step": _safe_int(step),
            "handle": _safe_int(handle),
            "transition_bits": None,
            "possible_out_dirs": [],
            "possible_transitions": [],
            "backward_transitions": {},
            "possible_in_dirs_for_out": {},
            "classification_reason": "position outside environment bounds",
        }
        return {
            "marey_topology": "unknown",
            "marey_svg": marey_svg,
            "marey_debug": debug,
            "marey_switch": None,
            "marey_merge": None,
        }

    possible_out_dirs = [
        int(out_dir)
        for out_dir, allowed in enumerate(_get_transitions(env, row_i, col_i, dir_i))
        if allowed
    ]

    possible_transitions = _all_possible_transitions(env, row_i, col_i)
    possible_in_dirs_for_out = _group_in_dirs_by_out_dir(possible_transitions)
    backward_transitions = _group_out_dirs_by_in_dir(possible_transitions)

    taken_i = _safe_int(taken_out_dir)
    if taken_i is None and len(possible_out_dirs) == 1:
        taken_i = possible_out_dirs[0]

    topology, reason, is_switch, is_merge = _classify_topology(
        possible_out_dirs=possible_out_dirs,
        possible_in_dirs_for_out=possible_in_dirs_for_out,
        possible_transitions=possible_transitions,
        taken_out_dir=taken_i,
    )

    transition_bits = _get_raw_transition_value(env, row_i, col_i)

    debug: Dict[str, Any] = {
        "pos": [row_i, col_i],
        "dir": dir_i,
        "step": _safe_int(step),
        "handle": _safe_int(handle),
        "transition_bits": transition_bits,
        "possible_out_dirs": possible_out_dirs,
        "possible_transitions": possible_transitions,
        "backward_transitions": backward_transitions,
        "possible_in_dirs_for_out": possible_in_dirs_for_out,
        "classification_reason": reason,
    }

    marey_switch = None
    if is_switch:
        not_taken = [
            int(out_dir)
            for out_dir in possible_out_dirs
            if taken_i is None or int(out_dir) != int(taken_i)
        ]
        marey_switch = {
            "taken": taken_i,
            "not_taken": not_taken,
            "possible_exits": possible_out_dirs,
        }

    marey_merge = None
    if is_merge:
        selected_out = taken_i
        inputs = possible_in_dirs_for_out.get(str(int(selected_out)), []) if selected_out is not None else []
        marey_merge = {
            "arrived_from": dir_i,
            "other_inputs": [int(in_dir) for in_dir in inputs if int(in_dir) != dir_i],
            "possible_inputs": inputs,
        }

    return {
        "marey_topology": topology,
        "marey_svg": marey_svg,
        "marey_debug": debug,
        "marey_switch": marey_switch,
        "marey_merge": marey_merge,
    }


__all__ = [
    "classify_marey_point",
]
