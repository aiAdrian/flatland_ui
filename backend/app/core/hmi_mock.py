"""Procedurale HMI-Mock-Daten basierend auf Session-Seed.

Reproduzierbar (gleicher Seed -> gleiche Daten), aber abwechslungsreich
genug fuer einen realistischen PoC-Eindruck.
"""
import hashlib
from typing import List

from app.models.hmi import (
    AppNotification,
    HmiBundle,
    KpiDelta,
    Recommendation,
    RelatedElement,
    ScenarioOption,
)

_NOTIFICATION_TEMPLATES = [
    ("warning", "Switch Failure",     "Switch {id} reports a fault."),
    ("warning", "Train Delay",        "Train {id} is running 90s late."),
    ("info",    "Signal Restored",    "Signal {id} cleared after maintenance."),
    ("error",   "Track Blocked",      "Track segment near switch {id} is blocked."),
    ("info",    "Train Departed",     "Train {id} has departed station."),
    ("warning", "Conflict Detected",  "Routing conflict at switch {id}."),
]

_SCENARIO_TEMPLATES = [
    ("Reroute via Track 2", "Take alternate route via track 2 to avoid conflict."),
    ("Hold and Wait",       "Hold train at current position for 60s."),
    ("Proceed Normally",    "Continue with current plan, accept delay."),
    ("Skip Stop",           "Skip non-essential stop to recover time."),
]

_RECOMMENDATION_TEMPLATES = [
    ("Take Scenario {sid}",         "AI recommends scenario {sid} based on KPI weights."),
    ("Override Agent {aid} = LEFT", "AI suggests turning agent {aid} left at next switch."),
    ("Hold Agent {aid}",            "Hold agent {aid} for 1 step to resolve conflict."),
]


def _seeded(session_id: str, step: int, salt: str = "") -> int:
    h = hashlib.md5(f"{session_id}|{step}|{salt}".encode()).hexdigest()
    return int(h[:8], 16)


def _pick(items, n: int):
    return items[n % len(items)]


def generate_notifications(session_id: str, step: int) -> List[AppNotification]:
    """Build notifications from the actual env state.

    We surface four classes of events, all derived deterministically
    from the current env so the list reflects what the operator can
    observe on the map:
      - error   "Malfunction"          - any agent currently malfunctioning
      - warning "Override active"      - any agent with a user-set override
      - info    "Decision pending"     - agent has a next decision <=5 cells away
      - info    "Episode finished"     - all agents done
    Notifications disappear automatically once the underlying condition
    clears.
    """
    from app.core.session_manager import session_manager
    from app.core.cell_classifier import lookahead_to_decision
    from app.core.override_manager import override_manager

    out: List[AppNotification] = []

    sess = session_manager.get(session_id)
    if not sess:
        return out
    env = getattr(sess, "env", None)
    if env is None:
        return out

    # 1) Episode finished
    dones = getattr(env, "dones", {}) or {}
    if dones.get("__all__"):
        out.append(AppNotification(
            id=f"n_{step}_done",
            kind="info",
            title="Episode finished",
            message="All agents have reached their target.",
            timestamp=step,
            relatedElement=None,
        ))

    overrides = override_manager.get_all(session_id)

    for agent in getattr(env, "agents", []) or []:
        h = int(agent.handle)
        aid = str(h)

        # 2) Malfunction (use new MalfunctionHandler API)
        mh = getattr(agent, "malfunction_handler", None)
        mf_steps = 0
        if mh is not None:
            try:
                mf_steps = int(getattr(mh, "malfunction_down_counter", 0) or 0)
            except Exception:
                mf_steps = 0
        if mf_steps > 0:
            out.append(AppNotification(
                id=f"n_{step}_mf_{h}",
                kind="error",
                title="Malfunction",
                message=f"Train {h} is malfunctioning ({mf_steps} steps remaining).",
                timestamp=step,
                relatedElement=RelatedElement(kind="train", id=aid),
            ))

        # 3) Override active
        if h in overrides:
            action = overrides[h]
            label = {1: "LEFT", 2: "FORWARD", 3: "RIGHT"}.get(int(action), str(action))
            out.append(AppNotification(
                id=f"n_{step}_ov_{h}",
                kind="warning",
                title="Override active",
                message=f"Train {h}: operator override {label} pending.",
                timestamp=step,
                relatedElement=RelatedElement(kind="train", id=aid),
            ))

        # 4) Decision pending (<=5 cells)
        try:
            nd = lookahead_to_decision(env, agent)
        except Exception:
            nd = None
        if nd is not None:
            dist = int(nd.get("distance", 999))
            if dist <= 5:
                kind = nd.get("cell_type", "DECISION")
                pos = nd.get("decision_position") or [None, None]
                out.append(AppNotification(
                    id=f"n_{step}_dec_{h}",
                    kind="info",
                    title="Decision pending",
                    message=(
                        f"Train {h} reaches a {kind.lower()} at "
                        f"({pos[0]},{pos[1]}) in {dist} cells."
                    ),
                    timestamp=step,
                    relatedElement=RelatedElement(kind="train", id=aid),
                ))

    return out


def generate_scenarios(session_id: str, step: int) -> List[ScenarioOption]:
    out: List[ScenarioOption] = []
    base_seed = _seeded(session_id, step // 50, "scn")
    for i in range(3):
        seed = base_seed + i * 7919
        title, desc = _pick(_SCENARIO_TEMPLATES, seed)
        time_delta = -((seed % 180) - 60)
        energy_delta = ((seed >> 4) % 80) - 40
        out.append(ScenarioOption(
            id=f"s_{step // 50}_{i}",
            title=title,
            description=desc,
            kpiDelta=KpiDelta(time=time_delta, energy=energy_delta),
            isRecommended=(i == 0),
        ))
    return out


def generate_recommendations(session_id: str, step: int) -> List[Recommendation]:
    seed = _seeded(session_id, step // 30, "rec")
    title_tmpl, desc_tmpl = _pick(_RECOMMENDATION_TEMPLATES, seed)
    sid = f"s_{step // 50}_{seed % 3}"
    aid = str(seed % 5)
    confidence = 0.55 + ((seed >> 6) % 45) / 100.0
    countdown = 15 + (seed % 45)
    return [Recommendation(
        id=f"r_{step // 30}_{seed % 100}",
        title=title_tmpl.format(sid=sid, aid=aid),
        description=desc_tmpl.format(sid=sid, aid=aid),
        confidence=round(confidence, 2),
        countdownSeconds=countdown,
        scenarioId=sid,
    )]


def generate_bundle(session_id: str, step: int) -> HmiBundle:
    return HmiBundle(
        notifications=generate_notifications(session_id, step),
        scenarios=generate_scenarios(session_id, step),
        recommendations=generate_recommendations(session_id, step),
    )
