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


def _rollout_baseline(sess, enabled: set):
    """`(baseline_id, factory)` — what actually drives this session.

    A Director-driven session (`goal_directed`) rolls out its *committed
    Director plan* as the baseline (`director_replay_factory` —
    model-free replay on the fork), never a proxy policy. The
    scenario-policy fallback applies only before a plan is committed,
    and for ordinary sessions. May add to `enabled` when even the
    fallback needs repair.
    """
    baseline_id = getattr(sess, "policy", None) or "deadlock_avoidance"
    if baseline_id == "goal_directed":
        from app.policies.goal_directed_policy import director_replay_factory

        factory = director_replay_factory(sess.env)
        if factory is not None:
            return baseline_id, factory
    if baseline_id not in enabled:
        baseline_id = sorted(enabled)[0]
    factory = _policy_factory_for(baseline_id)
    if factory is None:
        baseline_id = "deadlock_avoidance"
        factory = _policy_factory_for("deadlock_avoidance")
        enabled.add(baseline_id)
    return baseline_id, factory


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


# ── contentions (live conflict forecast for Combined Actions) ──────


# Only the multi-agent kinds a coordinated action answers: a blocked queue,
# a face-to-face swap, or a deadlock cycle. Single-train events (malfunction,
# agent_done, overdue_arrival) are served by /hmi/impact and the notifications
# feed, not here.
_CONTENTION_KINDS = ("blocked", "swap_attempt", "deadlock_cycle")

# Forecast lookahead for the no-override branch. Modest, so one call stays
# cheap; the runner exits early when all agents are done anyway.
_CONTENTION_MAX_STEPS = 50


def _group_contentions(conflicts) -> list[dict]:
    """Merge forecast conflicts into contention groups.

    A group is the connected component of conflicts that share at least one
    contending handle: one stalled queue produces several `blocked` events
    (one per stopped train), each naming the whole contender set, and they
    must collapse into a single group the widget builds one package set from.

    This generalises the brief's "merge conflicts that share a position" —
    with path-overlap contenders the events sit at *different* positions but
    name the *same* trains, so position-merging would emit duplicate groups.
    Handle-merging is the correct generalisation and is what the brief's
    intent (one group per contention) amounts to here.

    Returns groups sorted most-urgent first (lowest step, then lowest handle).
    """
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Two passes, and the second one is not optional: a root found while the
    # unions are still being made goes stale the moment a later conflict joins
    # its component to another. Keying the groups during the first pass split
    # one contention across several groups — with a train in both, since its
    # handle is in each conflict it appears in. Union everything first, then
    # key by the settled root.
    relevant = [
        c for c in conflicts
        if c.kind in _CONTENTION_KINDS and len({int(h) for h in c.agents}) >= 2
        # a single stopped train is a delay, not a contention
    ]
    for c in relevant:
        agents = [int(h) for h in c.agents]
        for h in agents:
            union(agents[0], h)

    groups: dict[int, list] = {}
    for c in relevant:
        groups.setdefault(find(int(c.agents[0])), []).append(c)

    out: list[dict] = []
    for cs in groups.values():
        handles = sorted({int(h) for c in cs for h in c.agents})
        earliest = min(cs, key=lambda c: c.step)
        pos = earliest.position
        # Union of every conflict's contended_cells — the contention's window,
        # carried on each blocked event by the detector (info["contended_cells"]).
        # Empty for kinds that don't compute it (swap/deadlock); those keep a
        # null window downstream rather than a fabricated one.
        window: set = set()
        for c in cs:
            for cell in (c.info or {}).get("contended_cells", []) or []:
                window.add((int(cell[0]), int(cell[1])))
        out.append({
            "step": int(earliest.step),
            "position": [int(pos[0]), int(pos[1])] if pos is not None else None,
            "kind": earliest.kind,
            "handles": handles,
            "window": sorted([ [r, c] for (r, c) in window ]) if window else [],
        })
    out.sort(key=lambda g: (g["step"], g["handles"][0] if g["handles"] else 0))
    return out


# ── per-handle enrichment (Task 1: the four quantities) ───────────


