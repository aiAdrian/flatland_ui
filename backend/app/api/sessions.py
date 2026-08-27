import asyncio

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
import logging
import time
from typing import Any, List

from app.core.session_manager import session_manager
from app.core.infrastructure_scene_adapter import build_scene_diagnostics, count_routable_agents
from app.core.serializer import serialize_env
from app.core.ws_manager import ws_manager
from app.core.override_manager import override_manager
from app.core.notification_manager import notification_manager
from app.core.learning_moments import learning_moment_store
from app.core.marey_history import capture_marey_history_snapshot, reset_marey_history
from app.core.scenario_presets import get_preset, list_presets
from app.models.session import (
    SessionCreateRequest,
    SessionInfo,
    StepRequest,
)
from app.models.agent import ActionRequest
from app.policies.override_policy import OverridePolicy
from app.policies.registry import create_runtime_policy, scenario_policy_factories, policy_specs

_perf_log = logging.getLogger("flatland.perf")
_perf_log.setLevel(logging.INFO)
if not _perf_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _perf_log.addHandler(_h)

router = APIRouter()


def _to_plain(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return float(value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float, str)):
        return value
    try:
        return float(value)
    except Exception:
        return str(value)



def _agent_state_name(agent) -> str:
    state = getattr(agent, "state", None)
    return getattr(state, "name", str(state))


def _capture_marey_history_snapshot(session) -> None:
    """Capture one real executed env state for Marey history.

    Stored shape intentionally matches Scenario/Conflict snapshots:
      {"step": int, "agents": {"0": {"pos": [r,c], "dir": d, "state": "MOVING"}}}
    """
    env = getattr(session, "env", None)
    if env is None:
        return

    try:
        step = int(getattr(env, "_elapsed_steps", 0) or 0)
    except Exception:
        step = 0

    agents: dict[str, dict] = {}

    for handle, agent in enumerate(getattr(env, "agents", []) or []):
        pos = getattr(agent, "position", None)
        direction = getattr(agent, "direction", None)

        # Off-map agents cannot produce a Marey path cell.
        if pos is None or direction is None:
            continue

        try:
            row, col = int(pos[0]), int(pos[1])
            dir_i = int(direction)
        except Exception:
            continue

        agents[str(handle)] = {
            "pos": [row, col],
            "dir": dir_i,
            "state": _agent_state_name(agent),
        }

    snap = {"step": step, "agents": agents}

    hist = list(getattr(session, "marey_history_snapshots", []) or [])

    # Avoid duplicate snapshots for repeated polling/state calls at same step.
    if hist and int(hist[-1].get("step", -1)) == step:
        hist[-1] = snap
    else:
        hist.append(snap)

    session.marey_history_snapshots = hist


def _is_done(env) -> bool:
    try:
        if env._elapsed_steps >= env._max_episode_steps:
            return True
    except Exception:
        pass
    try:
        return all(getattr(a.state, "name", str(a.state)) == "DONE" for a in env.agents)
    except Exception:
        return False


def _build_state_payload(session_id: str, env) -> dict:
    overrides = override_manager.get_all(session_id)
    state = serialize_env(env, overrides=overrides)
    state["episode_done"] = _is_done(env)
    return {"type": "state", "session_id": session_id, "state": state}


async def _broadcast_state(session_id: str, env):
    try:
        await ws_manager.broadcast(session_id, _build_state_payload(session_id, env))
    except Exception:
        pass


def _build_policy(session_id: str, env, policy_name: str):
    """Build a policy + wrap in OverridePolicy.

    R1: hybrid Policy interface — call policy.reset(env) so stateful
    heuristics (DLA later) get an env reference."""
    try:
        default = create_runtime_policy(policy_name, env)
    except KeyError:
        raise HTTPException(400, f"Unknown policy: {policy_name}")
    wrapped = OverridePolicy(default, session_id)
    wrapped.reset(env)
    return wrapped


def _scene_counts(infrastructure_scene: dict[str, Any]) -> dict[str, int]:
    cells = [cell for cell in infrastructure_scene.get("cells", []) if isinstance(cell, dict)]
    agents = [agent for agent in infrastructure_scene.get("agents", []) if isinstance(agent, dict)]
    return {
        "cells": len(cells),
        "switches": sum(1 for cell in cells if cell.get("kind") == "switch"),
        "agents": len(agents),
        "routable_agents": count_routable_agents(infrastructure_scene),
    }


