#!/usr/bin/env python
"""Precompute the sandbox outcomes of the Co-learning Monte Carlo Interviews tour.

Step 8 of the tour (Event Simulation) is a mock for the first interview round,
but its numbers are not invented: every variant is run with the real simulator on
the same episode the interviewee just played — the scenario's plan policy, the
same scripted disturbance, the impact analysis the HMI shows, and holds or
reroutes applied through the same override manager (STOP sticky until released,
a direction one-shot at the next switch). Only the interactivity is missing.

Delay is measured against the undisturbed run of the same plan, because the
scenario's latest-arrival windows are too generous to register a few steps.

Trains are referred to by handle only: texts carry `{T<handle>}` placeholders and
the HMI fills in the shared train name (`TrainIdentityService`), so the sandbox
reads like the map and the timetable.

    cd backend
    .venv/bin/python scripts/generate_sandbox_outcomes.py

Writes `frontend/src/app/core/demo/sandbox-outcomes.generated.ts`. Re-run it
whenever the scene, its plan or the tour disturbance changes.

Plan: docs/plans/colearning-monte-carlo-interviews-tour.md (WP3).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.disable(logging.CRITICAL)

from flatland.envs.step_utils.states import TrainState  # noqa: E402

from app.api.sessions import _build_policy  # noqa: E402
from app.core.disturbances import apply_due_disturbances  # noqa: E402
from app.core.override_manager import override_manager  # noqa: E402
from app.core.recommenders.registry import active_recommender  # noqa: E402
from app.core.scenario_presets import select_disturbances  # noqa: E402
from app.core.session_manager import session_manager  # noqa: E402

PRESET = "pf-ch-wn-wal-long-approach"
TOUR_DISTURBANCE = "interview-e1-breakdown-single-track"
STOP = 4
OUT = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "app" / "core" / "demo" / "sandbox-outcomes.generated.ts"
)

# A case the interviewee has not met: train 1 breaks down inside the single-track
# section while train 2 comes the other way. Inline rather than a fixture file, so
# it can never appear as a selectable disturbance.
NOVEL_DISTURBANCE = [{
    "id": "sandbox-head-on-breakdown",
    "events": [{"step": 34, "type": "train_delay", "agent_handle": 1, "delay_steps": 20}],
}]


def T(handle: int) -> str:
    """Placeholder the HMI replaces with the shared train name."""
    return f"{{T{handle}}}"


def _run(disturbances, actions=()):
    """Run the episode to its end.

    `actions` is a list of `(step, handle, action)`; `action=None` releases the
    handle. Returns `(arrival step per handle, first impact item and its step, trains)`.
    """
    session = session_manager.create(scenario_preset_id=PRESET, disturbances=disturbances)
    env = session.env
    policy = _build_policy(session.id, env, session.policy)
    recommender = active_recommender()
    max_steps = int(getattr(env, "_max_episode_steps", 0) or 180)
    arrival: dict[int, int] = {}
    first_impact = None
    try:
        while True:
            step = int(env._elapsed_steps)
            for at, handle, action in actions:
                if at == step:
                    if action is None:
                        override_manager.clear(session.id, handle)
                    else:
                        override_manager.set(session.id, handle, action)
            policy.start_step()
            chosen = policy.act_many(env.get_agent_handles(), session.last_observations or {})
            try:
                obs, _, dones, _ = env.step(chosen)
            except Exception as exc:  # Flatland raises once the episode is over
                if "Episode is done" in str(exc):
                    break
                raise
            policy.end_step()
            session.last_observations = obs
            apply_due_disturbances(session.id, session, env)
            if first_impact is None:
                items = recommender.recommend(env)
                if items:
                    first_impact = (int(env._elapsed_steps), items[0])
            for agent in env.agents:
                if agent.handle not in arrival and agent.state == TrainState.DONE:
                    arrival[agent.handle] = int(env._elapsed_steps)
            if dones.get("__all__") or env._elapsed_steps >= max_steps:
                break
        return arrival, first_impact, len(env.agents)
    finally:
        override_manager.clear_all(session.id)


def _outcome(arrival: dict[int, int], plan: dict[int, int], total: int) -> dict:
    trains = []
    for handle in range(total):
        arrived_at = arrival.get(handle)
        planned = plan.get(handle)
        trains.append({
            "handle": handle,
            "arrived": arrived_at is not None,
            "arrivalStep": arrived_at,
            "delayVsPlan": None if arrived_at is None or planned is None else arrived_at - planned,
        })
    return {
        "arrived": sum(1 for t in trains if t["arrived"]),
        "total": total,
        "totalDelayVsPlan": sum(t["delayVsPlan"] or 0 for t in trains),
        "trains": trains,
    }


def _variant(vid, label, description, matches_action, outcome) -> dict:
    return {"id": vid, "label": label, "description": description, "matchesAction": matches_action, **outcome}


def _case(disturbances, plan, total, meta, labels) -> dict:
    """Hold-then-release, proceed and (where the impact analysis offers it) reroute,
    decided at the step and for the train the impact analysis names."""
    proceed_arrival, impact, _ = _run(disturbances)
    if impact is None:
        raise SystemExit(f"{meta['id']}: the impact analysis never lists an affected train")
    at, item = impact
    handle, clears = int(item["handle"]), int(item["clears_in_steps"])
    blocker = int(item["blocked_by"])
    fill = lambda text: text.replace("{affected}", T(handle)).replace("{blocker}", T(blocker))  # noqa: E731

    hold_arrival, _, _ = _run(disturbances, [(at, handle, STOP), (at + clears, handle, None)])
    variants = [
        _variant("hold-release", fill(labels["hold"]), fill(labels["hold_desc"]), "hold",
                 _outcome(hold_arrival, plan, total)),
        _variant("proceed", fill(labels["proceed"]), fill(labels["proceed_desc"]), "proceed",
                 _outcome(proceed_arrival, plan, total)),
    ]
    if item.get("can_reroute") and item.get("reroute_action") is not None:
        reroute_arrival, _, _ = _run(disturbances, [(at, handle, int(item["reroute_action"]))])
        variants.append(_variant(
            "reroute", fill(labels["reroute"]), fill(labels["reroute_desc"]), "reroute",
            _outcome(reroute_arrival, plan, total),
        ))
    if labels.get("no_release"):
        stuck_arrival, _, _ = _run(disturbances, [(at, handle, STOP)])
        variants.append(_variant(
            "hold-no-release", fill(labels["no_release"]), fill(labels["no_release_desc"]), None,
            _outcome(stuck_arrival, plan, total),
        ))
    return {
        **meta,
        "title": fill(meta["title"]),
        "situation": fill(meta["situation"]),
        "decisionHandle": handle,
        "decisionStep": at,
        "variants": variants,
    }


def main() -> None:
    plan_arrival, _, total = _run([])

    tour = select_disturbances(PRESET, [TOUR_DISTURBANCE])
    tour_event = tour[0]["events"][0]
    novel_event = NOVEL_DISTURBANCE[0]["events"][0]

    experienced = _case(tour, plan_arrival, total, {
        "id": "experienced-single-track",
        "kind": "experienced",
        "title": "{blocker} bleibt im Einspurabschnitt stehen",
        "situation": (
            f"Der Vorfall aus Ihrer Schicht: {{blocker}} steht ab Schritt {tour_event['step']} für "
            f"{tour_event['delay_steps']} Schritte mitten im einspurigen Abschnitt, {{affected}} folgt auf demselben Gleis."
        ),
    }, {
        "hold": "Halten, dann freigeben",
        "hold_desc": "{affected} wartet, bis {blocker} wieder fährt, und wird dann freigegeben.",
        "proceed": "Weiterfahren",
        "proceed_desc": "{affected} fährt weiter bis vor die Störung und wartet dort.",
        "reroute": "Umleiten",
        "reroute_desc": "{affected} nimmt die von der KI angebotene Umfahrung.",
        "no_release": "Halten ohne Freigabe",
        "no_release_desc": "{affected} bleibt angehalten, weil niemand die Freigabe gibt.",
    })

    novel = _case(NOVEL_DISTURBANCE, plan_arrival, total, {
        "id": "novel-head-on",
        "kind": "novel",
        "title": "Gegenzug vor dem blockierten Einspurabschnitt",
        "situation": (
            f"Nicht erlebt: {{blocker}} bleibt ab Schritt {novel_event['step']} für {novel_event['delay_steps']} Schritte "
            "im Einspurabschnitt stehen, während {affected} aus der Gegenrichtung auf den Abschnitt zufährt."
        ),
    }, {
        "hold": "{affected} halten, dann freigeben",
        "hold_desc": "{affected} wartet vor dem Abschnitt, bis {blocker} ihn räumt.",
        "proceed": "{affected} weiterfahren lassen",
        "proceed_desc": "{affected} fährt bis an die Einfahrt und wartet dort.",
        "reroute": "{affected} umleiten",
        "reroute_desc": "{affected} nimmt die von der KI angebotene Umfahrung.",
    })

    data = {
        "scenario": PRESET,
        "generator": "backend/scripts/generate_sandbox_outcomes.py",
        "generatedOn": date.today().isoformat(),
        "planArrivalSteps": {str(h): s for h, s in sorted(plan_arrival.items())},
        "cases": [experienced, novel],
    }

    header = (
        "// Generated by backend/scripts/generate_sandbox_outcomes.py — do not edit by hand.\n"
        "// Re-run the script when the scene, its plan or the tour disturbance changes.\n"
        "import { SandboxOutcomes } from './sandbox-outcomes';\n\n"
    )
    OUT.write_text(
        header + "export const SANDBOX_OUTCOMES: SandboxOutcomes = "
        + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )

    print("plan arrivals by handle", data["planArrivalSteps"])
    for case in data["cases"]:
        print(f"{case['title']} (decision on T{case['decisionHandle']} at step {case['decisionStep']})")
        for v in case["variants"]:
            trains = ", ".join(
                f"T{t['handle']} " + (f"+{t['delayVsPlan']}" if t["arrived"] else "nicht angekommen")
                for t in v["trains"]
            )
            print(f"  {v['label']}: {v['arrived']}/{v['total']} angekommen, +{v['totalDelayVsPlan']} | {trains}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
