"""Generate the scenario JSON files under ``scenarios/``.

Run with:  python build_scenarios.py

The generated JSON files are the real, hand-editable artifacts. This script just
keeps them consistent and makes it easy to regenerate or add new scenarios. Once
generated you can edit the JSON directly without re-running this.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path(__file__).parent / "scenarios"

# A wide corridor layout (~1160x360) so trains travel a longer distance.
# Main line runs left->right; north/south branches meet at Center.
BASE_NODES = [
    {"id": "west_junction", "x": 80, "y": 190, "label": "West Jct"},
    {"id": "harburg", "x": 300, "y": 190, "label": "Harburg"},
    {"id": "center", "x": 560, "y": 190, "label": "Center"},
    {"id": "lehrte", "x": 830, "y": 190, "label": "Lehrte"},
    {"id": "east_junction", "x": 1080, "y": 190, "label": "East Jct"},
    {"id": "north", "x": 560, "y": 80, "label": "North Yard"},
    {"id": "south", "x": 560, "y": 300, "label": "South Yard"},
]


def _next_event_min(pressure: str) -> int:
    return {"LOW": 25, "MEDIUM": 15, "HIGH": 8, "STRESS": 4}.get(pressure, 15)


def _event(kind, text, severity="intervention"):
    """A short trigger announcement shown just before the situation appears.

    ``severity`` is "info" (the AI handles it autonomously; it only streams into
    the attention feed) or "intervention" (the shift pauses for a director
    decision).
    """
    icon = {
        "track_blocked": "🚧",
        "train_delayed": "⏱",
        "connection_risk": "🔗",
        "disruption": "🌩",
        "conflict": "⚠️",
    }.get(kind, "⚠️")
    return {"kind": kind, "icon": icon, "text": text, "severity": severity}


def network(conflict_node, critical_ids, trains, edge_status=None):
    edge_status = edge_status or {}
    edges = [
        {"from": "west_junction", "to": "harburg"},
        {"from": "harburg", "to": "center"},
        {"from": "center", "to": "lehrte"},
        {"from": "lehrte", "to": "east_junction"},
        {"from": "north", "to": "center"},
        {"from": "center", "to": "south"},
    ]
    for e in edges:
        key = f"{e['from']}->{e['to']}"
        if key in edge_status:
            e["status"] = edge_status[key]
    return {
        "nodes": BASE_NODES,
        "edges": edges,
        "conflict_node": conflict_node,
        "critical_connection": critical_ids,
        "trains": trains,
    }


def effects(delay, connection, ripple, follow_up):
    return {
        "delay_impact": delay,
        "connection_impact": connection,
        "ripple_risk": ripple,
        "follow_up_conflict_risk": follow_up,
    }


def outcome(delay, connection, follow_up, network_state):
    return {
        "additional_delay_min": delay,
        "connection": connection,
        "follow_up_conflicts": follow_up,
        "network_state": network_state,
    }


def dp(
    step,
    time_label,
    pressure,
    sim_step,
    event,
    description,
    affected,
    main_conflict,
    critical,
    buffer_min,
    delay,
    ripple,
    follow_up,
    confidence,
    strategies,
    strategy_effects,
    baseline,
    personalized,
    learning_influence,
    outcomes,
    conflict_node="center",
    critical_ids=None,
    trains=None,
    edge_status=None,
    passengers=None,
):
    return {
        "step": step,
        "time_label": time_label,
        "operational_pressure": pressure,
        "sim_step": sim_step,
        "next_event_min": _next_event_min(pressure),
        "event": event,
        "situation": {
            "description": description,
            "time_label": time_label,
            "affected_trains": affected,
            "main_conflict": main_conflict,
            "critical_connection": critical,
            "connection_buffer_min": buffer_min,
            "current_delay_min": delay,
            "ripple_risk": ripple,
            "expected_follow_up_conflicts": follow_up,
            "forecast_confidence": confidence,
            "passengers": passengers,
        },
        "network": network(
            conflict_node, critical_ids or [], trains or [], edge_status
        ),
        "strategies": strategies,
        "strategy_effects": strategy_effects,
        "baseline_recommendation": baseline,
        "personalized_recommendation": personalized,
        "learning_influence": learning_influence,
        "outcomes": outcomes,
    }


# Canonical strategy effects. Each option is the BEST on at least one axis, so
# none is Pareto-dominated ("no bad option, only trade-offs"):
#   minimize_delay          -> best delay
#   protect_critical_conn.  -> best connection
#   stabilize_network       -> best network load (ripple)
#   avoid_follow_up_confl.  -> best follow-up risk
#   maintain_current_plan   -> lowest immediate delay, worst downstream
CANON_EFFECTS = {
    "minimize_delay": effects("+1 min", "At risk", "medium", "medium"),
    "protect_critical_connection": effects("+3 min", "Protected", "low", "low"),
    "stabilize_network": effects("+2 min", "At risk", "low", "medium"),
    "avoid_follow_up_conflicts": effects("+2 min", "At risk", "medium", "low"),
    "maintain_current_plan": effects("+0 min", "At risk", "high", "high"),
}


def trio_effects():
    return {k: CANON_EFFECTS[k] for k in TRIO}


def std_outcomes(exp_delay_prot=3, unexpected=False):
    """Standard outcome block for the three common strategies."""
    protect_observed = [
        {"weight": 3, "values": outcome(exp_delay_prot, "Protected", 0, "stable")},
    ]
    if unexpected:
        protect_observed = [
            {"weight": 1, "values": outcome(exp_delay_prot, "Protected", 0, "stable")},
            {"weight": 4, "values": outcome(exp_delay_prot + 2, "Broken", 1, "strained")},
        ]
    return {
        "minimize_delay": {
            "expected": outcome(1, "At risk", 0, "stable"),
            "observed": [{"weight": 1, "values": outcome(1, "Broken", 0, "stable")}],
        },
        "protect_critical_connection": {
            "expected": outcome(exp_delay_prot, "Protected", 0, "stable"),
            "observed": protect_observed,
        },
        "stabilize_network": {
            "expected": outcome(2, "At risk", 0, "stable"),
            "observed": [{"weight": 1, "values": outcome(2, "At risk", 0, "stable")}],
        },
    }


# --------------------------------------------------------------------------- #
# Scenario builders
# --------------------------------------------------------------------------- #

TRIO = ["minimize_delay", "protect_critical_connection", "stabilize_network"]


def easy_morning():
    trains = [
        {"id": "train_5", "label": "T5", "x": 200, "y": 190, "status": "+1 min"},
        {"id": "train_6", "label": "T6", "x": 700, "y": 190, "status": "on time"},
    ]
    points = []
    times = ["09:10", "09:22", "09:31", "09:40", "09:54", "10:05", "10:14", "10:26"]
    n = 8
    for i in range(n):
        critical = i in (2, 4, 6)
        crit_ids = ["train_5", "train_6"] if critical else []
        baseline = "minimize_delay"
        personalized = "protect_critical_connection" if critical else "minimize_delay"
        learning = critical and i == 4  # one learning-adjusted case
        if critical:
            event = _event("connection_risk",
                           "Connection at risk: Train 5 → Train 6 buffer shrinking",
                           severity="intervention")
        else:
            event = _event("conflict", "Minor headway conflict resolved at Center",
                           severity="info")
        points.append(
            dp(
                step=i + 1,
                time_label=times[i],
                pressure="LOW",
                sim_step=int((i + 1) / n * 380) + 10,
                event=event,
                description=(
                    "Train 5 approaches West Junction. The connection Train 5 -> "
                    "Train 6 still has a small buffer."
                    if critical
                    else "Routine approach at Center. No critical connection at stake."
                ),
                affected=["train_5", "train_6"] if critical else ["train_5"],
                main_conflict="Minor headway conflict at Center",
                critical=critical,
                buffer_min=4 if critical else None,
                delay=2,
                ripple="low",
                follow_up=0,
                confidence="high",
                strategies=TRIO,
                strategy_effects=trio_effects(),
                baseline=baseline,
                personalized=personalized,
                learning_influence=learning,
                outcomes=std_outcomes(exp_delay_prot=2),
                conflict_node="center",
                critical_ids=crit_ids,
                trains=trains,
                edge_status={"harburg->center": "risk"} if critical else None,
            )
        )
    return {
        "scenario_id": "easy_morning",
        "name": "Easy Morning",
        "difficulty": "Easy",
        "seed": 42,
        "total_steps": 400,
        "description": (
            "A calm morning with few conflicts, clear recommendations and low "
            "uncertainty. A gentle introduction to the director-mode flow."
        ),
        "decision_points": points,
    }


def busy_junction():
    trains = [
        {"id": "train_2", "label": "T2", "x": 180, "y": 190, "status": "+2 min"},
        {"id": "train_3", "label": "T3", "x": 560, "y": 110, "status": "on time"},
        {"id": "train_5", "label": "T5", "x": 760, "y": 190, "status": "+1 min"},
        {"id": "train_6", "label": "T6", "x": 560, "y": 270, "status": "on time"},
    ]
    points = []
    times = [
        "11:02", "11:10", "11:18", "11:22", "11:29",
        "11:36", "11:44", "11:51", "11:58", "12:05",
    ]
    n = 10
    for i in range(n):
        critical = i in (1, 3, 5, 7, 9)
        crit_ids = ["train_5", "train_6"] if critical else []
        baseline = "minimize_delay"
        # several plausible strategies; personalized nudges towards protection
        personalized = (
            "protect_critical_connection" if critical else "stabilize_network"
        )
        learning = i in (3, 7)
        unexpected = i == 5
        if critical:
            event = _event("connection_risk",
                           "Connection at risk: Train 5 → Train 6 at Center junction",
                           severity="intervention")
        elif i in (5, 7):
            event = _event("train_delayed", "Train 2 delayed — reordered by AI",
                           severity="info")
        else:
            event = _event("conflict", "Junction capacity conflict resolved at Center",
                           severity="info")
        points.append(
            dp(
                step=i + 1,
                time_label=times[i],
                pressure="MEDIUM",
                sim_step=int((i + 1) / n * 380) + 10,
                event=event,
                description=(
                    "Several trains converge on Center. Protecting the Train 5 -> "
                    "Train 6 connection competes with keeping overall delay low."
                    if critical
                    else "Moderate congestion around the junction; multiple routings "
                    "are plausible."
                ),
                affected=["train_2", "train_3", "train_5", "train_6"],
                main_conflict="Junction capacity conflict at Center",
                critical=critical,
                buffer_min=5 if critical else None,
                delay=3,
                ripple="medium",
                follow_up=1 if i in (5, 7) else 0,
                confidence="medium",
                strategies=TRIO,
                strategy_effects=trio_effects(),
                baseline=baseline,
                personalized=personalized,
                learning_influence=learning,
                outcomes=std_outcomes(exp_delay_prot=3, unexpected=unexpected),
                conflict_node="center",
                critical_ids=crit_ids,
                trains=trains,
                edge_status={
                    "harburg->center": "conflict",
                    "north->center": "risk",
                },
            )
        )
    return {
        "scenario_id": "busy_junction",
        "name": "Busy Junction",
        "difficulty": "Medium",
        "seed": 77,
        "total_steps": 400,
        "description": (
            "Multiple relevant connections and several plausible strategies with "
            "moderate goal conflicts. The first situations where an override can "
            "make sense."
        ),
        "decision_points": points,
    }


def disruption_cascade():
    trains = [
        {"id": "train_1", "label": "T1", "x": 160, "y": 190, "status": "+3 min"},
        {"id": "train_4", "label": "T4", "x": 560, "y": 110, "status": "+1 min"},
        {"id": "train_5", "label": "T5", "x": 720, "y": 190, "status": "+2 min"},
        {"id": "train_6", "label": "T6", "x": 560, "y": 270, "status": "on time"},
        {"id": "train_9", "label": "T9", "x": 980, "y": 190, "status": "+4 min"},
    ]
    points = []
    strategies4 = TRIO + ["avoid_follow_up_conflicts"]
    eff = trio_effects()
    eff["avoid_follow_up_conflicts"] = CANON_EFFECTS["avoid_follow_up_conflicts"]
    n = 12
    for i in range(n):
        # A disruption is injected mid-session -> pressure & risk rise.
        pressure = "MEDIUM" if i < 4 else ("HIGH" if i < 9 else "STRESS")
        ripple = "low" if i < 3 else ("medium" if i < 8 else "high")
        follow_up = 0 if i < 4 else (1 if i < 8 else 2)
        critical = i in (2, 4, 6, 8, 10)
        crit_ids = ["train_5", "train_6"] if critical else []
        baseline = "minimize_delay" if i < 5 else "avoid_follow_up_conflicts"
        personalized = (
            "protect_critical_connection" if critical else "stabilize_network"
        )
        learning = i in (4, 8)
        unexpected = i in (6, 10)
        confidence = "high" if i < 3 else ("medium" if i < 8 else "low")
        hour = 13
        minute = 5 + i * 6
        intervention = (i == 4) or critical
        if i == 4:
            event = _event("disruption",
                           "Disruption detected: track blocked near East Junction",
                           severity="intervention")
        elif critical:
            event = _event("connection_risk",
                           "Connection at risk while disruption propagates",
                           severity="intervention")
        elif i >= 4:
            event = _event("track_blocked",
                           "Reduced capacity near Lehrte — rerouted by AI",
                           severity="info")
        else:
            event = _event("conflict", "Routine conflict resolved by AI",
                           severity="info")
        points.append(
            dp(
                step=i + 1,
                time_label=f"{hour}:{minute:02d}",
                pressure=pressure,
                sim_step=int((i + 1) / n * 380) + 10,
                event=event,
                description=(
                    "A track disruption has appeared. Protecting the critical "
                    "connection now competes with delay and network stability."
                    if i >= 4
                    else "Situation still calm, but the forecast flags a possible "
                    "disruption ahead."
                ),
                affected=["train_1", "train_4", "train_5", "train_6", "train_9"],
                main_conflict=(
                    "Disruption-driven conflict: delay vs connection vs stability"
                ),
                critical=critical,
                buffer_min=4 if critical else None,
                delay=2 + (i // 3),
                ripple=ripple,
                follow_up=follow_up,
                confidence=confidence,
                strategies=strategies4,
                strategy_effects=eff,
                baseline=baseline,
                personalized=personalized,
                learning_influence=learning,
                outcomes={
                    **std_outcomes(exp_delay_prot=3 + (i // 4), unexpected=unexpected),
                    "avoid_follow_up_conflicts": {
                        "expected": outcome(2, "At risk", 0, "stable"),
                        "observed": [
                            {"weight": 3, "values": outcome(2, "At risk", 0, "stable")},
                            {"weight": 1, "values": outcome(3, "At risk", 1, "strained")},
                        ],
                    },
                },
                conflict_node="east_junction" if i >= 4 else "center",
                critical_ids=crit_ids,
                trains=trains,
                edge_status={
                    "lehrte->east_junction": "conflict" if i >= 4 else "risk",
                    "center->lehrte": "risk",
                    "north->center": "risk",
                },
            )
        )
    return {
        "scenario_id": "disruption_cascade",
        "name": "Disruption Cascade",
        "difficulty": "Hard",
        "seed": 123,
        "total_steps": 400,
        "description": (
            "Additional disruptions appear during the session. Recommendations "
            "can change, and goal conflicts between delay, connection protection "
            "and network stability sharpen. Existing preference patterns may reach "
            "their limits."
        ),
        "decision_points": points,
    }


def stress_test():
    trains = [
        {"id": "train_1", "label": "T1", "x": 150, "y": 190, "status": "+5 min"},
        {"id": "train_3", "label": "T3", "x": 560, "y": 110, "status": "+2 min"},
        {"id": "train_5", "label": "T5", "x": 720, "y": 190, "status": "+3 min"},
        {"id": "train_6", "label": "T6", "x": 560, "y": 270, "status": "+1 min"},
        {"id": "train_8", "label": "T8", "x": 980, "y": 190, "status": "+6 min"},
    ]
    points = []
    strategies4 = TRIO + ["avoid_follow_up_conflicts", "maintain_current_plan"]
    eff = trio_effects()
    eff["avoid_follow_up_conflicts"] = CANON_EFFECTS["avoid_follow_up_conflicts"]
    eff["maintain_current_plan"] = CANON_EFFECTS["maintain_current_plan"]
    n = 15
    for i in range(n):
        # rapid-fire decisions, high pressure throughout, a quick-accept run 6..9
        pressure = "HIGH" if i < 5 else "STRESS"
        critical = i in (1, 4, 10, 12)
        crit_ids = ["train_5", "train_6"] if critical else []
        baseline = "minimize_delay"
        personalized = (
            "protect_critical_connection" if critical else "avoid_follow_up_conflicts"
        )
        learning = i in (4, 12)
        unexpected = i in (3, 11)
        confidence = "low" if i >= 5 else "medium"
        minute = i * 4
        # Only a few genuinely consequential moments interrupt; the rest stream
        # by as AI-handled info (stress = concurrency & triage, not a quiz).
        if critical:
            event = _event("connection_risk",
                           "Connection at risk under heavy load: Train 5 → Train 6",
                           severity="intervention")
        elif i == 8:
            event = _event("disruption",
                           "Cascading disruption — network stability at risk",
                           severity="intervention")
        elif i in (3, 11):
            event = _event("track_blocked",
                           "Track blocked near East Junction — rerouted by AI",
                           severity="info")
        elif i >= 8:
            event = _event("disruption", "Multiple trains delayed — managed by AI",
                           severity="info")
        else:
            event = _event("train_delayed", "Train delayed — resolved by AI",
                           severity="info")
        points.append(
            dp(
                step=i + 1,
                time_label=f"14:{minute:02d}",
                pressure=pressure,
                sim_step=int((i + 1) / n * 380) + 10,
                event=event,
                description=(
                    "Rapid succession of conflicts. Trade-offs are unclear and "
                    "forecast confidence is low. Recommendations arrive quickly."
                ),
                affected=["train_1", "train_3", "train_5", "train_6", "train_8"],
                main_conflict="High-load multi-conflict at Center/East",
                critical=critical,
                buffer_min=3 if critical else None,
                delay=2 + (i % 4),
                ripple="high" if i >= 5 else "medium",
                follow_up=2 if i >= 8 else 1,
                confidence=confidence,
                strategies=strategies4,
                strategy_effects=eff,
                baseline=baseline,
                personalized=personalized,
                learning_influence=learning,
                outcomes={
                    **std_outcomes(exp_delay_prot=3, unexpected=unexpected),
                    "avoid_follow_up_conflicts": {
                        "expected": outcome(2, "At risk", 1, "strained"),
                        "observed": [
                            {"weight": 2, "values": outcome(2, "At risk", 1, "strained")},
                            {"weight": 2, "values": outcome(3, "At risk", 2, "unstable")},
                        ],
                    },
                    "maintain_current_plan": {
                        "expected": outcome(0, "At risk", 2, "strained"),
                        "observed": [
                            {"weight": 1, "values": outcome(0, "Broken", 3, "unstable")},
                        ],
                    },
                },
                conflict_node="east_junction",
                critical_ids=crit_ids,
                trains=trains,
                edge_status={
                    "lehrte->east_junction": "conflict",
                    "center->lehrte": "risk",
                    "west_junction->harburg": "risk",
                    "north->center": "risk",
                },
            )
        )
    return {
        "scenario_id": "stress_test",
        "name": "Stress Test",
        "difficulty": "Stress",
        "seed": 999,
        "total_steps": 400,
        "description": (
            "Many decisions, multiple disruptions, unclear trade-offs and elevated "
            "uncertainty. Recommendations follow each other quickly to provoke "
            "quick accepts and possible over-reliance behaviour."
        ),
        "decision_points": points,
    }


def demo_quick():
    """A short, presentation-friendly shift (~2 min): 3 interventions + 3 info."""
    trains = [
        {"id": "train_5", "label": "T5", "x": 200, "y": 190, "status": "+1 min"},
        {"id": "train_6", "label": "T6", "x": 700, "y": 190, "status": "on time"},
        {"id": "train_3", "label": "T3", "x": 560, "y": 110, "status": "on time"},
    ]
    times = ["08:00", "08:03", "08:06", "08:09", "08:12", "08:15"]
    points = []
    n = 6
    for i in range(n):
        critical = i in (1, 3, 5)  # 3 interventions
        crit_ids = ["train_5", "train_6"] if critical else []
        if critical:
            event = _event("connection_risk",
                           "Connection at risk: Train 5 → Train 6 at Center",
                           severity="intervention")
        else:
            event = _event("conflict", "Minor conflict resolved by AI at Center",
                           severity="info")
        points.append(
            dp(
                step=i + 1,
                time_label=times[i],
                pressure="MEDIUM",
                sim_step=int((i + 1) / n * 55) + 5,
                event=event,
                description=(
                    "Train 5 approaches Center; the Train 5 → Train 6 connection "
                    "has a limited buffer."
                    if critical
                    else "Routine headway conflict at Center."
                ),
                affected=["train_5", "train_6", "train_3"],
                main_conflict="Connection vs delay at Center",
                critical=critical,
                buffer_min=4 if critical else None,
                delay=2,
                ripple="low",
                follow_up=0,
                confidence="high",
                strategies=TRIO,
                strategy_effects=trio_effects(),
                baseline="minimize_delay",
                personalized="protect_critical_connection" if critical else "minimize_delay",
                learning_influence=False,
                outcomes=std_outcomes(exp_delay_prot=2),
                conflict_node="center",
                critical_ids=crit_ids,
                trains=trains,
                edge_status={"harburg->center": "risk"} if critical else None,
            )
        )
    return {
        "scenario_id": "demo_quick",
        "name": "Demo (2 min)",
        "difficulty": "Demo",
        "seed": 7,
        "total_steps": 60,
        "description": (
            "A short, guided shift for presentations: a few autonomous AI actions "
            "and three critical-connection decisions — ideal to show the full "
            "predict → decide → reflect → learn loop quickly."
        ),
        "decision_points": points,
    }


def punctuality_trap():
    """Goal-conflict story: optimising punctuality quietly breaks connections and
    strands more and more passengers. Choosing 'Minimize Delay' (the tempting
    default) reliably breaks the connection; 'Protect Critical Connection' keeps
    it for a little extra delay. The cost compounds as passenger loads rise."""
    trains = [
        {"id": "train_5", "label": "RE5", "x": 200, "y": 190, "status": "on time"},
        {"id": "train_6", "label": "RB6", "x": 700, "y": 190, "status": "waiting"},
        {"id": "train_3", "label": "ICE3", "x": 560, "y": 110, "status": "+1 min"},
    ]
    times = ["07:00", "07:08", "07:16", "07:24", "07:33",
             "07:42", "07:50", "07:58", "08:06"]
    # passenger load on the connection rises through the rush hour
    pax = [70, 110, 90, 180, 240, 160, 320, 210, 280]
    n = len(times)

    eff = trio_effects()

    def trap_outcomes(pax_here):
        return {
            # punctuality: keeps trains moving but BREAKS the connection
            "minimize_delay": {
                "expected": outcome(1, "At risk", 0, "stable"),
                "observed": [{"weight": 1, "values": outcome(1, "Broken", 0, "stable")}],
            },
            # protect: holds the connection for a little extra delay
            "protect_critical_connection": {
                "expected": outcome(3, "Protected", 0, "stable"),
                "observed": [{"weight": 1, "values": outcome(3, "Protected", 0, "stable")}],
            },
            "stabilize_network": {
                "expected": outcome(2, "At risk", 0, "stable"),
                "observed": [
                    {"weight": 3, "values": outcome(2, "At risk", 0, "stable")},
                    {"weight": 1, "values": outcome(2, "Broken", 0, "stable")},
                ],
            },
        }

    points = []
    for i in range(n):
        points.append(
            dp(
                step=i + 1,
                time_label=times[i],
                pressure="MEDIUM" if i < 5 else "HIGH",
                sim_step=int((i + 1) / n * 70) + 5,
                event=_event(
                    "connection_risk",
                    f"Connection at risk: RE5 → RB6 (est. ~{round(pax[i] / 10) * 10} "
                    f"passengers waiting)",
                    severity="intervention",
                ),
                description=(
                    f"RE5 approaches Center. Holding for the RB6 connection costs a "
                    f"few minutes; letting RE5 run keeps it punctual but breaks the "
                    f"connection for an estimated ~{round(pax[i] / 10) * 10} "
                    f"passengers."
                ),
                affected=["train_5", "train_6", "train_3"],
                main_conflict="Punctuality vs. the RE5 → RB6 connection",
                critical=True,
                buffer_min=2,
                delay=2,
                ripple="low",
                follow_up=0,
                confidence="high",
                strategies=TRIO,
                strategy_effects=eff,
                baseline="minimize_delay",          # the tempting default
                personalized=None,                   # AI recommends punctuality
                learning_influence=False,
                outcomes=trap_outcomes(pax[i]),
                conflict_node="center",
                critical_ids=["train_5", "train_6"],
                trains=trains,
                edge_status={"harburg->center": "risk"},
                passengers=pax[i],
            )
        )
    return {
        "scenario_id": "punctuality_trap",
        "name": "The Punctuality Trap",
        "difficulty": "Story",
        "seed": 21,
        "total_steps": 80,
        "description": (
            "A goal-conflict story. The AI defaults to punctuality — and every time "
            "you let it run, another connection breaks and more passengers are "
            "stranded. Feels great early; the bill arrives later. Try protecting "
            "connections instead and watch the trade-off."
        ),
        "decision_points": points,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for builder in (demo_quick, punctuality_trap, easy_morning, busy_junction,
                    disruption_cascade, stress_test):
        data = builder()
        path = OUT_DIR / f"{data['scenario_id']}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {path}  ({data['difficulty']}, {len(data['decision_points'])} decisions)")


if __name__ == "__main__":
    main()
