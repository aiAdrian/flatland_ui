"""HMI API: Notifications, Scenarios, Recommendations.

* Notifications still come from the mock (will follow in a separate step).
* Scenarios are real what-if branches via ScenarioBuilder, with mock
  fallback when no agent is on the map yet.
* Recommendations are derived from the top-scoring scenario, with mock
  fallback if DLA is already optimal or generation fails.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.session_manager import session_manager
from app.core.hmi_mock import (
    generate_bundle,
    generate_notifications,
    generate_recommendations as mock_generate_recommendations,
    generate_scenarios as mock_generate_scenarios,
)
from app.core.hmi_scenario_adapter import scenarios_to_options
from app.core.recommendation_generator import (
    generate_recommendations as real_recommendations,
)
from app.core.scenario_builder import ScenarioBuilder
from app.models.hmi import (
    AppNotification,
    HmiBundle,
    Recommendation,
    ScenarioOption,
)
from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy


# ── Policy registry (used by /hmi/scenarios + POST /policy) ──────────
def _build_all_policies():
    from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy
    from app.policies.shortest_path_policy import ShortestPathPolicy
    from app.policies.forward_only_policy import ForwardOnlyPolicy
    from app.policies.do_nothing_policy import DoNothingPolicy
    from app.policies.random_policy import RandomPolicy
    return {
        "deadlock_avoidance": DeadLockAvoidancePolicy,
        "shortest_path": ShortestPathPolicy,
        "forward_only": ForwardOnlyPolicy,
        "do_nothing": DoNothingPolicy,
        "random": RandomPolicy,
    }


_ALL_POLICIES = _build_all_policies()


def _policy_factory_for(policy_id: str):
    return _ALL_POLICIES.get(policy_id)


router = APIRouter()


# ── helpers ────────────────────────────────────────────────────────


def _step_for(session_id: str) -> int:
    sess = session_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    env = getattr(sess, "env", None)
    if env is None:
        return 0
    return int(getattr(env, "_elapsed_steps", 0) or 0)


def _pick_default_handle(env) -> Optional[int]:
    """Pick the most interesting agent for what-if analysis:
       1) any MOVING / STOPPED / MALFUNCTION
       2) any READY_TO_DEPART
       3) None  → caller falls back to mock."""
    priority_states = ("MOVING", "STOPPED", "MALFUNCTION", "READY_TO_DEPART")
    for state_name in priority_states:
        for h, ag in enumerate(env.agents):
            s = ag.state.name if hasattr(ag.state, "name") else str(ag.state)
            if s == state_name:
                return h
    return None


# ── notifications (mock for now) ───────────────────────────────────


@router.get("/{session_id}/hmi/notifications", response_model=list[AppNotification])
def get_notifications(session_id: str):
    return generate_notifications(session_id, _step_for(session_id))


# ── scenarios (real, with mock fallback) ───────────────────────────


@router.get("/{session_id}/hmi/scenarios", response_model=list[ScenarioOption])
def get_scenarios(
    session_id: str,
    horizon: int = Query(200, ge=10, le=500, description="Branch lookahead in steps"),
):
    """What-if scenarios across alternative POLICIES.

    Runs the current policy as baseline plus each alternative policy
    in turn, all from the same env state. Returns:
      [baseline] + [alt1, alt2, …] sorted by score descending.

    Cached per (session_id, env._elapsed_steps) — no re-compute until
    the env actually advances.
    """
    from app.core.scenario_cache import scenario_cache
    from app.core.scenario_builder import ScenarioBuilder

    sess = session_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    env = getattr(sess, "env", None)
    if env is None:
        return mock_generate_scenarios(session_id, _step_for(session_id))

    # Determine the currently active baseline policy for this session.
    baseline_id = getattr(sess, "policy", None) or "deadlock_avoidance"
    baseline_factory = _policy_factory_for(baseline_id)
    if baseline_factory is None:
        # Unknown policy id stored on session — fall back to DLA.
        baseline_id = "deadlock_avoidance"
        baseline_factory = DeadLockAvoidancePolicy

    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    # Cache key combines step + horizon so different horizons don't collide.
    cache_key_step = elapsed * 1000 + int(horizon)
    cached = scenario_cache.get(session_id, cache_key_step)
    if cached is not None:
        return cached

    # Build candidate list (every policy id except baseline).
    candidates = [
        (pid, fac) for pid, fac in _ALL_POLICIES.items()
        if pid != baseline_id
    ]

    try:
        builder = ScenarioBuilder(env, baseline_id, baseline_factory)
        scenarios = builder.generate_scenarios(
            candidate_policies=candidates,
            horizon=horizon,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "ScenarioBuilder failed for session %s: %r", session_id, e,
        )
        return mock_generate_scenarios(session_id, _step_for(session_id))

    options = scenarios_to_options(scenarios)
    scenario_cache.put(session_id, cache_key_step, options)
    return options


@router.get("/{session_id}/hmi/recommendations", response_model=list[Recommendation])
def get_recommendations(session_id: str):
    """Surface the top-scoring alternative policy as a Recommendation,
    only if it clearly beats the current baseline. Empty list otherwise
    — that's the right signal: 'current policy is fine'."""
    from app.core.scenario_cache import scenario_cache
    from app.core.scenario_builder import ScenarioBuilder

    sess = session_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    env = getattr(sess, "env", None)
    if env is None:
        return []

    baseline_id = getattr(sess, "policy", None) or "deadlock_avoidance"
    baseline_factory = _policy_factory_for(baseline_id) or DeadLockAvoidancePolicy

    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    max_ep = int(getattr(env, "_max_episode_steps", 0) or 0)
    horizon = min(max(50, max_ep - elapsed) if max_ep else 200, 500)

    # We share the scenario cache with /hmi/scenarios so we don't re-run
    # the same 5 branches twice in a row.
    cache_key_step = elapsed * 1000 + horizon
    cached_options = scenario_cache.get(session_id, cache_key_step)

    # Cached options are already serialized; we need the Scenario objects.
    # Easiest: rebuild from scratch when the cache only has options.
    # (Future optimization: cache both shapes.)
    try:
        candidates = [
            (pid, fac) for pid, fac in _ALL_POLICIES.items() if pid != baseline_id
        ]
        builder = ScenarioBuilder(env, baseline_id, baseline_factory)
        scenarios = builder.generate_scenarios(
            candidate_policies=candidates, horizon=horizon,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "Recommendation: ScenarioBuilder failed for %s: %r", session_id, e,
        )
        return []

    return real_recommendations(session_id, scenarios)


# ── bundle (still mock, used by some UI panels) ────────────────────


@router.get("/{session_id}/hmi", response_model=HmiBundle)
def get_bundle(session_id: str):
    return generate_bundle(session_id, _step_for(session_id))
