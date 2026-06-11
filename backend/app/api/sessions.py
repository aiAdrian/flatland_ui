import asyncio

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
import logging
import time
from typing import Any, List

from app.core.session_manager import session_manager
from app.core.serializer import serialize_env
from app.core.ws_manager import ws_manager
from app.core.override_manager import override_manager
from app.core.notification_manager import notification_manager
from app.models.session import (
    SessionCreateRequest,
    SessionInfo,
    StepRequest,
)
from app.models.agent import ActionRequest
from app.policies.override_policy import OverridePolicy
from app.policies.registry import create_runtime_policy, scenario_policy_factories

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


@router.post("", response_model=SessionInfo)
def create_session(req: SessionCreateRequest):
    session = session_manager.create(
        width=req.width,
        height=req.height,
        number_of_agents=req.number_of_agents,
        seed=req.seed,
        max_num_cities=req.max_num_cities,
        max_rails_between_cities=req.max_rails_between_cities,
        max_rail_pairs_in_city=req.max_rail_pairs_in_city,
        max_episode_steps=req.max_episode_steps,
    )
    return SessionInfo(
        id=session.id,
        width=session.env.width,
        height=session.env.height,
        num_agents=len(session.env.agents),
    )


@router.get("")
def list_sessions() -> List[str]:
    return session_manager.list_ids()


@router.get("/{session_id}/state")
def get_state(session_id: str):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    overrides = override_manager.get_all(session_id)
    state = serialize_env(session.env, overrides=overrides)
    state["episode_done"] = _is_done(session.env)
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

    enabled = set(getattr(session, "enabled_scenario_policies", set()))
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
    obs, info = session.env.reset()
    session.last_observations = obs
    session.last_info = info
    override_manager.clear_all(session_id)
    notification_manager.clear_session(session_id)

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
    return {"deleted": session_id}


# ── POST /session/{id}/policy: set active policy without stepping ──
class PolicyChangeRequest(BaseModel):
    policy: str


class ScenarioPoliciesUpdateRequest(BaseModel):
    enabled_ids: list[str]


@router.post("/{session_id}/policy")
def set_session_policy(session_id: str, req: PolicyChangeRequest):
    """Switch the active policy for a session without stepping.
    Subsequent steps and /hmi/scenarios use this as baseline."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    enabled = set(getattr(session, "enabled_scenario_policies", set()))
    if req.policy not in enabled:
        raise HTTPException(400, f"Policy '{req.policy}' is not enabled for this session")
    session.policy = req.policy
    # Invalidate the scenario cache so the next /hmi/scenarios call
    # recomputes with the new baseline.
    try:
        from app.core.scenario_cache import scenario_cache
        scenario_cache.clear_session(session_id)
    except Exception:
        pass
    return {"session_id": session_id, "policy": session.policy}


@router.get("/{session_id}/scenario-policies")
def get_scenario_policies(session_id: str):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    specs = scenario_policy_factories()
    enabled = getattr(session, "enabled_scenario_policies", set(specs.keys()))
    return {
        "session_id": session_id,
        "enabled_ids": sorted(pid for pid in enabled if pid in specs),
        "available_ids": sorted(specs.keys()),
    }


@router.post("/{session_id}/scenario-policies")
def set_scenario_policies(session_id: str, req: ScenarioPoliciesUpdateRequest):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    available = set(scenario_policy_factories().keys())
    requested = set(req.enabled_ids or [])
    unknown = sorted(requested - available)
    if unknown:
        raise HTTPException(400, f"Unknown scenario policy ids: {unknown}")

    if not requested:
        raise HTTPException(400, "At least one scenario policy must remain enabled")

    session.enabled_scenario_policies = set(requested)
    if session.policy not in session.enabled_scenario_policies:
        session.policy = sorted(session.enabled_scenario_policies)[0]

    try:
        from app.core.scenario_cache import scenario_cache
        scenario_cache.clear_session(session_id)
    except Exception:
        pass

    return {
        "session_id": session_id,
        "enabled_ids": sorted(session.enabled_scenario_policies),
        "available_ids": sorted(available),
    }