@router.post("", response_model=SessionInfo)
def create_session(req: SessionCreateRequest):
    scenario_preset_id = req.scenario_preset_id or None
    if scenario_preset_id:
        # Prebuilt scenario preset (e.g. ECML 2026): env is loaded from file,
        # generation params and any scene are ignored. Validate up front so the
        # UI gets a clean 400 rather than a 500 from the loader.
        try:
            get_preset(scenario_preset_id)
        except (KeyError, FileNotFoundError) as e:
            raise HTTPException(400, str(e))
        _perf_log.info("[INFRA] create requested mode=preset id=%s", scenario_preset_id)
        session = session_manager.create(
            seed=req.seed,
            enabled_policy_ids=req.enabled_policy_ids,
            enabled_scenario_policy_ids=req.enabled_scenario_policy_ids,
            scenario_preset_id=scenario_preset_id,
        )
        _perf_log.info(
            "[INFRA] create built session=%s mode=preset id=%s env=%sx%s agents=%s",
            session.id,
            scenario_preset_id,
            session.env.width,
            session.env.height,
            len(session.env.agents),
        )
        return SessionInfo(
            id=session.id,
            width=session.env.width,
            height=session.env.height,
            num_agents=len(session.env.agents),
            scenario_preset_id=scenario_preset_id,
        )

    infrastructure_scene = req.infrastructure_scene or None
    infrastructure_grid = infrastructure_scene.get("grid", {}) if isinstance(infrastructure_scene, dict) else {}
    width = int(infrastructure_grid.get("width", req.width)) if infrastructure_grid else req.width
    height = int(infrastructure_grid.get("height", req.height)) if infrastructure_grid else req.height
    if isinstance(infrastructure_scene, dict):
        number_of_agents = count_routable_agents(infrastructure_scene)
        if number_of_agents < 1:
            raise HTTPException(400, "Selected infrastructure scene has no trains with start and target.")
    else:
        number_of_agents = req.number_of_agents

    if isinstance(infrastructure_scene, dict):
        counts = _scene_counts(infrastructure_scene)
        _perf_log.info(
            "[INFRA] create requested mode=scene id=%s name=%s grid=%sx%s cells=%s switches=%s agents=%s routable=%s",
            infrastructure_scene.get("id"),
            infrastructure_scene.get("name"),
            width,
            height,
            counts["cells"],
            counts["switches"],
            counts["agents"],
            counts["routable_agents"],
        )
    else:
        _perf_log.info(
            "[INFRA] create requested mode=random grid=%sx%s agents=%s seed=%s",
            width,
            height,
            number_of_agents,
            req.seed,
        )

    session = session_manager.create(
        width=width,
        height=height,
        number_of_agents=number_of_agents,
        seed=req.seed,
        max_num_cities=req.max_num_cities,
        max_rails_between_cities=req.max_rails_between_cities,
        max_rail_pairs_in_city=req.max_rail_pairs_in_city,
        max_episode_steps=req.max_episode_steps,
        latest_departure_max=req.latest_departure_max,
        speed_profile=req.speed_profile,
        line_length=req.line_length,
        malfunction_rate=req.malfunction_rate,
        malfunction_min_duration=req.malfunction_min_duration,
        malfunction_max_duration=req.malfunction_max_duration,
        enabled_policy_ids=req.enabled_policy_ids,
        enabled_scenario_policy_ids=req.enabled_scenario_policy_ids,
        infrastructure_scene=infrastructure_scene,
    )
    _capture_marey_history_snapshot(session)

    diagnostics = build_scene_diagnostics(infrastructure_scene, session.env)
    if diagnostics is not None:
        _perf_log.info(
            "[INFRA] create built session=%s scene=%s env=%sx%s agents=%s cells=%s/%s switches=%s/%s mismatches=%s unknown_tiles=%s",
            session.id,
            getattr(session, "infrastructure_scene_id", None),
            session.env.width,
            session.env.height,
            len(session.env.agents),
            diagnostics.get("rail_cell_count"),
            diagnostics.get("scene_cell_count"),
            diagnostics.get("rail_switch_tile_count"),
            diagnostics.get("scene_switch_count"),
            diagnostics.get("mismatched_cell_count"),
            diagnostics.get("unknown_tile_count"),
        )
    else:
        _perf_log.info(
            "[INFRA] create built session=%s mode=random env=%sx%s agents=%s",
            session.id,
            session.env.width,
            session.env.height,
            len(session.env.agents),
        )

    return SessionInfo(
        id=session.id,
        width=session.env.width,
        height=session.env.height,
        num_agents=len(session.env.agents),
        infrastructure_scene_id=getattr(session, "infrastructure_scene_id", None),
    )


@router.get("")
def list_sessions() -> List[str]:
    return session_manager.list_ids()


@router.get("/scenario-presets")
def get_scenario_presets() -> List[dict]:
    """Prebuilt scenario presets (e.g. ECML 2026 scenes) for the UI picker."""
    return list_presets()


@router.get("/{session_id}/state")
def get_state(session_id: str):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    overrides = override_manager.get_all(session_id)
    state = serialize_env(session.env, overrides=overrides)
    state["episode_done"] = _is_done(session.env)
    state["infrastructure_scene_id"] = getattr(session, "infrastructure_scene_id", None)
    state["infrastructure_scene_diagnostics"] = build_scene_diagnostics(
        getattr(session, "infrastructure_scene", None),
        session.env,
    )
    return state


