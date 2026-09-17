"""
Override API: User can set/clear per-agent action overrides.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.session_manager import session_manager
from app.core.scenario_cache import scenario_cache
from app.core.override_manager import override_manager
from app.core.notification_manager import notification_manager
from app.planners.replan import replan_from_state, replan_orders
from app.policies.plan_policy import (
    PlanPolicy,
    install_trainrun_plan,
    plan_branch_factory,
    planned_arrival_steps,
)
from app.policies.registry import PLAN_POLICY_ID, scenario_policy_factories

router = APIRouter()


class OverrideRequest(BaseModel):
    action: int  # 0=DO_NOTHING, 1=LEFT, 2=FORWARD, 3=RIGHT, 4=STOP


def _policy_factory_for(policy_id: str):
    factories = scenario_policy_factories()
    return factories.get(policy_id, factories["deadlock_avoidance"])


def _policy_factory_for_session(session):
    """The factory that reproduces what actually drives this session.

    A Director-driven session's what-if branches roll out the committed
    Director plan (model-free replay), and a plan-driven session's branches
    follow its scenario plan — never a proxy policy. Fallback to the scenario
    policies only when no such plan exists, and for ordinary sessions."""
    policy_id = getattr(session, "policy", None) or "deadlock_avoidance"
    if policy_id == "goal_directed":
        from app.policies.goal_directed_policy import director_replay_factory

        factory = director_replay_factory(session.env)
        if factory is not None:
            return factory
    if policy_id == PLAN_POLICY_ID:
        factory = plan_branch_factory(session.env)
        if factory is not None:
            return factory
    return _policy_factory_for(policy_id)


def _baseline_source(session) -> str:
    """What the what-if baseline follows, so the HMI can name it honestly:
    the scenario plan, a committed Director plan, or a dispatching policy."""
    policy_id = getattr(session, "policy", None)
    if policy_id == PLAN_POLICY_ID and plan_branch_factory(session.env) is not None:
        return "plan"
    if policy_id == "goal_directed":
        from app.policies.goal_directed_policy import director_replay_factory

        if director_replay_factory(session.env) is not None:
            return "director"
    return "policy"


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


def _branch_run(env, policy_factory, overrides: dict, horizon: int, release_at: dict | None = None):
    """Run a what-if branch and return the full BranchResult (system KPIs
    + per-agent outcomes + snapshots for trajectory extraction)."""
    from app.core.scenario_runner import TrajectoryBranchRunner

    runner = TrajectoryBranchRunner(env, policy_factory)
    return runner.run_branch(overrides=overrides, max_steps=horizon, release_at=release_at)


def _kpis_from_result(res) -> dict:
    return {
        "deadlocks": int(res.kpis.get("deadlocks", res.kpis.get("num_deadlock_cycles", 0)) or 0),
        "done": int(res.success_count or 0),
        "total": int(res.total_agents or 0),
        "delay": int(res.kpis.get("total_delay", 0) or 0),
    }


def _train_outcome(res, handle: int, planned_arrival: int | None = None) -> dict:
    """The overridden train's own fate on this branch: arrived / delay /
    deadlocked, plus when it arrives and how that compares to the plan.
    Falls back to all-zero if the handle is missing."""
    o = res.agent_outcomes.get(int(handle)) or {
        "arrived": False,
        "deadlocked": False,
        "delay": 0,
    }
    arrival = o.get("arrival_step")
    return {
        "arrived": bool(o.get("arrived", False)),
        "delay": int(o.get("delay", 0) or 0),
        "deadlocked": bool(o.get("deadlocked", False)),
        "arrival_step": None if arrival is None else int(arrival),
        "planned_arrival": planned_arrival,
        "delay_vs_plan": (
            None if arrival is None or planned_arrival is None else int(arrival) - int(planned_arrival)
        ),
    }


def _branch_trajectories(res) -> dict:
    """Per-agent trajectories from a branch's snapshots, in the same shape
    scenarios use ({handle_str: [{step, row, col, ...}]}), so the map overlay
    can draw them with the existing forecast machinery."""
    from app.core.hmi_scenario_adapter import _extract_trajectories

    return _extract_trajectories(res.snapshots)


def _whatif_summary(baseline: dict, branch: dict, train: dict | None = None) -> str:
    """Plain-language consequence of the human's proposed action vs. the
    current course (baseline). Mirrors the framing used in recommendations."""
    parts: list[str] = []

    # The selected train's arrival first: two routes that both arrive inside a
    # wide latest-arrival window differ only here.
    if train:
        before = train["baseline"].get("arrival_step")
        after = train["branch"].get("arrival_step")
        if before is not None and after is not None and before != after:
            diff = after - before
            unit = "step" if abs(diff) == 1 else "steps"
            parts.append(f"arrives {abs(diff)} {unit} {'later' if diff > 0 else 'earlier'}")

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
        policy_factory = _policy_factory_for_session(session)

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
                code="override.riskIncrease",
                params={"train": int(handle), "before": int(before_deadlocks), "after": int(after_deadlocks)},
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
                code="override.fewerArrivals",
                params={"train": int(handle), "before": int(before_done), "after": int(after_done)},
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
    policy_factory = _policy_factory_for_session(session)

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
    planned = planned_arrival_steps(env)
    train = None
    if affected_handles:
        h = affected_handles[0]
        train = {
            "handle": h,
            "baseline": _train_outcome(baseline_res, h, planned.get(h)),
            "branch": _train_outcome(branch_res, h, planned.get(h)),
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
        "summary": _whatif_summary(baseline, branch, train),
        "train": train,
        "baseline_source": _baseline_source(session),
        "baseline_trajectories": baseline_traj,
        "branch_trajectories": branch_traj,
        "handles": affected_handles,
    }


def _proposal_variant(vid: str, source: str, res, handle: int, planned: dict) -> dict:
    return {
        "id": vid,
        "source": source,
        "train": _train_outcome(res, handle, planned.get(handle)),
        "system": _kpis_from_result(res),
        "trajectories": _branch_trajectories(res),
    }


PROPOSAL_OPTIONS = ("hold", "hold_until_clear", "proceed", "reroute")
_NOT_ARRIVED_PENALTY = 1000


def _impact_item(env, handle: int) -> dict | None:
    """The impact analysis' entry for `handle`, if the train is affected now."""
    from app.core.recommenders.registry import active_recommender

    for item in active_recommender().recommend(env):
        if int(item.get("handle", -1)) == int(handle):
            return item
    return None


