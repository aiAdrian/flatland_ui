"""HMI API: Notifications, Scenarios, Recommendations.

* Notifications still come from the mock (will follow in a separate step).
* Scenarios are real what-if branches via ScenarioBuilder, with mock
  fallback when no agent is on the map yet.
* Recommendations are derived from the top-scoring scenario, with mock
  fallback if DLA is already optimal or generation fails.
"""
from typing import Optional
import logging
import time

from fastapi import APIRouter, HTTPException, Query

from app.core.session_manager import session_manager
from app.core.hmi_mock import (
    generate_bundle,
    generate_notifications,
    generate_recommendations as mock_generate_recommendations,
    generate_scenarios as mock_generate_scenarios,
)
from app.core.hmi_scenario_adapter import scenarios_to_options, _extract_trajectories
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
from app.policies.registry import scenario_policy_factories


# ── Policy registry (used by /hmi/scenarios + POST /policy) ──────────
_ALL_POLICIES = scenario_policy_factories()


def _policy_factory_for(policy_id: str):
    return _ALL_POLICIES.get(policy_id)


_perf_log = logging.getLogger("flatland.perf")
_perf_log.setLevel(logging.INFO)
if not _perf_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _perf_log.addHandler(_h)

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


@router.get("/{session_id}/hmi/impact")
def get_impact(session_id: str):
    """Impact analysis / intervention recommendations: trains affected by a
    malfunctioning train, with a per-train recommendation. Produced by the active
    InterventionRecommender (pluggable seam) — Phase-1 proximity today, PP replan
    / RL later. Empty when there is no active malfunction."""
    from app.core.recommenders.registry import active_recommender

    sess = session_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    env = getattr(sess, "env", None)
    if env is None:
        return []
    try:
        return active_recommender().recommend(env)
    except Exception as e:
        _perf_log.warning("Impact analysis failed for %s: %r", session_id, e)
        return []


# ── scenarios (real, with mock fallback) ───────────────────────────


