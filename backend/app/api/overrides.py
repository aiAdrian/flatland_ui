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
