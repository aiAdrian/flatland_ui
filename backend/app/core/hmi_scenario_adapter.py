"""Adapter: ScenarioBuilder.Scenario → app.models.hmi.ScenarioOption."""
from __future__ import annotations

from typing import List, Optional

from app.core.scenario_builder import Scenario
from app.core.scenario_runner import BranchResult
from app.models.hmi import KpiDelta, ScenarioKpis, ScenarioOption


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
        deadlocks=int(res.kpis.get("num_deadlock_cycles", 0)),
        done=n_done,
        meanDelay=mean_delay,
    )


def _deltas(cand: ScenarioKpis, base: ScenarioKpis) -> ScenarioKpis:
    return ScenarioKpis(
        totalDelay=cand.totalDelay - base.totalDelay,
        deadlocks=cand.deadlocks - base.deadlocks,
        done=cand.done - base.done,
        meanDelay=round(cand.meanDelay - base.meanDelay, 1),
    )


def _describe(kpis: ScenarioKpis, deltas: Optional[ScenarioKpis]) -> str:
    base = f"done={kpis.done} · deadlocks={kpis.deadlocks} · delay={kpis.totalDelay} (mean {kpis.meanDelay})"
    if deltas is None:
        return f"Current policy: {base}"
    parts = []
    if deltas.done != 0:
        parts.append(f"Δdone={deltas.done:+d}")
    if deltas.deadlocks != 0:
        parts.append(f"Δdeadlocks={deltas.deadlocks:+d}")
    if deltas.totalDelay != 0:
        parts.append(f"Δdelay={deltas.totalDelay:+d}")
    head = " · ".join(parts) if parts else "≈ baseline"
    return f"{head}  |  {base}"


def scenarios_to_options(scenarios: List[Scenario]) -> List[ScenarioOption]:
    baseline_scenario = next((s for s in scenarios if s.name == "baseline"), None)
    base_kpis = _kpis_from(baseline_scenario.result) if baseline_scenario else None

    out: List[ScenarioOption] = []
    for s in scenarios:
        kpis = _kpis_from(s.result)
        is_baseline = (s.name == "baseline")
        deltas = None if is_baseline or base_kpis is None else _deltas(kpis, base_kpis)
        out.append(ScenarioOption(
            id=f"scn_{s.policy_id}",
            title=_label_for(s),
            description=_describe(kpis, deltas),
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