@router.get("/{session_id}/hmi/scenarios", response_model=list[ScenarioOption])
def get_scenarios(
    session_id: str,
    horizon: int | None = Query(None, ge=10, le=2000, description="Branch lookahead; defaults to remaining episode."),
    kpi_time: float = Query(1.0, ge=0.0, le=1.0, description="KPI priority: time"),
    kpi_energy: float = Query(0.5, ge=0.0, le=1.0, description="KPI priority: energy"),
    kpi_platform: float = Query(0.5, ge=0.0, le=1.0, description="KPI priority: platform routing"),
    kpi_train: float = Query(0.5, ge=0.0, le=1.0, description="KPI priority: train routing"),
):
    """What-if scenarios across alternative POLICIES.

    Runs the current policy as baseline plus each alternative policy
    in turn, all from the same env state. Returns:
      [baseline] + [alt1, alt2, …] sorted by score descending.

    Cached per (session_id, env._elapsed_steps) — no re-compute until
    the env actually advances.
    """
    from app.core.scenario_cache import scenario_cache
    from app.core.scenario_builder import ScenarioBuilder, scoring_weights_from_kpi

    weights = scoring_weights_from_kpi(kpi_time, kpi_energy, kpi_platform, kpi_train)

    sess = session_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    env = getattr(sess, "env", None)
    if env is None:
        return mock_generate_scenarios(session_id, _step_for(session_id))

    # Determine enabled scenario policies for this session.
    enabled = set(getattr(sess, "enabled_scenario_policies", set(_ALL_POLICIES.keys())))
    enabled = {pid for pid in enabled if pid in _ALL_POLICIES}
    if not enabled:
        enabled = {"deadlock_avoidance"}

    # Determine baseline: active session policy if enabled, otherwise first enabled.
    baseline_id = getattr(sess, "policy", None) or "deadlock_avoidance"
    if baseline_id not in enabled:
        baseline_id = sorted(enabled)[0]

    baseline_factory = _policy_factory_for(baseline_id)
    if baseline_factory is None:
        baseline_id = "deadlock_avoidance"
        baseline_factory = _policy_factory_for("deadlock_avoidance")
        enabled.add(baseline_id)

    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    # Smart default: simulate until episode end (cap 1000 steps; the
    # runner exits early when all_done anyway).
    if horizon is None:
        max_ep = int(getattr(env, "_max_episode_steps", 0) or 0)
        # Use full remaining episode — user controls duration via max_episode_steps
        # at session creation. Runner exits early on all_done anyway.
        horizon = max(50, max_ep - elapsed) if max_ep else 200

    # Pull current operator overrides for this session.
    # Cache key MUST include override state so that changing overrides
    # triggers a fresh compute, not a cache hit from old overrides.
    overrides: dict = {}
    if session_id is not None:
        try:
            from app.core.override_manager import override_manager
            overrides = dict(override_manager.get_all(session_id))
        except Exception:
            overrides = {}
    
    # Cache key combines step + horizon + override hash so that:
    # - Different steps: different cache entry
    # - Different horizons: different cache entry
    # - Different overrides: different cache entry → re-compute
    import hashlib
    override_hash = hashlib.md5(
        str(sorted(overrides.items())).encode()
    ).hexdigest()[:8]
    kpi_hash = hashlib.md5(
        f"{weights.done:.3f}:{weights.delay:.3f}:{weights.deadlock:.3f}".encode()
    ).hexdigest()[:6]
    cache_key_step = elapsed * 1000 + int(horizon)
    cache_key_str = f"{cache_key_step}:{override_hash}:{kpi_hash}"

    cached = scenario_cache.get(session_id, cache_key_str)
    if cached is not None:
        _perf_log.info(
            f"[SCENARIOS] cache_hit session={session_id[:8]} step={elapsed} "
            f"overrides={override_hash}"
        )
        return cached
    _perf_log.info(
        f"[SCENARIOS] cache_miss session={session_id[:8]} step={elapsed} "
        f"horizon={horizon} overrides={override_hash}"
    )

    # Build candidate list (every policy id except baseline).
    candidates = [
        (pid, fac)
        for pid, fac in _ALL_POLICIES.items()
        if pid != baseline_id and pid in enabled
    ]

    try:
        # Re-fetch fresh env before building scenarios to ensure we fork
        # from the absolutely latest state (main simulation may have advanced).
        sess_fresh = session_manager.get(session_id)
        if not sess_fresh:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        env = getattr(sess_fresh, "env", None)
        if env is None:
            return mock_generate_scenarios(session_id, _step_for(session_id))
        
        n_agents = len(env.get_agent_handles()) if hasattr(env, 'get_agent_handles') else 0
        n_policies = 1 + len(candidates)  # baseline + candidates
        t_total0 = time.perf_counter()
        builder = ScenarioBuilder(env, baseline_id, baseline_factory, session_id=session_id, scoring_weights=weights)
        scenarios = builder.generate_scenarios(
            candidate_policies=candidates,
            horizon=horizon,
        )
        t_total_ms = (time.perf_counter() - t_total0) * 1000
        _perf_log.info(
            f"[SCENARIOS] agents={n_agents} policies={n_policies} "
            f"horizon={horizon} total={t_total_ms:.1f}ms"
        )
        _perf_log.info(
            f"[SCENARIOS] recompute_done session={session_id[:8]} baseline={baseline_id} "
            f"step={int(getattr(env, '_elapsed_steps', 0) or 0)} overrides={override_hash}"
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "ScenarioBuilder failed for session %s: %r", session_id, e,
        )
        return mock_generate_scenarios(session_id, _step_for(session_id))

    options = scenarios_to_options(scenarios, env=env)
    # Cache BOTH shapes from this single compute run, so a subsequent
    # /hmi/recommendations call for the same step can reuse the
    # Scenario objects without re-running ScenarioBuilder.
    # Include override hash in key so override changes invalidate cache.
    scenario_cache.put_full(session_id, cache_key_str, scenarios, options)
    return options