def _course_score(res, planned: dict) -> int:
    """Lower is better: summed arrival delay against the plan (raw arrival step
    without a plan), and a heavy penalty per train that does not arrive."""
    score = 0
    for handle, outcome in res.agent_outcomes.items():
        arrival = outcome.get("arrival_step")
        if arrival is None:
            if not outcome.get("arrived"):
                score += _NOT_ARRIVED_PENALTY
            continue
        reference = planned.get(handle)
        score += int(arrival) - int(reference) if reference is not None else int(arrival)
    return score


def _arrivals(res) -> dict:
    return {h: o.get("arrival_step") for h, o in sorted(res.agent_outcomes.items())}


def _variant_metrics(res, planned: dict, now: int, horizon: int) -> dict:
    """The few numbers the three courses can be compared on.

    - ``lateness``: summed minutes-late against the timetable, arrived trains
      only. Early arrivals do not offset lateness — a train that gains time does
      not repay the one that lost it.
    - ``time_in_network``: summed steps the trains are still running from now on,
      the closest thing this simulation has to resource use (longer occupancy,
      more energy). Trains that never arrive count the full horizon.
    - ``not_arrived``: trains still out at the horizon, which is what makes the
      other two numbers incomparable if it differs between courses.
    """
    lateness = 0
    time_in_network = 0
    not_arrived = 0
    for handle, outcome in res.agent_outcomes.items():
        arrival = outcome.get("arrival_step")
        if arrival is None:
            not_arrived += 1
            time_in_network += int(horizon)
            continue
        reference = planned.get(int(handle))
        if reference is not None:
            lateness += max(0, int(arrival) - int(reference))
        time_in_network += max(0, int(arrival) - int(now))
    return {
        "lateness": int(lateness),
        "time_in_network": int(time_in_network),
        "not_arrived": int(not_arrived),
    }


def _human_course(env, handle: int, committed: dict, elapsed: int, action, option):
    """Overrides and release steps for the operator's choice, and its label."""
    overrides = dict(committed)
    release: dict = {}
    handle = int(handle)
    if option is not None:
        if option not in PROPOSAL_OPTIONS:
            raise HTTPException(400, f"Invalid option {option!r}; one of {', '.join(PROPOSAL_OPTIONS)}")
        if option == "proceed":
            overrides.pop(handle, None)
        elif option in ("hold", "hold_until_clear"):
            overrides[handle] = 4
            if option == "hold_until_clear":
                item = _impact_item(env, handle)
                clears = int(item["clears_in_steps"]) if item else 0
                release[handle] = elapsed + max(1, clears)
        else:  # reroute
            item = _impact_item(env, handle)
            if not item or item.get("reroute_action") is None:
                raise HTTPException(409, f"No reroute is available for train {handle} now")
            overrides[handle] = int(item["reroute_action"])
        return overrides, release, option
    overrides[handle] = int(action)
    return overrides, release, f"action:{int(action)}"


class ProposalApplyRequest(BaseModel):
    """Which of the three courses the operator takes for real."""
    variant: str            # 'plan' | 'ai' | 'human'
    handle: int
    option: str | None = None      # human: hold | hold_until_clear | proceed | reroute
    priority: list[int] | None = None  # ai: the order this replan was computed for