@router.post("/{session_id}/step")
async def step(session_id: str, req: StepRequest):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    env = session.env

    if _is_done(env):
        return {
            "session_id": session_id,
            "elapsed_steps": int(env._elapsed_steps),
            "rewards": {},
            "dones": {"__all__": True},
            "all_done": True,
            "episode_done": True,
            "message": "Episode finished. Use 'Reset' to start again.",
        }

    enabled = set(getattr(session, "enabled_policy_ids", set()))
    if req.policy not in enabled:
        raise HTTPException(400, f"Policy '{req.policy}' is not enabled for this session")

    policy = _build_policy(session_id, env, req.policy)
    # Track the most recently used policy so /hmi/scenarios can
    # use it as baseline.
    session.policy = req.policy

    rewards = {}
    dones = {}
    all_done = False

    t_total0 = time.perf_counter()
    n_done_steps = 0

    for _ in range(req.n_steps):
        if _is_done(env):
            all_done = True
            break
        handles = env.get_agent_handles()
        observations: dict[int, Any] = session.last_observations or {}
        policy.start_step()
        actions = policy.act_many(handles, observations)
        try:
            next_obs, rewards, dones, info = env.step(actions)
        except Exception as e:
            if "Episode is done" in str(e):
                policy.end_step()
                all_done = True
                break
            raise
        policy.end_step()
        session.last_observations = next_obs
        session.last_info = info
        # Capture exact executed state for Marey history.
        _capture_marey_history_snapshot(session)
        n_done_steps += 1
        if dones.get("__all__", False):
            all_done = True
            break

    t_total_ms = (time.perf_counter() - t_total0) * 1000
    t_ser0 = time.perf_counter()
    await _broadcast_state(session_id, env)
    t_ser_ms = (time.perf_counter() - t_ser0) * 1000

    n_agents = len(env.get_agent_handles())
    avg_ms = t_total_ms / max(n_done_steps, 1)
    _perf_log.info(
        f"[STEP] requested={req.n_steps} done={n_done_steps} agents={n_agents} "
        f"total={t_total_ms:.1f}ms avg={avg_ms:.1f}ms/step "
        f"final_broadcast={t_ser_ms:.1f}ms"
    )

    return {
        "session_id": session_id,
        "elapsed_steps": int(env._elapsed_steps),
        "rewards": _to_plain(rewards),
        "dones": _to_plain(dones),
        "all_done": bool(all_done),
        "episode_done": _is_done(env),
    }


@router.post("/{session_id}/reset")
async def reset_session(session_id: str):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    # Replay the IDENTICAL scenario (same rail, schedule, malfunctions) so a
    # Reset — and each guided-demo mode switch — restarts the same situation,
    # instead of env.reset() rolling a fresh random episode.
    if session.seed is not None:
        obs, info = session.env.reset(
            regenerate_rail=False, regenerate_schedule=False, random_seed=session.seed
        )
    else:
        obs, info = session.env.reset()
    # Flatland's reset() overwrites _max_episode_steps; re-apply the session's.
    if session.max_episode_steps:
        session.env._max_episode_steps = session.max_episode_steps
    session.last_observations = obs
    session.last_info = info
    session.marey_history_snapshots = []
    _capture_marey_history_snapshot(session)
    override_manager.clear_all(session_id)
    notification_manager.clear_session(session_id)
    # The moments belong to the episode that just ended, not to the next one.
    learning_moment_store.clear_session(session_id)

    await _broadcast_state(session_id, session.env)

    return {"session_id": session_id, "reset": True, "elapsed_steps": 0}


@router.post("/{session_id}/action")
async def manual_action(session_id: str, req: ActionRequest):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    env = session.env
    if _is_done(env):
        raise HTTPException(409, "Episode is done, cannot apply action")
    next_obs, rewards, dones, info = env.step({req.handle: req.action})
    session.last_observations = next_obs
    session.last_info = info
    # Capture manual action state for Marey history.
    _capture_marey_history_snapshot(session)

    await _broadcast_state(session_id, env)

    return {
        "session_id": session_id,
        "handle": req.handle,
        "action": req.action,
        "elapsed_steps": int(env._elapsed_steps),
        "all_done": bool(dones.get("__all__", False)),
    }


@router.delete("/{session_id}")
def delete_session(session_id: str):
    if not session_manager.delete(session_id):
        raise HTTPException(404, f"Session {session_id} not found")
    override_manager.clear_all(session_id)
    notification_manager.clear_session(session_id)
    learning_moment_store.clear_session(session_id)
    _STRATEGY_CACHE.pop(session_id, None)
    return {"deleted": session_id}


# ── POST /session/{id}/policy: set active policy without stepping ──
class PolicyChangeRequest(BaseModel):
    policy: str


class ScenarioPoliciesUpdateRequest(BaseModel):
    # Backwards-compatible: enabled_ids means scenario policies.
    enabled_ids: list[str] | None = None
    enabled_policy_ids: list[str] | None = None