def _station_label_map(sess) -> dict[tuple, str]:
    """cell (row, col) → station name, from the session's infrastructure scene.

    The scene's stations carry `name` + `x`/`y` (col = x, row = y — the same
    mapping `stations_from_scene` uses). Built once per call; empty when the
    session has no scene or the scene carries no station names. A contended
    cell that maps to no station is reported by its cell, never a fabricated
    name."""
    scene = getattr(sess, "infrastructure_scene", None)
    if not isinstance(scene, dict):
        return {}
    out: dict[tuple, str] = {}
    for st in scene.get("stations", []) or []:
        if not isinstance(st, dict):
            continue
        try:
            cell = (int(st["y"]), int(st["x"]))
            name = st.get("name")
            if name:
                out[cell] = str(name)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _location_for(window: list[tuple], station_labels: dict[tuple, str]) -> dict:
    """Where the contention bites, for the panel to say. A station name where
    the window overlaps a named station; otherwise the representative cell.
    Never invented: when neither holds, the cell is returned explicitly and
    `kind` says which."""
    if not window:
        return {"kind": "none", "name": None, "cell": None}
    rep = sorted(window)[0]
    # The *overlap*, not just the representative cell. A path-overlap window is
    # hundreds of cells wide, and its lexicographically smallest cell is a
    # corner of it — almost never a platform, so checking that one alone
    # reported `null` on scenes carrying 32 named stations.
    named = sorted(cell for cell in window if cell in station_labels)
    if named:
        # A window spanning several stations reports the first in reading
        # order; the cell is returned beside the name, so the panel is never
        # left with a label it cannot locate.
        at = named[0]
        return {
            "kind": "station",
            "name": station_labels[at],
            "cell": [int(at[0]), int(at[1])],
        }
    return {"kind": "cell", "name": None, "cell": [int(rep[0]), int(rep[1])]}


def _cell_of(agent) -> Optional[tuple]:
    """(row, col) of an agent, or None when off-map. Snapshot entries carry
    the same shape under ``pos``."""
    p = getattr(agent, "position", None)
    if p is None:
        return None
    return (int(p[0]), int(p[1]))


def _waypoint_nearest_cell(env, handle: int, target: tuple) -> Optional[int]:
    """Index into ``agent.waypoints`` of the stop cell nearest `target`
    (Manhattan), preferring a real stop with a latest_arrival over the bare
    origin/target. Returns None when the agent has no waypoints.

    `target` is a contended cell. Slack is the time-slip a train has at the
    *relevant* deadline — the one closest to where the contention bites — so
    the waypoint nearest the contended cell is the one whose
    ``latest_arrival`` slack is reported. Documented because "nearest" is a
    choice: an exact-cell match would almost never fire (trains rarely stop
    exactly on a conflict cell), and the target waypoint would report slack
    at the journey end, not at the contention. Manhattan distance on the
    grid is the stable, cheap proxy."""
    ag = env.agents[handle]
    wps = getattr(ag, "waypoints", None) or []
    if not wps:
        return None
    best_i, best_d = None, None
    for i, stop in enumerate(wps):
        if not stop:
            continue
        pos = stop[0].position if hasattr(stop[0], "position") else None
        if pos is None:
            continue
        cell = (int(pos[0]), int(pos[1]))
        d = abs(cell[0] - target[0]) + abs(cell[1] - target[1])
        if best_d is None or d < best_d:
            best_i, best_d = i, d
    return best_i


def _slack_at(env, handle: int, target: tuple, elapsed: int) -> dict:
    """Slack (steps) at the waypoint nearest `target`: that waypoint's
    ``latest_arrival`` minus the current elapsed step. Negative = already
    overdue at that stop. ``null`` + ``unavailable_reason`` when not derivable
    (no waypoints, or the chosen waypoint carries no latest_arrival).

    Reuses the per-stop time-window arrays the env already carries
    (``waypoints_latest_arrival``), the same source `serializer.py` reads —
    no second source of truth."""
    ag = env.agents[handle]
    wps = getattr(ag, "waypoints", None) or []
    if not wps:
        return {"value": None, "unavailable_reason": "no_waypoints"}
    idx = _waypoint_nearest_cell(env, handle, target)
    if idx is None:
        return {"value": None, "unavailable_reason": "no_stop_cell"}
    wlas = getattr(ag, "waypoints_latest_arrival", None) or []
    if idx >= len(wlas):
        return {"value": None, "unavailable_reason": "no_time_window"}
    latest = wlas[idx]
    if latest is None:
        return {"value": None, "unavailable_reason": "no_latest_arrival"}
    return {"value": int(latest) - int(elapsed), "unavailable_reason": None}


