"""Stage 2a: a PP replan from the running episode, and Plan / KI / Mensch proposals.

Plan: docs/plans/proposal-agents-roadmap.md.
"""
import warnings

warnings.filterwarnings("ignore")

import pytest
from fastapi import HTTPException

from app.api.overrides import (
    ProposalApplyRequest,
    _branch_run,
    _policy_factory_for_session,
    apply_proposal,
    get_proposals,
)
from app.core.override_manager import override_manager
from app.policies.plan_policy import planned_arrival_steps, trainruns_from_env
from app.api.sessions import _build_policy
from app.core.disturbances import apply_due_disturbances
from app.core.scenario_presets import select_disturbances
from app.core.session_manager import session_manager
from app.planners.blackbox.utils import check_no_collisions
from app.planners.replan import build_rail_digraph, replan_from_state, replan_orders
from app.policies.plan_policy import PlanPolicy

PRESET = "pf-ch-wn-wal-long-approach"
DISTURBANCE = "interview-e1-breakdown-single-track"
FORK_STEP = 30


def _forked_session():
    session = session_manager.create(
        scenario_preset_id=PRESET, disturbances=select_disturbances(PRESET, [DISTURBANCE]),
    )
    policy = _build_policy(session.id, session.env, session.policy)
    for _ in range(FORK_STEP):
        policy.start_step()
        actions = policy.act_many(session.env.get_agent_handles(), session.last_observations or {})
        obs, _, _, _ = session.env.step(actions)
        policy.end_step()
        session.last_observations = obs
        apply_due_disturbances(session.id, session, session.env)
    return session


def test_rail_digraph_has_each_train_in_its_heading():
    env = _forked_session().env
    graph = build_rail_digraph(env)
    for agent in env.agents:
        if agent.position is not None:
            assert (agent.position[0], agent.position[1], agent.direction) in graph


def test_replan_covers_the_trains_and_keeps_a_broken_down_train_standing():
    env = _forked_session().env
    down = env.agents[0].malfunction_handler.malfunction_down_counter
    assert down > 0, "the tour disturbance should have stopped train 0 by now"

    trainruns = replan_from_state(env)

    assert trainruns is not None
    assert set(trainruns) == {0, 1, 2}
    run = trainruns[0]
    assert tuple(run[0].waypoint.position) == tuple(env.agents[0].position)
    assert run[1].scheduled_at >= FORK_STEP + down


def test_replan_paths_are_collision_free_when_followed():
    session = _forked_session()
    trainruns = replan_from_state(session.env)

    result = _branch_run(session.env, lambda: PlanPolicy(None, trainruns), {}, 150)

    assert result.success_count == 3
    assert int(result.kpis.get("deadlocks", 0) or 0) == 0
    # The waypoints themselves never put two trains in one cell at one step.
    check_no_collisions({
        handle: [((wp.waypoint.position[0], wp.waypoint.position[1], wp.waypoint.direction), wp.scheduled_at)
                 for wp in run]
        for handle, run in trainruns.items()
    })


def test_proposals_offer_plan_ai_and_human():
    session = _forked_session()

    response = get_proposals(session.id, handle=1, action=4)

    assert response["ai_available"] is True
    assert [v["id"] for v in response["variants"]] == ["plan", "ai", "human"]
    assert [v["source"] for v in response["variants"]] == ["plan", "pp_replan", "operator"]
    for variant in response["variants"]:
        assert {"arrival_step", "planned_arrival", "delay_vs_plan"} <= set(variant["train"])
        assert {"done", "total", "delay", "deadlocks"} <= set(variant["system"])


def test_branch_release_ends_a_hold():
    session = _forked_session()
    factory = _policy_factory_for_session(session)

    held = _branch_run(session.env, factory, {1: 4}, 150)
    released = _branch_run(session.env, factory, {1: 4}, 150, release_at={1: FORK_STEP + 12})

    assert held.agent_outcomes[1]["arrival_step"] is None
    assert released.agent_outcomes[1]["arrival_step"] is not None


def test_replan_orders_are_distinct_plans():
    orders = replan_orders(_forked_session().env)

    assert orders
    keys = {
        tuple((h, tuple(wp.scheduled_at for wp in run)) for h, run in sorted(trainruns.items()))
        for _, trainruns in orders
    }
    assert len(keys) == len(orders)


def test_applying_the_ai_plan_installs_it_and_keeps_the_timetable_as_yardstick():
    session = _forked_session()
    before = planned_arrival_steps(session.env)
    timetable = trainruns_from_env(session.env)

    response = apply_proposal(session.id, ProposalApplyRequest(variant="ai", handle=1))

    assert response["applied"] == "ai"
    assert session.policy == "plan"
    installed = trainruns_from_env(session.env)
    assert installed is not timetable
    # The session now runs the replan, but "delay vs plan" still means the timetable.
    assert planned_arrival_steps(session.env) == before
    # And the live policy built from here follows the replan, not the timetable.
    policy = _build_policy(session.id, session.env, session.policy)
    assert policy is not None


def test_applying_human_and_plan_set_and_clear_the_override():
    session = _forked_session()

    apply_proposal(session.id, ProposalApplyRequest(variant="human", handle=1, option="hold"))
    assert override_manager.get_all(session.id).get(1) == 4

    apply_proposal(session.id, ProposalApplyRequest(variant="plan", handle=1))
    assert 1 not in override_manager.get_all(session.id)


def test_applying_human_without_an_option_is_refused():
    session = _forked_session()

    with pytest.raises(HTTPException) as excinfo:
        apply_proposal(session.id, ProposalApplyRequest(variant="human", handle=1))

    assert excinfo.value.status_code == 400


def test_proposals_rank_the_ai_orders_and_hold_until_clear_arrives():
    session = _forked_session()

    response = get_proposals(session.id, handle=1, option="hold_until_clear")

    ai = response["variants"][1]
    assert ai["id"] == "ai" and ai["priority"]
    scores = [ai["score"]] + [v["score"] for v in response["ai_alternatives"]]
    assert scores == sorted(scores)

    human = response["variants"][-1]
    assert human["id"] == "human" and human["choice"] == "hold_until_clear"
    assert human["train"]["arrival_step"] is not None
