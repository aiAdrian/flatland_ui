"""
Override API: User can set/clear per-agent action overrides.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.session_manager import session_manager
from app.core.scenario_cache import scenario_cache
from app.core.override_manager import override_manager
from app.core.notification_manager import notification_manager
from app.policies.registry import scenario_policy_factories

router = APIRouter()


class OverrideRequest(BaseModel):
    action: int  # 0=DO_NOTHING, 1=LEFT, 2=FORWARD, 3=RIGHT, 4=STOP


def _policy_factory_for(policy_id: str):
    factories = scenario_policy_factories()
    return factories.get(policy_id, factories["deadlock_avoidance"])


def _estimate_branch_kpis(env, policy_factory, overrides: dict, horizon: int) -> tuple[int, int]:
    from app.core.scenario_runner import TrajectoryBranchRunner

    runner = TrajectoryBranchRunner(env, policy_factory)
    res = runner.run_branch(overrides=overrides, max_steps=horizon)
    deadlocks = int(res.kpis.get("deadlocks", res.kpis.get("num_deadlock_cycles", 0)) or 0)
    done = int(res.success_count or 0)
    return deadlocks, done


def _branch_kpis_full(env, policy_factory, overrides: dict, horizon: int) -> dict:
    """Forward-simulate a branch and return the KPIs Co-Learning feedback
    needs: deadlocks, arrived (done), total trains, and total delay."""
    res = _branch_run(env, policy_factory, overrides, horizon)
    return _kpis_from_result(res)


def _branch_run(env, policy_factory, overrides: dict, horizon: int):
    """Run a what-if branch and return the full BranchResult (system KPIs
    + per-agent outcomes + snapshots for trajectory extraction)."""
    from app.core.scenario_runner import TrajectoryBranchRunner

    runner = TrajectoryBranchRunner(env, policy_factory)
    return runner.run_branch(overrides=overrides, max_steps=horizon)


def _kpis_from_result(res) -> dict:
    return {
        "deadlocks": int(res.kpis.get("deadlocks", res.kpis.get("num_deadlock_cycles", 0)) or 0),
        "done": int(res.success_count or 0),
        "total": int(res.total_agents or 0),
        "delay": int(res.kpis.get("total_delay", 0) or 0),
    }


def _train_outcome(res, handle: int) -> dict:
    """The overridden train's own fate on this branch: arrived / delay /
    deadlocked. Falls back to all-zero if the handle is missing."""
    o = res.agent_outcomes.get(int(handle)) or {
        "arrived": False,
        "deadlocked": False,
        "delay": 0,
    }
    return {
        "arrived": bool(o.get("arrived", False)),
        "delay": int(o.get("delay", 0) or 0),
        "deadlocked": bool(o.get("deadlocked", False)),
    }


def _branch_trajectories(res) -> dict:
    """Per-agent trajectories from a branch's snapshots, in the same shape
    scenarios use ({handle_str: [{step, row, col, ...}]}), so the map overlay
    can draw them with the existing forecast machinery."""
    from app.core.hmi_scenario_adapter import _extract_trajectories

    return _extract_trajectories(res.snapshots)


def _whatif_summary(baseline: dict, branch: dict) -> str:
    """Plain-language consequence of the human's proposed action vs. the
    current course (baseline). Mirrors the framing used in recommendations."""
    parts: list[str] = []

    d_delay = branch["delay"] - baseline["delay"]
    if d_delay < 0:
        parts.append(f"saves {abs(d_delay)} steps")
    elif d_delay > 0:
        parts.append(f"+{d_delay} steps delay")

    d_dl = branch["deadlocks"] - baseline["deadlocks"]
    if d_dl < 0:
        parts.append(f"avoids {abs(d_dl)} deadlock(s)")
    elif d_dl > 0:
        parts.append(f"risks {d_dl} deadlock(s)")

    d_done = branch["done"] - baseline["done"]
    if d_done > 0:
        parts.append(f"{d_done} more train(s) arrive")
    elif d_done < 0:
        parts.append(f"{abs(d_done)} fewer train(s) arrive")

    return " · ".join(parts) if parts else "no measurable change vs. current course"


@router.post("/{session_id}/agent/{handle}/override")
def set_override(session_id: str, handle: int, req: OverrideRequest):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    if handle < 0 or handle >= len(session.env.agents):
        raise HTTPException(404, f"Agent {handle} not found")

    if req.action not in (0, 1, 2, 3, 4):
        raise HTTPException(400, f"Invalid action {req.action}")

    # Keep current overrides for before/after impact estimate.
    before_overrides = dict(override_manager.get_all(session_id))
    scenario_cache.clear_session(session_id)
    override_manager.set(session_id, handle, req.action)

    # Estimate impact of the new override from the current env state.
    # If deadlocks increase or done-count drops, emit a warning notification.
    try:
        env = session.env
        elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
        max_ep = int(getattr(env, "_max_episode_steps", 0) or 0)
        horizon = min(max(50, max_ep - elapsed) if max_ep else 200, 250)
        policy_id = getattr(session, "policy", None) or "deadlock_avoidance"
        policy_factory = _policy_factory_for(policy_id)

        before_deadlocks, before_done = _estimate_branch_kpis(env, policy_factory, before_overrides, horizon)
        after_overrides = dict(override_manager.get_all(session_id))
        after_deadlocks, after_done = _estimate_branch_kpis(env, policy_factory, after_overrides, horizon)

        if after_deadlocks > before_deadlocks:
            notification_manager.add(
                session_id,
                kind="warning",
                title="Override risk increase",
                message=(
                    f"Train {handle}: deadlocks may increase "
                    f"({before_deadlocks} -> {after_deadlocks})."
                ),
                timestamp=elapsed,
                related_kind="train",
                related_id=str(handle),
                ttl_steps=40,
            )

        if after_done < before_done:
            notification_manager.add(
                session_id,
                kind="warning",
                title="Override reduces arrivals",
                message=(
                    f"Train {handle}: fewer agents may finish "
                    f"({before_done} -> {after_done})."
                ),
                timestamp=elapsed,
                related_kind="train",
                related_id=str(handle),
                ttl_steps=40,
            )
    except Exception:
        # Best-effort only; override setting must never fail due to alert logic.
        pass

    return {
        "session_id": session_id,
        "handle": handle,
        "action": req.action,
    }


class WhatIfRequest(BaseModel):
    """A hypothetical proposal: handle → action int. Not committed."""
    overrides: dict[int, int]


@router.post("/{session_id}/what-if-override")
def what_if_override(session_id: str, req: WhatIfRequest):
    """Read-only Co-Learning feedback: forward-simulate the human's PROPOSED
    action(s) against the current course (committed overrides) and return the
    KPI delta + a plain-language consequence — without committing anything.

    This is the reciprocal half of co-learning: the human proposes, the AI
    gives feedback on the proposal before it is applied."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    env = session.env
    n = len(env.agents)
    for h, a in req.overrides.items():
        if h < 0 or h >= n:
            raise HTTPException(404, f"Agent {h} not found")
        if a not in (0, 1, 2, 3, 4):
            raise HTTPException(400, f"Invalid action {a}")

    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    max_ep = int(getattr(env, "_max_episode_steps", 0) or 0)
    horizon = min(max(50, max_ep - elapsed) if max_ep else 200, 250)
    policy_id = getattr(session, "policy", None) or "deadlock_avoidance"
    policy_factory = _policy_factory_for(policy_id)

    # Baseline = current course (already-committed overrides). Branch = baseline
    # plus the proposed override(s), which win on conflicting handles.
    baseline_overrides = dict(override_manager.get_all(session_id))
    branch_overrides = dict(baseline_overrides)
    branch_overrides.update({int(h): int(a) for h, a in req.overrides.items()})

    baseline_res = _branch_run(env, policy_factory, baseline_overrides, horizon)
    branch_res = _branch_run(env, policy_factory, branch_overrides, horizon)

    baseline = _kpis_from_result(baseline_res)
    branch = _kpis_from_result(branch_res)

    # Per-train outcome for the operator's selected handle (the first override
    # key — the UI sends exactly one). Primary content; system KPIs above are
    # the secondary "local action → global effect" context.
    affected_handles = [int(h) for h in req.overrides.keys()]
    train = None
    if affected_handles:
        h = affected_handles[0]
        train = {
            "handle": h,
            "baseline": _train_outcome(baseline_res, h),
            "branch": _train_outcome(branch_res, h),
        }

    # Per-agent trajectories for BOTH branches (baseline = AI, branch = human),
    # in scenario shape so the map overlay draws them with the forecast code.
    baseline_traj = _branch_trajectories(baseline_res)
    branch_traj = _branch_trajectories(branch_res)

    return {
        "horizon": horizon,
        "baseline": baseline,
        "branch": branch,
        "delta": {
            "delay": branch["delay"] - baseline["delay"],
            "deadlocks": branch["deadlocks"] - baseline["deadlocks"],
            "done": branch["done"] - baseline["done"],
        },
        "summary": _whatif_summary(baseline, branch),
        "train": train,
        "baseline_trajectories": baseline_traj,
        "branch_trajectories": branch_traj,
        "handles": affected_handles,
    }


@router.delete("/{session_id}/agent/{handle}/override")
def clear_override(session_id: str, handle: int):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    scenario_cache.clear_session(session_id); override_manager.clear(session_id, handle)
    return {"session_id": session_id, "handle": handle, "cleared": True}


@router.get("/{session_id}/overrides")
def get_overrides(session_id: str):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    return {
        "session_id": session_id,
        "overrides": override_manager.get_all(session_id),
    }