@router.post("/{session_id}/proposals/apply")
def apply_proposal(session_id: str, req: ProposalApplyRequest):
    """Commit one of Plan / KI / Mensch to the running session.

    - ``plan``: drop this train's override — it follows the timetable again.
    - ``ai``: re-solve the replan for `priority` and make it the plan the session
      runs on (`install_trainrun_plan`), with the standing overrides cleared,
      because they were answers to the course the replan just replaced. The
      timetable stays the yardstick for "delay vs plan".
    - ``human``: the operator's option as an override, exactly what the what-if
      simulated.

    The read-only sibling is `GET /proposals`. Plan: docs/plans/proposal-agents-roadmap.md.
    """
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    env = session.env
    handle = int(req.handle)
    if handle < 0 or handle >= len(env.agents):
        raise HTTPException(404, f"Agent {handle} not found")

    step = int(getattr(env, "_elapsed_steps", 0) or 0)

    if req.variant == "plan":
        override_manager.clear(session_id, handle)
        label = "Plan behalten"

    elif req.variant == "ai":
        priority = tuple(int(h) for h in (req.priority or ()))
        trainruns = replan_from_state(env, priority=priority)
        if not trainruns:
            raise HTTPException(409, "The planner found no collision-free plan from here")
        install_trainrun_plan(env, trainruns)
        session.trainrun_plan = trainruns
        session.policy = PLAN_POLICY_ID
        # The overrides answered the old course; leaving them would fight the
        # replan the operator just accepted.
        override_manager.clear_all(session_id)
        label = "KI-Plan übernommen"

    elif req.variant == "human":
        if not req.option:
            raise HTTPException(400, "variant 'human' needs an option")
        overrides, _release, choice = _human_course(env, handle, {}, step, None, req.option)
        action = overrides.get(handle)
        if action is None:
            override_manager.clear(session_id, handle)
        else:
            override_manager.set(session_id, handle, int(action))
        label = f"Mensch: {choice}"

    else:
        raise HTTPException(400, f"Unknown variant {req.variant!r}")

    return {
        "applied": req.variant,
        "label": label,
        "step": step,
        "policy": getattr(session, "policy", None) or "",
    }


@router.get("/{session_id}/proposals")
def get_proposals(
    session_id: str,
    handle: int,
    action: int | None = None,
    option: str | None = None,
    alternatives: int = 3,
):
    """Plan / KI / Mensch for one train, each simulated to the same horizon.

    - ``plan``: what drives the session now (its plan, a Director plan or a
      policy) with the committed overrides — the course if nobody steps in.
    - ``ai``: the best of the Prioritized Planning replans over different priority
      orders (`app.planners.replan.replan_orders`), each followed by `PlanPolicy`
      and ranked by delay against the plan; the next best come back as
      ``ai_alternatives``. Each carries its ``priority`` order and ``score``.
    - ``human``: the plan course with the operator's choice — an ``option``
      (hold, hold_until_clear, proceed, reroute) or a raw ``action`` — when given.

    Read-only, like the what-if. Plan: docs/plans/proposal-agents-roadmap.md (2a/2c).
    """
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    env = session.env
    if handle < 0 or handle >= len(env.agents):
        raise HTTPException(404, f"Agent {handle} not found")
    if action is not None and action not in (0, 1, 2, 3, 4):
        raise HTTPException(400, f"Invalid action {action}")

    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    max_ep = int(getattr(env, "_max_episode_steps", 0) or 0)
    horizon = min(max(50, max_ep - elapsed) if max_ep else 200, 250)
    planned = planned_arrival_steps(env)
    committed = dict(override_manager.get_all(session_id))
    plan_factory = _policy_factory_for_session(session)

    plan_res = _branch_run(env, plan_factory, committed, horizon)
    variants = [_proposal_variant("plan", _baseline_source(session), plan_res, handle, planned)]
    variants[0]["score"] = _course_score(plan_res, planned)
    variants[0]["metrics"] = _variant_metrics(plan_res, planned, elapsed, horizon)

    ranked = []
    for order, trainruns in replan_orders(env):
        res = _branch_run(env, lambda tr=trainruns: PlanPolicy(None, tr), {}, horizon)
        ranked.append((_course_score(res, planned), list(order), res))
    ranked.sort(key=lambda entry: entry[0])

    ai_alternatives = []
    for rank, (score, order, res) in enumerate(ranked[: max(1, int(alternatives))]):
        variant = _proposal_variant("ai" if rank == 0 else f"ai-{rank + 1}", "pp_replan", res, handle, planned)
        variant["priority"] = order
        variant["score"] = score
        variant["metrics"] = _variant_metrics(res, planned, elapsed, horizon)
        if rank == 0:
            variants.append(variant)
        else:
            ai_alternatives.append(variant)

    if action is not None or option is not None:
        overrides, release, choice = _human_course(env, handle, committed, elapsed, action, option)
        human_res = _branch_run(env, plan_factory, overrides, horizon, release_at=release)
        variant = _proposal_variant("human", "operator", human_res, handle, planned)
        variant["choice"] = choice
        variant["score"] = _course_score(human_res, planned)
        variant["metrics"] = _variant_metrics(human_res, planned, elapsed, horizon)
        variants.append(variant)

    return {
        "session_id": session_id,
        "handle": int(handle),
        "step": elapsed,
        "horizon": horizon,
        "ai_available": bool(ranked),
        # The best replan keeps every arrival of the plan: the AI would not change course.
        "ai_matches_plan": bool(ranked) and _arrivals(ranked[0][2]) == _arrivals(plan_res),
        "variants": variants,
        "ai_alternatives": ai_alternatives,
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