@router.get("/{session_id}/hmi/recommendations", response_model=list[Recommendation])
def get_recommendations(
    session_id: str,
    kpi_time: float = Query(1.0, ge=0.0, le=1.0),
    kpi_energy: float = Query(0.5, ge=0.0, le=1.0),
    kpi_platform: float = Query(0.5, ge=0.0, le=1.0),
    kpi_train: float = Query(0.5, ge=0.0, le=1.0),
):
    """Surface the top-scoring alternative policy as a Recommendation,
    only if it clearly beats the current baseline. Empty list otherwise
    — that's the right signal: 'current policy is fine'."""
    from app.core.scenario_cache import scenario_cache
    from app.core.scenario_builder import ScenarioBuilder, scoring_weights_from_kpi

    weights = scoring_weights_from_kpi(kpi_time, kpi_energy, kpi_platform, kpi_train)

    sess = session_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    env = getattr(sess, "env", None)
    if env is None:
        return []

    enabled = set(getattr(sess, "enabled_scenario_policies", set(_ALL_POLICIES.keys())))
    enabled = {pid for pid in enabled if pid in _ALL_POLICIES}
    if not enabled:
        enabled = {"deadlock_avoidance"}

    baseline_id = getattr(sess, "policy", None) or "deadlock_avoidance"
    if baseline_id not in enabled:
        baseline_id = sorted(enabled)[0]
    baseline_factory = _policy_factory_for(baseline_id) or _policy_factory_for("deadlock_avoidance")

    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    max_ep = int(getattr(env, "_max_episode_steps", 0) or 0)
    horizon = min(max(50, max_ep - elapsed) if max_ep else 200, 500)

    # Get overrides for cache key (must match /hmi/scenarios logic).
    import hashlib
    overrides: dict = {}
    try:
        from app.core.override_manager import override_manager
        overrides = dict(override_manager.get_all(session_id))
    except Exception:
        overrides = {}
    
    override_hash = hashlib.md5(
        str(sorted(overrides.items())).encode()
    ).hexdigest()[:8]
    kpi_hash = hashlib.md5(
        f"{weights.done:.3f}:{weights.delay:.3f}:{weights.deadlock:.3f}".encode()
    ).hexdigest()[:6]
    cache_key_step = elapsed * 1000 + horizon
    cache_key_str = f"{cache_key_step}:{override_hash}:{kpi_hash}"

    # Try the cache FIRST: if /hmi/scenarios was just called for this
    # same step + overrides, the Scenario objects are already there —
    # recommendations take ~10ms instead of re-running 1300ms of DLA.
    scenarios = scenario_cache.get_scenarios(session_id, cache_key_str)

    if scenarios is not None:
        _perf_log.info(
            f"[REC] cache_hit session={session_id[:8]} step={elapsed} "
            f"overrides={override_hash} (no re-compute)"
        )
        return real_recommendations(session_id, scenarios)
    _perf_log.info(
        f"[REC] cache_miss session={session_id[:8]} step={elapsed} "
        f"horizon={horizon} overrides={override_hash}"
    )

    # Cache miss → compute. Mirror the /hmi/scenarios setup so the cache
    # entry we drop in is identical.
    try:
        # Re-fetch fresh env to ensure we fork from the latest state
        sess_fresh = session_manager.get(session_id)
        if not sess_fresh:
            return []
        env = getattr(sess_fresh, "env", None)
        if env is None:
            return []
        
        candidates = [
            (pid, fac) for pid, fac in _ALL_POLICIES.items()
            if pid != baseline_id and pid in enabled
        ]
        builder = ScenarioBuilder(env, baseline_id, baseline_factory, session_id=session_id, scoring_weights=weights)
        scenarios = builder.generate_scenarios(
            candidate_policies=candidates, horizon=horizon,
        )
        _perf_log.info(
            f"[REC] recompute_done session={session_id[:8]} baseline={baseline_id} "
            f"step={int(getattr(env, '_elapsed_steps', 0) or 0)} overrides={override_hash}"
        )
        # Populate cache so the next /hmi/scenarios pull is also free.
        try:
            options = scenarios_to_options(scenarios, env=env)
            scenario_cache.put_full(session_id, cache_key_str, scenarios, options)
        except Exception:
            pass  # Best-effort: if serialization fails, still return recs.
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "Recommendation: ScenarioBuilder failed for %s: %r", session_id, e,
        )
        return []

    return real_recommendations(session_id, scenarios)


