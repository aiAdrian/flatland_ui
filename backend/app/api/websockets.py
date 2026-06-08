"""
WebSocket + Play API Endpoints.

WebSocket: /ws/session/{session_id}
   Client connectet sich, Backend pusht initialen State und nach jedem Step.

Play / Pause:
   POST /session/{session_id}/play  body={speed: 5, policy: "shortest_path"}
   POST /session/{session_id}/pause
"""
import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional

from app.core.session_manager import session_manager
from app.core.serializer import serialize_env
from app.core.ws_manager import ws_manager
from app.core.play_manager import play_manager, PlayState
from app.policies.random_policy import RandomPolicy
from app.policies.shortest_path_policy import ShortestPathPolicy
from app.policies.override_policy import OverridePolicy
from app.core.override_manager import override_manager

router = APIRouter()


class PlayRequest(BaseModel):
    speed: float = 5.0  # steps per second, 0.5 - 20
    policy: str = "shortest_path"


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
    """Build the state payload broadcast over WebSocket.
    Includes the current overrides so the frontend keeps showing the
    selected action pills while play is running."""
    overrides = override_manager.get_all(session_id)
    state = serialize_env(env, overrides=overrides)
    state["episode_done"] = _is_done(env)
    return {"type": "state", "session_id": session_id, "state": state}


async def _play_loop(session_id: str):
    state = play_manager.get(session_id)
    if state is None:
        return
    session = session_manager.get(session_id)
    if session is None:
        return

    env = session.env

    if state.policy == "random":
        try:
            action_size = int(env.action_space[0])
        except Exception:
            action_size = 5
        default_policy = RandomPolicy(action_size=action_size)
    else:
        default_policy = ShortestPathPolicy(env)
    # Wrap the chosen policy so user overrides are honoured during play.
    policy = OverridePolicy(env, session_id, default_policy)

    while state.running:
        if _is_done(env):
            state.running = False
            await ws_manager.broadcast(session_id, {
                "type": "episode_done",
                "session_id": session_id,
            })
            break

        try:
            handles = env.get_agent_handles()
            observations = session.last_observations or {}
            actions = policy.act_many(handles, observations)
            next_obs, rewards, dones, info = env.step(actions)
            session.last_observations = next_obs
            session.last_info = info
        except Exception as e:
            state.running = False
            await ws_manager.broadcast(session_id, {
                "type": "error",
                "session_id": session_id,
                "message": str(e),
            })
            break

        await ws_manager.broadcast(session_id, _build_state_payload(session_id, env))

        # Wait based on configured speed (steps per second)
        delay = 1.0 / max(state.speed, 0.1)
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            break


@router.websocket("/ws/session/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    session = session_manager.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return

    await ws_manager.connect(session_id, websocket)
    try:
        # Send initial state
        await websocket.send_json(_build_state_payload(session_id, session.env))

        # Keep connection alive, just receive any pings
        while True:
            try:
                msg = await websocket.receive_text()
                # Allow client to send commands like "ping"
                if msg == "ping":
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        ws_manager.disconnect(session_id, websocket)


@router.post("/session/{session_id}/play")
async def play(session_id: str, req: PlayRequest):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    if play_manager.is_playing(session_id):
        return {"session_id": session_id, "playing": True, "message": "Already playing"}

    state = PlayState(session_id, req.speed, req.policy)
    state.running = True
    play_manager.register(state)
    state.task = asyncio.create_task(_play_loop(session_id))

    return {
        "session_id": session_id,
        "playing": True,
        "speed": req.speed,
        "policy": req.policy,
    }


@router.post("/session/{session_id}/pause")
async def pause(session_id: str):
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    await play_manager.stop(session_id)
    return {"session_id": session_id, "playing": False}


@router.get("/session/{session_id}/play_status")
def play_status(session_id: str):
    return {
        "session_id": session_id,
        "playing": play_manager.is_playing(session_id),
    }