@router.post("/{session_id}/policy")
def set_session_policy(session_id: str, req: PolicyChangeRequest):
    """Switch the active policy for a session without stepping.
    Subsequent steps and /hmi/scenarios use this as baseline."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    enabled = set(getattr(session, "enabled_policy_ids", set()))
    if req.policy not in enabled:
        raise HTTPException(400, f"Policy '{req.policy}' is not enabled for this session")
    session.policy = req.policy
    _invalidate_scenario_forecasts(session_id)
    return {"session_id": session_id, "policy": session.policy}


def _invalidate_scenario_forecasts(session_id: str) -> None:
    """Drop the session's cached scenario forecasts so the next
    /hmi/scenarios call recomputes them — required whenever what drives
    the session changes without a step (policy switch, committed re-plan,
    enabled-policy change)."""
    try:
        from app.core.scenario_cache import scenario_cache
        scenario_cache.clear_session(session_id)
    except Exception:
        pass
    # Same reasoning for the strategy answers: they compare each focus against
    # the plan that drives, so a changed plan invalidates them too. The key check
    # would catch it, but dropping it here keeps stale payloads from lingering.
    _STRATEGY_CACHE.pop(session_id, None)


# ── Director-mode planner dials (goal_directed policy) ──
class DirectorWeightsBody(BaseModel):
    punctuality: float
    connections: float
    stability: float


class DirectorWeightsRequest(DirectorWeightsBody):
    # Plan under the new dials NOW (blocking for the planning duration)
    # instead of lazily on the next step — the map overlay wants the new
    # paths the moment the slider settles.
    plan: bool = False


@router.post("/{session_id}/director/weights")
def set_director_weights_for_session(
    session_id: str, req: DirectorWeightsRequest
):
    """Set this session's Director dials.

    Default: the next `goal_directed` step re-plans under the new
    weights (from scratch before the first step, from the current state
    mid-episode). With `plan: true` that happens right here — the
    response then carries the fresh plan and its drawable paths, so the
    HMI can update its overlay instantly.
    """
    from app.policies.goal_directed_policy import (
        GoalDirectedPolicy,
        plan_info,
        plan_paths,
        plan_player,
        replan_now,
        set_env_weights,
    )

    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    try:
        set_env_weights(
            session.env, req.punctuality, req.connections, req.stability
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    replanned = False
    if req.plan:
        if plan_player(session.env) is None:
            # Not planned yet (or dropped at step zero): plan from scratch.
            GoalDirectedPolicy(session.env)
            replanned = plan_info(session.env) is not None
        else:
            # Running episode: residual re-plan from the current state,
            # ungated — the user changed the objective.
            replanned = (
                replan_now(session.env, reason="weights change", gate=False)
                is not None
            )
        if replanned:
            _invalidate_scenario_forecasts(session_id)
    return {
        "session_id": session_id,
        "weights": {
            "punctuality": req.punctuality,
            "connections": req.connections,
            "stability": req.stability,
        },
        "replanned": replanned,
        "plan": plan_info(session.env) if req.plan else None,
        "paths": plan_paths(session.env) if req.plan else None,
    }


# The three strategy focuses the Director offers as A/B/C tiles. Each is a
# dial preset that wins on exactly one axis and pays for it on the others —
# no dominated option, so the choice is a genuine trade-off rather than a
# quality ranking. Points are the same 0–5 grid the dials use.
def _divergence(current: list | None, option: list | None) -> dict | None:
    """Where an option's route differs from the plan that is driving.

    Drawing each option's *full* planned routes was unusable: nearly every train
    gets re-planned, so the map filled with 7–8 dashed lines spanning the whole
    grid — and they were almost identical between the options, because most
    trains keep their path. The only informative part is the stretch where the
    new plan deviates.

    Two kinds of difference, and they need different marks:

    - **reroute** — the cell sequence differs. Returns just the deviating
      stretch, with one cell of context on each side so it visibly branches off
      and rejoins.
    - **hold** — the cells are identical but the option arrives later: the train
      waits rather than taking another route. A line cannot show that; the
      caller marks the spot instead.

    Returns None when the option changes nothing for this train.
    """
    cur = [(int(p["row"]), int(p["col"])) for p in (current or [])]
    opt = [(int(p["row"]), int(p["col"])) for p in (option or [])]
    if not opt:
        return None

    if cur == opt[: len(cur)] or opt == cur[: len(opt)]:
        # Same route as far as both go → the only possible difference is timing.
        if current and option:
            delay = int(option[0].get("step", 0)) - int(current[0].get("step", 0))
            if delay >= 1:
                return {
                    "kind": "hold",
                    "steps": delay,
                    "row": int(option[0]["row"]),
                    "col": int(option[0]["col"]),
                }
        return None

    first = next(
        (i for i in range(min(len(cur), len(opt))) if cur[i] != opt[i]),
        min(len(cur), len(opt)),
    )
    # Last index at which they still differ, so a detour that rejoins is cut off
    # at the merge point instead of running to the end of the plan.
    last = first
    for i in range(min(len(cur), len(opt))):
        if cur[i] != opt[i]:
            last = i
    if len(opt) > len(cur):
        last = len(opt) - 1

    start = max(0, first - 1)
    end = min(len(opt) - 1, last + 1)
    stretch = option[start : end + 1]
    if len(stretch) < 2:
        return None
    # The branch point is what the map marks by default. Measured on the demo
    # environment, the deviating stretches run 19–96 cells: these options are not
    # small detours but substantially different routes, so drawing them all as
    # lines is unreadable however well they are filtered. One mark per train at
    # the cell where it starts to differ is the readable minimum; the stretch
    # itself is drawn only for the train the operator points at.
    branch = option[first] if first < len(option) else stretch[0]
    return {
        "kind": "reroute",
        "points": stretch,
        "branch": {
            "row": int(branch["row"]),
            "col": int(branch["col"]),
            "step": int(branch.get("step", 0)),
        },
    }


def _schedule_entries(schedules: list, handle: int) -> tuple:
    """One train's schedule as a comparable tuple, or () when it has none.

    Schedules are absolute and origin-anchored (director-mode.md §2, invariant 5),
    so two schedules for the same train are directly comparable entry by entry.
    """
    for schedule in schedules or ():
        if int(schedule.handle) == int(handle):
            return tuple(
                (int(entry.node_id), int(entry.wait)) for entry in schedule.entries
            )
    return ()


_STRATEGY_CACHE: dict[str, tuple[tuple, dict]] = {}


def _strategy_cache_key(env, info: dict) -> tuple:
    """What makes a strategy answer valid: the state it was planned from, and the
    plan it was compared against. Both change → re-plan; neither → reuse."""
    return (
        int(getattr(env, "_elapsed_steps", 0) or 0),
        tuple(info.get("weights") or ()),
        info.get("source"),
        len(info.get("replans") or []),
    )


DIRECTOR_STRATEGY_PRESETS: list[dict[str, object]] = [
    {
        "id": "focus_delay",
        "ident": "A",
        "focus": "punctuality",
        "weights": {"punctuality": 5, "connections": 2, "stability": 2},
    },
    {
        "id": "focus_connections",
        "ident": "B",
        "focus": "connections",
        "weights": {"punctuality": 2, "connections": 5, "stability": 2},
    },
    {
        "id": "focus_stability",
        "ident": "C",
        "focus": "stability",
        "weights": {"punctuality": 2, "connections": 2, "stability": 5},
    },
]


@router.get("/{session_id}/director/activity")
def get_director_activity(session_id: str, limit: int = 12):
    """What the autonomous planner has actually been doing, newest first.

    Director mode's supervisory question is "what is the AI doing, and did it
    react to what just happened?" — and the answer already exists in the plan
    info: every committed decision (`trace`) and every mid-episode re-plan
    (`replans`, including the ones it decided *against*). None of it was
    reachable in the UI.

    A dedicated endpoint rather than reading `/director`: that response carries
    the full trace with every weighed option per decision — measured at
    **172 KB** for a 64-decision episode — which is far too much to poll for a
    feed that needs a handful of one-liners. Here the options are reduced to
    their count and the chosen branch, so the payload stays flat in the episode
    length.
    """
    from app.policies.goal_directed_policy import plan_info

    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    info = plan_info(session.env) or {}
    step = int(getattr(session.env, "_elapsed_steps", 0) or 0)
    entries: list[dict] = []

    for event in info.get("replans") or []:
        considered = event.get("considered") or {}
        entries.append({
            "kind": "replan",
            "step": int(event.get("step", 0)),
            "reason": event.get("reason"),
            # 'research' = the plan was replaced; 'continue' = it was kept, either
            # on score or because the paired rollout gate vetoed the switch.
            "verdict": event.get("source"),
            "gate": event.get("gate"),
            "changed": len(event.get("changed") or []),
            "scoreResearch": considered.get("research"),
            "scoreContinue": considered.get("continue"),
        })

    for item in info.get("trace") or []:
        options = item.get("options") or []
        chosen_idx = item.get("chosen")
        chosen = (
            options[chosen_idx]
            if isinstance(chosen_idx, int) and 0 <= chosen_idx < len(options)
            else None
        )
        entries.append({
            "kind": "decision",
            "step": int(round(float(item.get("time", 0) or 0))),
            "handle": item.get("handle"),
            "stuck": bool(item.get("stuck")) or chosen is None,
            "wait": (chosen or {}).get("wait"),
            "toNode": (chosen or {}).get("to_node"),
            "optionCount": len(options),
            "score": (chosen or {}).get("weighted"),
        })

    # The trace is a *plan*, not a log: each entry's `time` is the planned moment
    # of that decision, so entries beyond the current step have not happened yet.
    # Conflating the two would have shown "the AI just did X" for something
    # scheduled 30 steps into the future. Split instead — which turns one feed
    # into the two questions supervision actually asks: what did it just do, and
    # what is it about to do?
    cap = max(1, min(limit, 100))

    # Re-plans get their own channel rather than competing for slots in the
    # decision history. They are rare and they are the point: a disruption hits,
    # the planner weighs replacing the plan, and either commits or is vetoed by
    # the paired simulation. In a shared 6-entry window the single most
    # informative event of a run scrolled out within a few steps.
    replans = [e for e in entries if e["kind"] == "replan"]
    replans.sort(key=lambda e: e["step"], reverse=True)

    decisions = [e for e in entries if e["kind"] == "decision"]
    recent = sorted(
        (e for e in decisions if e["step"] <= step), key=lambda e: e["step"], reverse=True
    )
    upcoming = sorted((e for e in decisions if e["step"] > step), key=lambda e: e["step"])

    return {
        "session_id": session_id,
        "step": step,
        "source": info.get("source"),
        "totalDecisions": len(decisions),
        "totalReplans": len(replans),
        "replans": replans[:cap],
        "recent": recent[:cap],
        "upcoming": upcoming[:cap],
    }


@router.get("/{session_id}/director/strategies")
def get_director_strategies(session_id: str):
    """Plan the episode's remainder under each strategy focus — minimise
    delay / hold connections / maximise stability — and report what each
    focus promises plus its drawable reroute.

    This backs the A/B/C strategy tiles: the supervisory decision is which
    objective the autonomous plan should pursue, so each tile has to be
    answered by an actual plan under those dials, not by a label.

    Planning only, no forward simulation to the episode's end (that is what
    `/director/whatif` is for) — three residual plans are fast enough to
    answer while the operator is still looking at the tiles, and the
    per-axis utilities are the planner's own scores for the branch it would
    commit. Each focus is planned on its own fork; the live session and its
    committed plan are untouched.

    Degrades instead of failing: when the session has not planned yet or no
    models are installed, the presets come back with `available: false` and
    no numbers, so the tiles can still be offered as pure directives.
    """
    import copy

    from app.policies.goal_based_policies.schedule import SchedulePlayer
    from app.policies.goal_directed_policy import (
        loaded_models,
        plan_info,
        plan_player,
        plan_schedules,
    )

    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    # The running plan, so each focus can be read as a difference to what is
    # driving right now instead of as an absolute score in a vacuum.
    info = plan_info(session.env) or {}
    current = (
        {
            "source": info.get("source"),
            "weighted": info.get("weighted"),
            "utilities": info.get("utilities"),
            "reported": info.get("reported"),
        }
        if info.get("utilities")
        else None
    )

    def shell(reason: str | None = None) -> dict:
        return {
            "session_id": session_id,
            "step": int(getattr(session.env, "_elapsed_steps", 0) or 0),
            "available": reason is None,
            "reason": reason,
            "current": current,
            "strategies": [
                {
                    **preset, "plan": None, "paths": None,
                    "divergence": {"reroutes": {}, "holds": []},
                }
                for preset in DIRECTOR_STRATEGY_PRESETS
            ],
        }

    player = plan_player(session.env)
    schedules = plan_schedules(session.env)
    models = loaded_models()
    if player is None or schedules is None:
        return shell("No committed plan yet — step under 'goal_directed' first")
    if models is None:
        return shell("No models installed — strategy plans need them")

    # Imported only past the models gate: the ensemble pulls in torch, which a
    # model-free deployment does not have. Without this the "no models"
    # degradation would itself crash with an ImportError.
    from app.policies.goal_based_policies.ensemble import DirectorWeights
    from app.policies.goal_based_policies.replan import (
        apply_residual_plan,
        residual_plan,
    )
    from app.policies.goal_based_policies.search import _reported as _reported_figures
    from app.policies.goal_based_policies.search import director_plan

    # Three residual plans cost ~16s (measured), and an unchanged request costs
    # exactly the same again — which made re-entering Director, a second panel
    # instance or a stray refresh a 16s stall for an answer we already had.
    cache_key = _strategy_cache_key(session.env, info)
    cached = _STRATEGY_CACHE.get(session_id)
    if cached and cached[0] == cache_key:
        return {**cached[1], "cached": True}

    graph = player.graph
    snapshot = player.snapshot()
    handles = [int(schedule.handle) for schedule in schedules]
    # The plan that is driving, to diff each option against.
    live_paths = {h: player.future_path(h) for h in handles}
    # Before the first step there is no past to pin, and `director_plan` is the
    # planner the driving plan itself came from (`goal_directed_policy._plan`).
    # It is not interchangeable with `residual_plan`: only it runs the
    # **portfolio guarantee** — the searched plan is held against
    # `plan_all_lines` / `plan_avoiding_overlaps` under the same weighted score
    # (docs/reference/director-mode.md §3.7). Planning the options residually at
    # t=0 skipped that step, so an option could be offered that its own scorer
    # rates below the naive baseline — against a baseline plan that *did* get the
    # guarantee. That asymmetry is what let a focus come out worse on its own
    # axis than the plan already driving.
    at_start = int(getattr(session.env, "_elapsed_steps", 0) or 0) == 0

    out = []
    for preset in DIRECTOR_STRATEGY_PRESETS:
        w = preset["weights"]
        try:
            weights = DirectorWeights(
                w["punctuality"], w["connections"], w["stability"])
        except ValueError as e:  # pragma: no cover — presets are static
            raise HTTPException(500, str(e))

        fork = copy.deepcopy(session.env)
        fork_player = SchedulePlayer(graph, fork)
        fork_player.restore(snapshot)
        if at_start:
            plan = director_plan(fork, graph, weights, *models)
            # A full-horizon plan replaces the schedules outright; there is no
            # captured head to splice onto (§3.8 splices tails, §3.7 does not).
            for schedule in plan.schedules:
                fork_player.set_schedule(schedule)
            changed = sorted(
                handle for handle in handles
                if _schedule_entries(plan.schedules, handle)
                != _schedule_entries(schedules, handle)
            )
        else:
            plan = residual_plan(
                fork, graph, weights, *models,
                player=fork_player, schedules=schedules,
                reason=f"strategy-{preset['id']}",
            )
            if plan is None:
                out.append({
                    **preset, "plan": None, "paths": None,
                    "divergence": {"reroutes": {}, "holds": []},
                })
                continue
            apply_residual_plan(fork_player, plan)
            changed = sorted(plan.tails)
        option_paths = {h: fork_player.future_path(h) for h in handles}
        reroutes: dict[str, list] = {}
        holds: list[dict] = []
        for handle in handles:
            diff = _divergence(live_paths.get(handle), option_paths.get(handle))
            if diff is None:
                continue
            if diff["kind"] == "reroute":
                reroutes[str(handle)] = {
                    "branch": diff["branch"],
                    "points": diff["points"],
                }
            else:
                holds.append({
                    "handle": handle,
                    "row": diff["row"],
                    "col": diff["col"],
                    "steps": diff["steps"],
                })
        out.append({
            **preset,
            # The minimal honest overlay: only what this option changes.
            "divergence": {"reroutes": reroutes, "holds": holds},
            "plan": {
                "source": plan.source,
                "weighted": plan.score.weighted,
                "utilities": dict(plan.score.breakdown["utilities"]),
                # Display figures — see `search._reported`. The raw utilities stay
                # for the ranking; the tiles show these.
                "reported": _reported_figures(plan.score.breakdown),
                "changed": changed,
                # The planner's own comparison. At t=0 that is the portfolio
                # (search vs lines vs avoidance, §3.7); mid-episode it is
                # research vs continue. Forwarded because `source` alone hides
                # *how close* the call was — and a focus whose plan is really the
                # conflict-blind baseline is worth saying out loud.
                "considered": {k: float(v) for k, v in (plan.considered or {}).items()},
            },
            "paths": {str(handle): option_paths[handle] for handle in handles},
        })

    payload = {
        "session_id": session_id,
        "step": int(getattr(session.env, "_elapsed_steps", 0) or 0),
        "available": True,
        "reason": None,
        "current": current,
        "strategies": out,
    }
    _STRATEGY_CACHE[session_id] = (cache_key, payload)
    return {**payload, "cached": False}


@router.get("/{session_id}/director")
def get_director_state(session_id: str):
    """The session's dials and, once the policy has planned, the plan's
    provenance — source, weighted score, per-axis utilities — plus the
    plan's drawable per-train paths for the map overlay."""
    from app.policies.goal_directed_policy import (
        env_weights,
        plan_info,
        plan_paths,
    )

    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    punctuality, connections, stability = env_weights(session.env)
    return {
        "session_id": session_id,
        "weights": {
            "punctuality": punctuality,
            "connections": connections,
            "stability": stability,
        },
        "plan": plan_info(session.env),
        "paths": plan_paths(session.env),
    }


