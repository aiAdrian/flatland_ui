"""Plan-driven sessions are forecast with their own plan, not a proxy policy.

Before, the map forecast and the what-if of a session running a scenario plan
fell back to deadlock avoidance: for ICE_42 (handle 1) on the Walensee corridor the
what-if baseline stayed on the lower track and never arrived, while the train
actually switched tracks at column 95 and arrived at step 70.
Plan: docs/plans/proposal-agents-roadmap.md (stage 1).
"""
import warnings

warnings.filterwarnings("ignore")

from flatland.envs.step_utils.states import TrainState

from app.api.hmi import _rollout_baseline
from app.api.overrides import (
    WhatIfRequest,
    _branch_run,
    _branch_trajectories,
    _policy_factory_for_session,
    what_if_override,
)
from app.api.sessions import _build_policy
from app.core.disturbances import apply_due_disturbances
from app.core.scenario_presets import select_disturbances
from app.core.session_manager import session_manager
from app.policies.plan_policy import PlanPolicy, planned_arrival_steps

PRESET = "pf-ch-wn-wal-long-approach"
DISTURBANCE = "interview-e1-breakdown-single-track"
FORK_STEP = 30
HANDLE = 1


def _session():
    session = session_manager.create(
        scenario_preset_id=PRESET, disturbances=select_disturbances(PRESET, [DISTURBANCE]),
    )
    return session, _build_policy(session.id, session.env, session.policy)


def _step(session, policy) -> dict:
    policy.start_step()
    actions = policy.act_many(session.env.get_agent_handles(), session.last_observations or {})
    obs, _, dones, _ = session.env.step(actions)
    policy.end_step()
    session.last_observations = obs
    apply_due_disturbances(session.id, session, session.env)
    return dones


def _forked_session():
    session, policy = _session()
    for _ in range(FORK_STEP):
        _step(session, policy)
    return session


def _live_course(handle: int):
    """Cells and arrival step of `handle` after FORK_STEP on the live run."""
    session, policy = _session()
    cells, arrival = {}, None
    for _ in range(180):
        try:
            dones = _step(session, policy)
        except Exception:
            break
        agent = session.env.agents[handle]
        step = int(session.env._elapsed_steps)
        if step > FORK_STEP and agent.position is not None:
            cells[step] = tuple(int(x) for x in agent.position)
        if arrival is None and agent.state == TrainState.DONE:
            arrival = step
        if dones.get("__all__"):
            break
    return cells, arrival


def test_planned_arrival_steps_come_from_the_plan():
    session, _ = _session()
    assert planned_arrival_steps(session.env) == {0: 57, 1: 63, 2: 57}


def test_forecast_and_whatif_baselines_follow_the_plan():
    session = _forked_session()

    baseline_id, forecast_factory = _rollout_baseline(session, {"deadlock_avoidance"})
    assert baseline_id == "plan"
    assert isinstance(forecast_factory(), PlanPolicy)
    assert isinstance(_policy_factory_for_session(session)(), PlanPolicy)


def test_whatif_baseline_matches_the_live_run():
    session = _forked_session()
    live_cells, live_arrival = _live_course(HANDLE)

    result = _branch_run(session.env, _policy_factory_for_session(session), {}, 150)
    branch_cells = {
        p.step: (p.row, p.col)
        for p in _branch_trajectories(result).get(str(HANDLE), [])
        if p.row is not None
    }

    shared = sorted(set(branch_cells) & set(live_cells))
    assert shared, "branch and live run share no steps"
    assert all(branch_cells[s] == live_cells[s] for s in shared[:15])
    assert live_arrival is not None
    assert result.agent_outcomes[HANDLE]["arrival_step"] == live_arrival


def test_whatif_response_names_the_plan_and_reports_arrival():
    session = _forked_session()

    response = what_if_override(session.id, WhatIfRequest(overrides={HANDLE: 4}))

    assert response["baseline_source"] == "plan"
    baseline = response["train"]["baseline"]
    assert baseline["planned_arrival"] == 63
    assert baseline["arrival_step"] is not None
    assert baseline["delay_vs_plan"] == baseline["arrival_step"] - 63