def _enrich_handles(
    handles: list[int],
    window: list[tuple],
    result,
    env,
    elapsed: int,
) -> dict[int, dict]:
    """The four quantities per handle, all derived from the one forecast
    `result` (BranchResult: snapshots + agent_outcomes) plus the live env for
    the waypoint time-windows — no second run_branch.

    baselineOrder / headway — measured against `window`, the contended cell
    set carried on the conflict events (the same path-overlap that defined
    the contention). `baselineOrder` is the order in which each handle first
    enters any window cell; `headway` is how many steps it occupies window
    cells (first entry to last presence). A handle that never enters a window
    cell within the horizon gets null + unavailable_reason — never a silent
    zero (a fabricated zero is worse than a missing field).

    entryDelay — the existing serializer.py formula (steps overdue vs.
    latest_arrival; 0 while not overdue or already arrived). `agent_outcomes`
    already computes exactly this — reused directly, nothing re-derived.

    slack — `_slack_at` at the waypoint nearest the window's representative
    cell; null + reason when not derivable.
    """
    window_set = {(int(r), int(c)) for r, c in window}
    rep = window_set and sorted(window_set)[0]  # representative cell, stable

    # First/last window-cell presence per handle, from the branch snapshots.
    first_enter: dict[int, int] = {}
    last_present: dict[int, int] = {}
    for snap in result.snapshots:
        step = int(snap.get("step", 0))
        agents = snap.get("agents", {})
        for h in handles:
            a = agents.get(h)
            if not a:
                continue
            pos = a.get("pos")
            if pos is None:
                continue
            cell = (int(pos[0]), int(pos[1]))
            if cell not in window_set:
                continue
            if h not in first_enter:
                first_enter[h] = step
            last_present[h] = step

    out: dict[int, dict] = {}
    for h in handles:
        entry = first_enter.get(h)
        last = last_present.get(h)
        if entry is None:
            baseline_order = {"value": None, "unavailable_reason": "never_enters_window"}
            headway = {"value": None, "unavailable_reason": "never_enters_window"}
        else:
            baseline_order = {"value": int(entry), "unavailable_reason": None}
            headway = {"value": int(last - entry), "unavailable_reason": None}

        ao = result.agent_outcomes.get(h) or {}
        entry_delay = {"value": int(ao.get("delay", 0)), "unavailable_reason": None}

        slack = (
            _slack_at(env, h, rep, elapsed) if rep is not None
            else {"value": None, "unavailable_reason": "no_window"}
        )

        out[h] = {
            "agentHandle": int(h),
            "baselineOrder": baseline_order,
            "headway": headway,
            "entryDelay": entry_delay,
            "slack": slack,
        }
    return out