@router.get("/{session_id}/hmi/marey-data")
def get_marey_data(session_id: str):
    """Combined history + forecast trajectories for Marey-Chart.
    
    For each agent:
    - history: real trajectory from step 0 to NOW (from session.snapshots)
    - forecast: predicted trajectory from NOW+1 forward (from scenarios)
    - override_active: bool indicating if override is set
    
    This ensures the Marey shows the complete picture: what happened + what's predicted.
    """
    from app.core.scenario_cache import scenario_cache
    from app.core.override_manager import override_manager
    from app.core.marey_topology import classify_marey_point
    from app.core.tile_resolver import resolve_tile

    sess = session_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    env = getattr(sess, "env", None)
    if env is None:
        return {"agents": {}}
    
    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    
    # Get current overrides
    try:
        active_overrides = set(override_manager.get_all(session_id).keys())
    except Exception:
        active_overrides = set()
    
    max_ep = int(getattr(env, "_max_episode_steps", 0) or 0)
    horizon = max(50, max_ep - elapsed) if max_ep else 200
    
    # Build cache key (must match /hmi/scenarios logic)
    import hashlib
    try:
        all_overrides = dict(override_manager.get_all(session_id))
    except Exception:
        all_overrides = {}
    override_hash = hashlib.md5(
        str(sorted(all_overrides.items())).encode()
    ).hexdigest()[:8]
    cache_key_str = f"{elapsed * 1000 + horizon}:{override_hash}"
    
    # Try to get scenario from cache first
    scenarios = scenario_cache.get_scenarios(session_id, cache_key_str)
    
    if scenarios is None:
        # Cache miss — return minimal data; Frontend will call /hmi/scenarios to populate
        return {"agents": {}, "cached": False}
    
    options = scenarios_to_options(scenarios, env=env)
    baseline_opt = next((s for s in options if s.isBaseline), options[0] if options else None)
    if not baseline_opt:
        return {"agents": {}, "cached": False}
    
    # Build output: history + forecast per agent
    def _dump_trajectory_point(point):
        if isinstance(point, dict):
            return dict(point)
        if hasattr(point, "model_dump"):
            return point.model_dump()
        if hasattr(point, "dict"):
            return point.dict()
        return dict(point)

    history_by_handle = {}
    try:
        history_snapshots = list(getattr(sess, "marey_history_snapshots", []) or [])
        history_by_handle = _extract_trajectories(history_snapshots, env=env)
    except Exception:
        history_by_handle = {}

    agents_data = {}
    
    forecast_by_handle = baseline_opt.trajectories or {}
    all_handle_keys = sorted(
        set(str(k) for k in forecast_by_handle.keys()) |
        set(str(k) for k in history_by_handle.keys()),
        key=lambda x: int(x) if str(x).isdigit() else str(x),
    )

    for handle_str in all_handle_keys:
        traj_points = forecast_by_handle.get(handle_str) or []
        handle = int(handle_str)
        
        def _point_value(point, name, default=None):
            if isinstance(point, dict):
                return point.get(name, default)
            return getattr(point, name, default)

        def _taken_out_dir(current_point, next_point):
            """Derive the actual outgoing direction from the next position."""
            if next_point is None:
                return None
            try:
                r0 = int(_point_value(current_point, "row"))
                c0 = int(_point_value(current_point, "col"))
                r1 = int(_point_value(next_point, "row"))
                c1 = int(_point_value(next_point, "col"))
            except (TypeError, ValueError):
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
            return None

        def _marey_svg_for_cell(row, col):
            """
            Resolve the SVG file name for a rail cell using the same tile
            resolver as the Flatland map serialization.
            """
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
                # Keep the same fallback as build_rail_tiles().
                return "Gleis_horizontal.svg"

            svg, _rot = resolved
            return svg

        def _enrich_forecast_points(points, handle):
            enriched = []
            points = list(points or [])
            for idx, point in enumerate(points):
                step = _point_value(point, "step")
                row = _point_value(point, "row")
                col = _point_value(point, "col")
                direction = _point_value(point, "dir", _point_value(point, "direction"))

                if row is None or col is None or direction is None:
                    continue

                try:
                    step_i = int(step) if step is not None else None
                    row_i = int(row)
                    col_i = int(col)
                    dir_i = int(direction)
                except (TypeError, ValueError):
                    continue

                next_point = points[idx + 1] if idx + 1 < len(points) else None
                taken_out_dir = _taken_out_dir(point, next_point)
                marey_svg = _marey_svg_for_cell(row_i, col_i)

                base = {
                    "step": step_i,
                    "row": row_i,
                    "col": col_i,
                    "dir": dir_i,
                    "direction": dir_i,
                    "handle": int(handle),
                    "agent_id": int(handle),
                }

                try:
                    base.update(
                        classify_marey_point(
                            env,
                            row_i,
                            col_i,
                            dir_i,
                            step=step_i,
                            handle=int(handle),
                            taken_out_dir=taken_out_dir,
                            marey_svg=marey_svg,
                        )
                    )
                except Exception as exc:
                    # Keep /hmi/marey-data backwards compatible even if topology
                    # enrichment fails for a Flatland edge case.
                    base.update(
                        {
                            "marey_topology": "unknown",
                            "marey_svg": marey_svg,
                            "marey_debug": {
                                "pos": [row_i, col_i],
                                "dir": dir_i,
                                "step": step_i,
                                "handle": int(handle),
                                "transition_bits": None,
                                "possible_out_dirs": [],
                                "possible_transitions": [],
                                "backward_transitions": {},
                                "possible_in_dirs_for_out": {},
                                "classification_reason": f"topology enrichment failed: {type(exc).__name__}: {exc}",
                            },
                            "marey_switch": None,
                            "marey_merge": None,
                        }
                    )

                enriched.append(base)
            return enriched

        # Extract and enrich position (row, col, direction) from each point.
        forecast = _enrich_forecast_points(traj_points, handle)
        
        history = [
            _dump_trajectory_point(p)
            for p in (history_by_handle.get(str(handle)) or [])
            if int(_dump_trajectory_point(p).get("step", 0) or 0) <= elapsed
        ]

        agents_data[handle] = {
            "handle": handle,
            "history": history,
            "forecast": forecast,
            "override_active": handle in active_overrides,
            "current_step": elapsed,
        }
    
    return {"agents": agents_data, "elapsed": elapsed, "cached": True}


# ── bundle (still mock, used by some UI panels) ────────────────────


@router.get("/{session_id}/hmi", response_model=HmiBundle)
def get_bundle(session_id: str):
    return generate_bundle(session_id, _step_for(session_id))


@router.get("/{session_id}/hmi/debug")
def debug_hmi_state(session_id: str):
    """Debug endpoint: show cache state and override state."""
    from app.core.override_manager import override_manager
    
    sess = session_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    env = getattr(sess, "env", None)
    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0) if env else -1
    
    try:
        overrides = dict(override_manager.get_all(session_id))
    except Exception:
        overrides = {}
    
    import hashlib
    override_hash = hashlib.md5(
        str(sorted(overrides.items())).encode()
    ).hexdigest()[:8]
    
    return {
        "session_id": session_id,
        "elapsed_steps": elapsed,
        "overrides": overrides,
        "override_hash": override_hash,
        "env_exists": env is not None,
    }