@router.post("/{session_id}/director/verify")
def verify_director_plan(session_id: str):
    """Ground-truth the committed plan: replay it on a pristine fork of
    the session's episode (persister clone + state-only reset — same
    rail, same timetable, step zero) and report what actually happens
    next to what the models predicted. The live session is not touched.
    """
    import tempfile
    import uuid as uuid_module
    from pathlib import Path as PathLib

    from flatland.envs.persistence import RailEnvPersister

    from app.policies.goal_based_policies.infrastructure_graph import (
        build_decision_point_graph,
    )
    from app.policies.goal_based_policies.search import verify_plan
    from app.policies.goal_based_policies.stations import resolve_stations
    from app.policies.goal_directed_policy import plan_info, plan_schedules

    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    schedules = plan_schedules(session.env)
    info = plan_info(session.env)
    if schedules is None or info is None:
        raise HTTPException(
            400, "No committed plan — step under 'goal_directed' first")

    with tempfile.TemporaryDirectory() as tmp:
        path = PathLib(tmp) / f"verify-{uuid_module.uuid4().hex}.pkl"
        RailEnvPersister.save(session.env, str(path))
        fork, _ = RailEnvPersister.load_new(str(path))
    fork.reset(regenerate_rail=False, regenerate_schedule=False)

    graph = build_decision_point_graph(fork)
    verified = verify_plan(fork, graph, resolve_stations(fork), schedules)
    return {
        "session_id": session_id,
        "predicted": {
            "weighted": info.get("weighted"),
            "utilities": info.get("utilities"),
            "source": info.get("source"),
        },
        "verified": verified,
    }


