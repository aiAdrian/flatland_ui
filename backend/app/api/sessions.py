import asyncio

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from typing import List

from app.core.session_manager import session_manager
from app.core.serializer import serialize_env
from app.core.ws_manager import ws_manager
from app.core.override_manager import override_manager
from app.models.session import (
    SessionCreateRequest,
    SessionInfo,
    StepRequest,
)
from app.models.agent import ActionRequest
from app.policies.random_policy import RandomPolicy
from app.policies.shortest_path_policy import ShortestPathPolicy
from app.policies.do_nothing_policy import DoNothingPolicy
from app.policies.forward_only_policy import ForwardOnlyPolicy
from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy
from app.policies.override_policy import OverridePolicy

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
    if policy_name == "random":
        try:
            action_size = int(env.action_space[0])
        except Exception:
            action_size = 5
        default = RandomPolicy(action_size=action_size)
    elif policy_name == "shortest_path":
        default = ShortestPathPolicy(env)
    elif policy_name == "do_nothing":
        default = DoNothingPolicy()
    elif policy_name == "forward_only":
        default = ForwardOnlyPolicy()
    elif policy_name == "deadlock_avoidance":
        default = DeadLockAvoidancePolicy()
    else:
        raise HTTPException(400, f"Unknown policy: {policy_name}")
    default.reset(env)
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

    policy = _build_policy(session_id, env, req.policy)
    # Track the most recently used policy so /hmi/scenarios can
    # use it as baseline.
    session.policy = req.policy

    rewards = {}
    dones = {}
    all_done = False

    for _ in range(req.n_steps):
        if _is_done(env):
            all_done = True
            break
        handles = env.get_agent_handles()
        observations = session.last_observations or {}
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
        if dones.get("__all__", False):
            all_done = True
            break

    await _broadcast_state(session_id, env)

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
    return {"deleted": session_id}


# ── POST /session/{id}/policy: set active policy without stepping ──
class PolicyChangeRequest(BaseModel):
    policy: str


@router.post("/{session_id}/policy")
def set_session_policy(session_id: str, req: PolicyChangeRequest):
    """Switch the active policy for a session without stepping.
    Subsequent steps and /hmi/scenarios use this as baseline."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    # Validate against known policy ids
    known = {"deadlock_avoidance", "shortest_path", "forward_only", "do_nothing", "random"}
    if req.policy not in known:
        raise HTTPException(400, f"Unknown policy: {req.policy}")
    session.policy = req.policy
    # Invalidate the scenario cache so the next /hmi/scenarios call
    # recomputes with the new baseline.
    try:
        from app.core.scenario_cache import scenario_cache
        scenario_cache.clear_session(session_id)
    except Exception:
        pass
    return {"session_id": session_id, "policy": session.policy}

