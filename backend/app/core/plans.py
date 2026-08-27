"""Premade plans: the exact route and timing of every train.

A **plan** answers "which cell is each train in at which step", which neither
of the two things next to it answers:

- the *scene* says what the network looks like and where each train starts and
  ends (`infrastructure_scene_adapter`),
- the *timetable* Flatland derives from it says only "leave no earlier than X,
  arrive no later than Y" (`waypoints_earliest_departure` / `_latest_arrival`),
- the plan says the whole run, cell by cell.

The format is Flatland's own `Trainrun` vocabulary
(`flatland.envs.rail_trainrun_data_structures`), inherited from the crowdAI
train-schedule-optimisation challenge: a train run is a list of
`TrainrunWaypoint(scheduled_at, Waypoint(position, direction))`, one entry per
**cell entry**. Cell-based rather than graph-node-based on purpose — node ids
shift whenever the infrastructure changes, cells do not, so a plan file stays
readable and diffable.

On disk (``*.plan.json``)::

    {
      "id": "pf-ch-wn-wal-conflict.plan.v1",
      "scenario": "pf-ch-wn-wal-conflict",
      "generated_by": "deadlock_avoidance",
      "trainruns": {
        "0": [{"scheduled_at": 6, "position": [3, 12], "direction": 1}, ...]
      }
    }

`PlanPolicy` drives it; see `app/policies/plan_policy.py` for why replay is by
position and not by clock.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from flatland.envs.rail_trainrun_data_structures import (
    Trainrun,
    TrainrunDict,
    TrainrunWaypoint,
    Waypoint,
)

# Flatland convention: 0=N, 1=E, 2=S, 3=W.
_DIR_DELTA = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}


class PlanError(ValueError):
    """A plan file is malformed or internally inconsistent."""


def _neighbours(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    return (b[0] - a[0], b[1] - a[1]) in _DIR_DELTA.values()


def parse_plan(payload: Mapping[str, Any]) -> TrainrunDict:
    """`{handle: Trainrun}` from a decoded plan file. Raises `PlanError`."""
    runs = payload.get("trainruns")
    if not isinstance(runs, Mapping) or not runs:
        raise PlanError("plan has no 'trainruns'")

    trainruns: TrainrunDict = {}
    for raw_handle, raw_run in runs.items():
        try:
            handle = int(raw_handle)
        except (TypeError, ValueError):
            raise PlanError(f"trainrun key {raw_handle!r} is not a handle")
        if not isinstance(raw_run, Sequence) or not raw_run:
            raise PlanError(f"train {handle} has an empty trainrun")

        run: Trainrun = []
        for entry in raw_run:
            if not isinstance(entry, Mapping):
                raise PlanError(f"train {handle}: waypoint is not an object")
            try:
                position = (int(entry["position"][0]), int(entry["position"][1]))
                waypoint = TrainrunWaypoint(
                    scheduled_at=int(entry["scheduled_at"]),
                    waypoint=Waypoint(position, int(entry["direction"])),
                )
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise PlanError(f"train {handle}: bad waypoint {entry!r} ({exc})")
            run.append(waypoint)
        trainruns[handle] = run
    return trainruns


def validate_plan(trainruns: TrainrunDict) -> None:
    """Reject a plan that cannot be executed. Raises `PlanError`.

    Three properties, each of which would otherwise surface as a train
    silently dropping off its plan mid-run, which is far harder to diagnose
    than a rejected file:

    - time moves forward within a run;
    - consecutive waypoints are grid neighbours, so the route is contiguous
      on the rails (a reversal stays in its cell and only flips direction);
    - no two trains claim the same cell at the same step.
    """
    for handle, run in trainruns.items():
        previous = None
        for waypoint in run:
            if previous is not None:
                if waypoint.scheduled_at <= previous.scheduled_at:
                    raise PlanError(
                        f"train {handle}: time does not advance at "
                        f"{waypoint.waypoint.position} "
                        f"({previous.scheduled_at} -> {waypoint.scheduled_at})"
                    )
                here = waypoint.waypoint.position
                there = previous.waypoint.position
                if here != there and not _neighbours(there, here):
                    raise PlanError(
                        f"train {handle}: {there} and {here} are not neighbours"
                    )
            previous = waypoint

    claimed: Dict[Tuple[Tuple[int, int], int], int] = {}
    for handle, run in trainruns.items():
        for waypoint in run:
            key = (waypoint.waypoint.position, waypoint.scheduled_at)
            other = claimed.get(key)
            if other is not None:
                raise PlanError(
                    f"trains {other} and {handle} both occupy "
                    f"{key[0]} at step {key[1]}"
                )
            claimed[key] = handle


def load_plan(path: str | Path) -> TrainrunDict:
    """Read, parse and validate a plan file."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    trainruns = parse_plan(payload)
    validate_plan(trainruns)
    return trainruns


def plan_to_dict(
    trainruns: TrainrunDict,
    *,
    plan_id: str,
    scenario: str | None = None,
    generated_by: str | None = None,
) -> Dict[str, Any]:
    """Serialisable plan file body — the inverse of `parse_plan`."""
    return {
        "id": plan_id,
        "scenario": scenario,
        "generated_by": generated_by,
        "trainruns": {
            str(handle): [
                {
                    "scheduled_at": int(w.scheduled_at),
                    "position": [int(w.waypoint.position[0]), int(w.waypoint.position[1])],
                    "direction": int(w.waypoint.direction),
                }
                for w in run
            ]
            for handle, run in sorted(trainruns.items())
        },
    }


def trainruns_from_marey_history(snapshots: Iterable[Mapping[str, Any]]) -> TrainrunDict:
    """Turn recorded per-step positions into plans — one entry per cell entry.

    `session.marey_history_snapshots` already holds `{step, agents: {h: {pos,
    dir}}}` for every executed step, so recording a run under any policy is
    the cheapest way to obtain a plan that is feasible by construction. A
    train standing still for several steps produced several identical
    snapshots; only the first is a cell *entry*, so the rest are dropped —
    otherwise a slow or waiting train would encode its dwell twice, once here
    and once in the speed counter.
    """
    trainruns: Dict[int, List[TrainrunWaypoint]] = {}
    last: Dict[int, Tuple[Tuple[int, int], int]] = {}

    for snapshot in sorted(snapshots, key=lambda s: int(s.get("step", 0))):
        step = int(snapshot.get("step", 0))
        for raw_handle, agent in (snapshot.get("agents") or {}).items():
            handle = int(raw_handle)
            position = agent.get("pos")
            direction = agent.get("dir")
            if position is None or direction is None:
                continue
            key = ((int(position[0]), int(position[1])), int(direction))
            if last.get(handle) == key:
                continue
            last[handle] = key
            trainruns.setdefault(handle, []).append(
                TrainrunWaypoint(scheduled_at=step, waypoint=Waypoint(key[0], key[1]))
            )
    return trainruns


__all__ = [
    "PlanError",
    "load_plan",
    "parse_plan",
    "plan_to_dict",
    "trainruns_from_marey_history",
    "validate_plan",
]