@router.post("/{session_id}/director/replan")
def replan_director_now(session_id: str):
    """Re-plan the episode's remainder from the current state, now, under
    the session's weights — the manual counterpart of the malfunction
    trigger. The result is spliced into the live plan only when it
    out-scores continuing; either way the verdict lands in the plan
    info's `replans` list."""
    from app.policies.goal_directed_policy import (
        plan_info,
        plan_paths,
        replan_now,
    )

    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    event = replan_now(session.env, reason="manual")
    if event is None:
        raise HTTPException(
            400,
            "Nothing to re-plan — needs a committed plan under "
            "'goal_directed' and installed models",
        )
    if event.get("source") == "research":
        _invalidate_scenario_forecasts(session_id)
    return {
        "session_id": session_id,
        "event": event,
        "plan": plan_info(session.env),
        "paths": plan_paths(session.env),
    }


@router.post("/{session_id}/director/whatif")
def director_what_if(session_id: str, req: DirectorWeightsBody):
    """What-if from the current state: on two forks of the live episode,
    simulate (a) continuing the committed plan and (b) re-planning under
    the candidate weights, both to the episode's end, and report the
    outcomes side by side. The A3S restore → simulate-forward → report
    contract (see `replan.py`), in-process; the live session is not
    touched, and both forks share the same future malfunction stream.

    Connection outcomes count station calls from the fork point (`step`)
    onward — calls that already happened are invisible to both branches
    alike, so the comparison stays fair.
    """
    import copy

    from app.policies.goal_based_policies.connections import (
        evaluate_connections,
        observed_times,
        planned_connections,
        station_watch_cells,
    )
    from app.policies.goal_based_policies.ensemble import DirectorWeights
    from app.policies.goal_based_policies.replan import (
        apply_residual_plan,
        residual_plan,
        simulate_forward,
    )
    from app.policies.goal_based_policies.schedule import SchedulePlayer
    from app.policies.goal_based_policies.stations import resolve_stations
    from app.policies.goal_directed_policy import (
        loaded_models,
        plan_player,
        plan_schedules,
    )

    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    player = plan_player(session.env)
    schedules = plan_schedules(session.env)
    models = loaded_models()
    if player is None or schedules is None:
        raise HTTPException(
            400, "No committed plan — step under 'goal_directed' first")
    if models is None:
        raise HTTPException(400, "No models installed — what-if needs them")
    try:
        weights = DirectorWeights(
            req.punctuality, req.connections, req.stability)
    except ValueError as e:
        raise HTTPException(400, str(e))

    graph = player.graph
    snapshot = player.snapshot()
    stations = resolve_stations(session.env)
    connections = planned_connections(session.env, stations)
    watch = station_watch_cells(stations)
    step = int(getattr(session.env, "_elapsed_steps", 0) or 0)

    def branch_outcome(outcome):
        report = evaluate_connections(
            connections, observed_times(stations, outcome["occupancy"])
        )
        return {
            "total_delay": outcome["total_delay"],
            "arrived": outcome["arrived"],
            "trains": outcome["trains"],
            "all_arrived": outcome["all_arrived"],
            "steps": outcome["steps"],
            "connections_total": int(report.total),
            "connections_kept": int(report.kept),
            "kept_ratio": float(report.kept_ratio),
        }

    fork_a = copy.deepcopy(session.env)
    player_a = SchedulePlayer(graph, fork_a)
    player_a.restore(snapshot)
    continued = branch_outcome(
        simulate_forward(fork_a, player_a, watch_cells=watch))

    fork_b = copy.deepcopy(session.env)
    player_b = SchedulePlayer(graph, fork_b)
    player_b.restore(snapshot)
    plan = residual_plan(
        fork_b, graph, weights, *models,
        player=player_b, schedules=schedules, reason="what-if",
    )
    apply_residual_plan(player_b, plan)
    replanned = branch_outcome(
        simulate_forward(fork_b, player_b, watch_cells=watch))
    replanned["source"] = plan.source
    replanned["changed"] = sorted(plan.tails)
    replanned["predicted"] = {
        "weighted": plan.score.weighted,
        "utilities": dict(plan.score.breakdown["utilities"]),
        "considered": dict(plan.considered),
    }

    return {
        "session_id": session_id,
        "step": step,
        "weights": {
            "punctuality": req.punctuality,
            "connections": req.connections,
            "stability": req.stability,
        },
        "continue": continued,
        "replan": replanned,
    }


