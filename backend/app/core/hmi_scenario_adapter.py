"""Adapter: ScenarioBuilder.Scenario → app.models.hmi.ScenarioOption."""
from __future__ import annotations

from typing import List, Optional

from app.core.scenario_builder import Scenario
from app.core.scenario_runner import BranchResult
from app.models.hmi import KpiDelta, ScenarioKpis, ScenarioOption, TrajectoryPoint


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
            return f"⚠ {n_dl} train(s) end up stuck in deadlock"
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
        return f"⚠ Would leave {d_dl} more train(s) stuck in deadlock"

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


def _extract_trajectories(snapshots):
    """Snapshots → {handle_str: [TrajectoryPoint, ...]}.

    Off-map agents (pos is None) are skipped per step.
    """
    out: dict = {}
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
            d   = info.get("dir") if isinstance(info, dict) else None
            if pos is None or d is None:
                continue
            try:
                row, col = int(pos[0]), int(pos[1])
            except (TypeError, ValueError, IndexError):
                continue
            out.setdefault(str(handle), []).append(
                TrajectoryPoint(step=step, row=row, col=col, dir=int(d))
            )
    return out


def scenarios_to_options(scenarios: List[Scenario]) -> List[ScenarioOption]:
    baseline_scenario = next((s for s in scenarios if s.name == "baseline"), None)
    base_kpis = _kpis_from(baseline_scenario.result) if baseline_scenario else None

    out: List[ScenarioOption] = []
    for s in scenarios:
        kpis = _kpis_from(s.result)
        is_baseline = (s.name == "baseline")
        deltas = None if is_baseline or base_kpis is None else _deltas(kpis, base_kpis)
        out.append(ScenarioOption(
            trajectories=_extract_trajectories(s.result.snapshots),
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