@router.get("/{session_id}/hmi/contentions")
def get_contentions(session_id: str):
    """The train-contentions ahead, for the Combined Actions panel to build
    its packages from.

    Runs a no-override forecast branch (the predicted course of the network
    from the current step) and returns the multi-agent conflicts it hits,
    grouped into contention groups most-urgent first, plus the **forecast
    budget** the panel states on screen. Each group carries, additively to
    `handles` (which stays unchanged for the existing variant):

      * `window`        — the contended cell set (the same path-overlap that
                           defined the contention; never a position guessed
                           downstream),
      * `location`       — a station name where the window overlaps one, else
                           the representative cell; never invented,
      * `perHandle`      — the four derived quantities per handle, all from
                           the one forecast `result` (no second run_branch):
        - `baselineOrder` — step the handle first enters a window cell,
        - `headway`       — steps it occupies window cells,
        - `entryDelay`    — overdue steps vs. latest_arrival (the existing
                             serializer.py formula; agent_outcomes already
                             computes it),
        - `slack`         — latest_arrival at the waypoint nearest the window
                             minus elapsed.
        Each is `{value, unavailable_reason}` — a quantity not derivable in
        the horizon is `null` with a reason, never a silent zero.

        {"horizonSteps": 50, "groups": [{
          "step": 18, "position": [2, 124], "kind": "blocked",
          "handles": [5, 8, 10],
          "window": [[2, 124]],
          "location": {"kind": "station", "name": "Olten", "cell": [2, 124]},
          "perHandle": [{
            "agentHandle": 5,
            "baselineOrder": {"value": 16, "unavailable_reason": null},
            "headway": {"value": 3, "unavailable_reason": null},
            "entryDelay": {"value": 0, "unavailable_reason": null},
            "slack": {"value": 12, "unavailable_reason": null}
          }]
        }]}

    `horizonSteps` is the compute budget the forecast ran with — how far
    `run_branch` looked ahead. It is *not* a reliability statement (the
    strategy-forecast panel's load-shrinking `horizonMinutes` is that); the two
    are deliberately different things (spec §8). The frontend renders it in
    minutes via the shared `MINUTES_PER_STEP` convention so the panel says how
    far ahead it looked in the operator's unit. All times at this boundary are
    in simulation steps; the frontend converts. Train names stay frontend —
    handles are returned as `agentHandle`, never a service name.

    Empty groups — not an error — when the network has no contentions ahead,
    and on any forecast failure (a forecast must never break the panel).
    `horizonSteps` is returned even then, so the panel can state its lookahead
    regardless of whether this step found a contention. Memoised per
    (session_id, current_step) so repeated polls within one step are free.
    """
    from app.core.contention_cache import contention_cache
    from app.core.scenario_runner import TrajectoryBranchRunner

    def _empty() -> dict:
        return {"horizonSteps": _CONTENTION_MAX_STEPS, "groups": []}

    sess = session_manager.get(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    env = getattr(sess, "env", None)
    if env is None:
        return _empty()

    elapsed = int(getattr(env, "_elapsed_steps", 0) or 0)
    cached = contention_cache.get(session_id, elapsed)
    if cached is not None:
        return cached

    try:
        # Baseline = what actually drives the session (Director plan replay
        # for goal_directed sessions — see _rollout_baseline). The forecast
        # is the predicted course under that policy, overrides ignored by
        # design (a coordinated action answers an upcoming contention, not a
        # past operator stop).
        enabled = set(getattr(sess, "enabled_scenario_policies", set(_ALL_POLICIES.keys())))
        enabled = {pid for pid in enabled if pid in _ALL_POLICIES}
        if not enabled:
            enabled = {"deadlock_avoidance"}
        _, baseline_factory = _rollout_baseline(sess, enabled)

        runner = TrajectoryBranchRunner(env, baseline_factory)
        result = runner.run_branch(overrides={}, max_steps=_CONTENTION_MAX_STEPS)
        groups = _group_contentions(result.conflicts)

        # Additive enrichment (Task 1 + Task 2): per group, a `location` and a
        # `perHandle` block with the four derived quantities. `handles` is left
        # unchanged so the existing Combined Actions variant keeps working off
        # the same field; the enrichment rides alongside. All times are in
        # simulation steps at the API boundary — the frontend renders minutes
        # via the shared MINUTES_PER_STEP convention. Train names stay frontend:
        # every handle is returned as `agentHandle`, never a service name.
        station_labels = _station_label_map(sess)
        for g in groups:
            window = [(int(r), int(c)) for r, c in g.get("window", []) or []]
            g["location"] = _location_for(window, station_labels)
            g["perHandle"] = list(_enrich_handles(
                g["handles"], window, result, env, elapsed,
            ).values())
    except Exception as e:
        _perf_log.warning("Contentions forecast failed for %s: %r", session_id, e)
        return _empty()

    payload = {"horizonSteps": _CONTENTION_MAX_STEPS, "groups": groups}
    contention_cache.put(session_id, elapsed, payload)
    return payload


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

    # Baseline = what actually drives the session (Director plan replay
    # for goal_directed sessions — see _rollout_baseline).
    baseline_id, baseline_factory = _rollout_baseline(sess, enabled)

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
    guarantee: bool = Query(False),
):
    """Surface the top-scoring alternative policy as a Recommendation,
    only if it clearly beats the current baseline. Empty list otherwise
    — that's the right signal: 'current policy is fine'.

    ``guarantee=true`` (guided demo / study): never leave the panel silently
    empty — if nothing beats the baseline by the margin, surface the best
    deadlock-free alternative anyway so there is always a decision moment."""
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

    baseline_id, baseline_factory = _rollout_baseline(sess, enabled)

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
        return real_recommendations(session_id, scenarios, guarantee=guarantee)
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

    return real_recommendations(session_id, scenarios, guarantee=guarantee)


@router.get("/{session_id}/hmi/marey-data")
def get_marey_data(
    session_id: str,
    kpi_time: float = Query(1.0, ge=0.0, le=1.0, description="KPI priority: time"),
    kpi_energy: float = Query(0.5, ge=0.0, le=1.0, description="KPI priority: energy"),
    kpi_platform: float = Query(0.5, ge=0.0, le=1.0, description="KPI priority: platform routing"),
    kpi_train: float = Query(0.5, ge=0.0, le=1.0, description="KPI priority: train routing"),
):
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
    from app.core.scenario_builder import scoring_weights_from_kpi
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
    # The KPI weights are part of the key in /hmi/scenarios, so they must be here
    # too — without them this endpoint can never hit the entry that endpoint wrote.
    weights = scoring_weights_from_kpi(kpi_time, kpi_energy, kpi_platform, kpi_train)
    kpi_hash = hashlib.md5(
        f"{weights.done:.3f}:{weights.delay:.3f}:{weights.deadlock:.3f}".encode()
    ).hexdigest()[:6]
    cache_key_str = f"{elapsed * 1000 + horizon}:{override_hash}:{kpi_hash}"
    
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
