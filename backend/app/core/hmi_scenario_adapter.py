"""Adapter: ScenarioBuilder.Scenario → app.models.hmi.ScenarioOption."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.scenario_builder import Scenario
from app.core.scenario_runner import BranchResult
from app.models.hmi import KpiDelta, ScenarioKpis, ScenarioOption, TrajectoryPoint
from app.core.marey_topology import classify_marey_point
from app.core.tile_resolver import resolve_tile


POLICY_LABELS = {
    "deadlock_avoidance": "DLA (Deadlock Avoidance)",
    "shortest_path": "Shortest Path",
    "forward_only": "Forward Only",
    "do_nothing": "Do Nothing",
    "random": "Random",
}


def _label_for(s: Scenario) -> str:
    base = POLICY_LABELS.get(s.policy_id, s.policy_id)
    return f"{base} (current)" if s.name == "baseline" else base


def _kpis_from(res: BranchResult) -> ScenarioKpis:
    n_done = int(res.success_count)
    total_delay = int(res.kpis.get("total_delay", 0))
    mean_delay = round(total_delay / n_done, 1) if n_done > 0 else 0.0
    return ScenarioKpis(
        totalDelay=total_delay,
        deadlocks=int(res.kpis.get("deadlocks", res.kpis.get("num_deadlock_cycles", 0))),
        done=n_done,
        meanDelay=mean_delay,
        episodeSteps=int(getattr(res, "elapsed_steps", 0)),
        episodeFinished=bool(getattr(res, "finished", False)),
    )


def _deltas(cand: ScenarioKpis, base: ScenarioKpis) -> ScenarioKpis:
    return ScenarioKpis(
        totalDelay=cand.totalDelay - base.totalDelay,
        deadlocks=cand.deadlocks - base.deadlocks,
        done=cand.done - base.done,
        meanDelay=round(cand.meanDelay - base.meanDelay, 1),
    )


def _describe(
    kpis: ScenarioKpis,
    deltas: Optional[ScenarioKpis],
    total_agents: int,
    is_baseline: bool,
) -> str:
    """Plain-language outcome summary; the small KPI grid in the UI
    carries the numeric details, this is the headline."""
    n_done = kpis.done
    n_dl = kpis.deadlocks

    # ── Baseline (current policy) ───────────────────────────────
    if is_baseline:
        if n_dl > 0:
            return f"⚠ {n_dl} train(s) end up in deadlock"
        if n_done == total_agents:
            return f"✓ All {total_agents} trains will arrive"
        if n_done == 0:
            return f"✗ No trains arrive within horizon"
        return f"⚠ Only {n_done} of {total_agents} trains arrive"

    # ── Alternative policy (deltas vs baseline) ─────────────────
    assert deltas is not None  # always set for non-baseline
    d_done = deltas.done
    d_dl = deltas.deadlocks
    d_delay = deltas.totalDelay

    # Worst signal first: deadlocks introduced
    if d_dl > 0:
        return f"⚠ {d_dl} more train(s) in deadlock"

    # Catastrophic loss of arrivals
    if n_done == 0 and d_done < 0:
        return f"✗ {abs(d_done)} train(s) would not arrive"

    # Strict improvement
    if d_done > 0:
        return f"✓ {d_done} more train(s) would arrive"

    # Strict regression
    if d_done < 0:
        return f"⚠ {abs(d_done)} fewer train(s) would arrive"

    # Same arrivals — look at delay
    if d_delay < -20:
        return f"✓ Saves {abs(d_delay)} steps of delay"
    if d_delay > 20:
        return f"⚠ Adds {d_delay} steps of delay"

    return "≈ Same outcome as current policy"


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _taken_out_dir(current_point: dict, next_point: Optional[dict]) -> Optional[int]:
    """Derive the actually taken outgoing direction from consecutive positions.

    Flatland direction convention:
      0=N, 1=E, 2=S, 3=W
    """
    if next_point is None:
        return None

    try:
        r0 = int(current_point["row"])
        c0 = int(current_point["col"])
        r1 = int(next_point["row"])
        c1 = int(next_point["col"])
    except (KeyError, TypeError, ValueError):
        return None

    dr = r1 - r0
    dc = c1 - c0

    if dr == -1 and dc == 0:
        return 0
    if dr == 0 and dc == 1:
        return 1
    if dr == 1 and dc == 0:
        return 2
    if dr == 0 and dc == -1:
        return 3

    # Non-adjacent or waiting/duplicate point: no reliable outgoing direction.
    return None


def _marey_svg_for_cell(env: Any, row: int, col: int) -> Optional[str]:
    """Resolve SVG filename for a rail cell, matching map tile serialization."""
    if env is None:
        return None

    try:
        value = int(env.rail.grid[int(row), int(col)])
    except Exception:
        return None

    if value == 0:
        return None

    try:
        resolved = resolve_tile(value)
    except Exception:
        return None

    if resolved is None:
        # Keep same fallback as build_rail_tiles() / /hmi/marey-data.
        return "Gleis_horizontal.svg"

    svg, _rot = resolved
    return svg


def _marey_error_metadata(
    *,
    row: int,
    col: int,
    direction: int,
    step: Optional[int],
    handle: Optional[int],
    marey_svg: Optional[str],
    exc: Exception,
) -> dict:
    """Backward-compatible fallback if topology enrichment hits an edge case."""
    return {
        "marey_topology": "unknown",
        "marey_svg": marey_svg,
        "marey_debug": {
            "pos": [int(row), int(col)],
            "dir": int(direction),
            "step": _safe_int(step),
            "handle": _safe_int(handle),
            "transition_bits": None,
            "possible_out_dirs": [],
            "possible_transitions": [],
            "backward_transitions": {},
            "possible_in_dirs_for_out": {},
            "classification_reason": (
                f"topology enrichment failed: {type(exc).__name__}: {exc}"
            ),
        },
        "marey_switch": None,
        "marey_merge": None,
    }


def _extract_trajectories(snapshots, env: Optional[Any] = None):
    """Snapshots → {handle_str: [TrajectoryPoint, ...]}.

    Off-map agents (pos is None) are skipped per step.

    If env is provided, each point is enriched with backend-derived Marey
    topology metadata:
      - marey_topology
      - marey_svg
      - marey_debug
      - marey_switch
      - marey_merge
    """
    raw: Dict[str, List[dict]] = {}

    # First pass: collect raw per-agent points in chronological order.
    for snap in snapshots:
        step = int(snap.get("step", 0))
        agents = snap.get("agents") or {}

        # Snapshot agents may be dict {handle: {...}} or list of dicts.
        if isinstance(agents, dict):
            iterator = agents.items()
        else:
            iterator = ((str(i), a) for i, a in enumerate(agents))

        for handle, info in iterator:
            pos = info.get("pos") if isinstance(info, dict) else None
            d = info.get("dir") if isinstance(info, dict) else None

            if pos is None or d is None:
                continue

            try:
                row, col = int(pos[0]), int(pos[1])
                dir_i = int(d)
            except (TypeError, ValueError, IndexError):
                continue

            handle_str = str(handle)
            handle_i = _safe_int(handle)

            raw.setdefault(handle_str, []).append(
                {
                    "step": step,
                    "row": row,
                    "col": col,
                    "dir": dir_i,
                    "handle": handle_i,
                    "agent_id": handle_i,
                }
            )

    # Second pass: enrich each point, using the next point to derive
    # the actually taken outgoing direction.
    out: Dict[str, List[TrajectoryPoint]] = {}

    for handle_str, points in raw.items():
        handle_i = _safe_int(handle_str)
        enriched: List[TrajectoryPoint] = []

        for idx, point in enumerate(points):
            next_point = points[idx + 1] if idx + 1 < len(points) else None

            row_i = int(point["row"])
            col_i = int(point["col"])
            dir_i = int(point["dir"])
            step_i = int(point["step"])

            data = dict(point)
            data["handle"] = handle_i
            data["agent_id"] = handle_i

            if env is not None:
                marey_svg = _marey_svg_for_cell(env, row_i, col_i)
                taken_out_dir = _taken_out_dir(point, next_point)

                try:
                    data.update(
                        classify_marey_point(
                            env,
                            row_i,
                            col_i,
                            dir_i,
                            step=step_i,
                            handle=handle_i,
                            taken_out_dir=taken_out_dir,
                            marey_svg=marey_svg,
                        )
                    )
                except Exception as exc:
                    data.update(
                        _marey_error_metadata(
                            row=row_i,
                            col=col_i,
                            direction=dir_i,
                            step=step_i,
                            handle=handle_i,
                            marey_svg=marey_svg,
                            exc=exc,
                        )
                    )

            enriched.append(TrajectoryPoint(**data))

        out[handle_str] = enriched

    return out


def scenarios_to_options(scenarios: List[Scenario], env: Optional[Any] = None) -> List[ScenarioOption]:
    baseline_scenario = next((s for s in scenarios if s.name == "baseline"), None)
    base_kpis = _kpis_from(baseline_scenario.result) if baseline_scenario else None

    out: List[ScenarioOption] = []
    for s in scenarios:
        kpis = _kpis_from(s.result)
        is_baseline = (s.name == "baseline")
        deltas = None if is_baseline or base_kpis is None else _deltas(kpis, base_kpis)
        out.append(ScenarioOption(
            trajectories=_extract_trajectories(s.result.snapshots, env=env),
            id=f"scn_{s.policy_id}",
            title=_label_for(s),
            description=_describe(kpis, deltas, s.result.total_agents, is_baseline),
            kpiDelta=KpiDelta(
                time=kpis.totalDelay,
                energy=kpis.deadlocks,
            ),
            kpis=kpis,
            kpiDeltas=deltas,
            isBaseline=is_baseline,
            isRecommended=(s.tag == "recommended"),
            score=round(s.score, 3),
            tag=s.tag,
        ))
    return out