@router.get("/{session_id}/scenario-policies")
def get_scenario_policies(session_id: str):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    scenario_available = set(scenario_policy_factories().keys())
    policy_available = {spec.id for spec in policy_specs(include_hidden=True) if spec.show_in_ui}

    scenario_enabled = getattr(session, "enabled_scenario_policies", scenario_available)
    policy_enabled = getattr(session, "enabled_policy_ids", policy_available)

    return {
        "session_id": session_id,
        "enabled_ids": sorted(pid for pid in scenario_enabled if pid in scenario_available),
        "available_ids": sorted(scenario_available),
        "enabled_policy_ids": sorted(pid for pid in policy_enabled if pid in policy_available),
        "available_policy_ids": sorted(policy_available),
    }


@router.post("/{session_id}/scenario-policies")
def set_scenario_policies(session_id: str, req: ScenarioPoliciesUpdateRequest):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    scenario_available = set(scenario_policy_factories().keys())
    policy_available = {spec.id for spec in policy_specs(include_hidden=True) if spec.show_in_ui}

    requested_scenarios = set(req.enabled_ids or [])
    requested_policies = set(req.enabled_policy_ids or [])

    unknown_scenarios = sorted(requested_scenarios - scenario_available)
    if unknown_scenarios:
        raise HTTPException(400, f"Unknown scenario policy ids: {unknown_scenarios}")

    unknown_policies = sorted(requested_policies - policy_available)
    if unknown_policies:
        raise HTTPException(400, f"Unknown policy-control ids: {unknown_policies}")

    if not requested_scenarios:
        raise HTTPException(400, "At least one scenario policy must remain enabled")

    if not requested_policies:
        raise HTTPException(400, "At least one policy-control policy must remain enabled")

    session.enabled_scenario_policies = set(requested_scenarios)
    session.enabled_policy_ids = set(requested_policies)

    if session.policy not in session.enabled_policy_ids:
        default_id = next((spec.id for spec in policy_specs(include_hidden=True) if spec.is_default and spec.id in session.enabled_policy_ids), None)
        session.policy = default_id or sorted(session.enabled_policy_ids)[0]

    _invalidate_scenario_forecasts(session_id)

    return {
        "session_id": session_id,
        "enabled_ids": sorted(session.enabled_scenario_policies),
        "available_ids": sorted(scenario_available),
        "enabled_policy_ids": sorted(session.enabled_policy_ids),
        "available_policy_ids": sorted(policy_available),
    }


