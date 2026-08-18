"""Selects the (at most three) most interesting decisions to reflect on.

Uses a transparent rule-based scoring scheme. Each decision episode is scored,
tagged with a reflection "case type", and the top scoring, diverse cases are
returned.
"""

from __future__ import annotations

from typing import Any

from pattern_analyzer import analyze_pattern, pattern_relation
from strategies import (
    CASE_LEARNING_ADJUSTED,
    CASE_OVERRIDE,
    CASE_PATTERN_CONFIRMATION,
    CASE_PATTERN_DEVIATION,
    CASE_QUICK_ACCEPT,
    CASE_UNEXPECTED_OUTCOME,
    CONFIRMATION_DEFERRED,
    CONFIRMATION_INFORMED_ACCEPT,
    CONFIRMATION_OVERRIDE,
    CONFIRMATION_QUICK_ACCEPT,
    RATIONALE_FREE_TEXT,
    RATIONALE_REASON_TAGS,
)

MAX_REFLECTION_MOMENTS = 3


def score_episode(
    episode: dict[str, Any], all_episodes: list[dict[str, Any]]
) -> dict[str, Any]:
    """Score a single episode and determine its dominant case type."""
    user = episode.get("user_decision", {})
    outcome = episode.get("outcome", {})
    recommendation = episode.get("recommendation", {})

    confirmation_mode = user.get("confirmation_mode")
    rationale_mode = user.get("rationale_mode")
    selected = user.get("selected_strategy")

    pattern = analyze_pattern(all_episodes, episode)
    relation = pattern_relation(pattern, selected)

    score = 0.0
    reasons: list[str] = []
    case_type = None

    # Pattern deviation
    if relation == "deviation":
        score += 5
        reasons.append("Pattern deviation (+5)")
        case_type = CASE_PATTERN_DEVIATION

    # Override with free text
    is_override = confirmation_mode == CONFIRMATION_OVERRIDE
    if is_override and rationale_mode == RATIONALE_FREE_TEXT:
        score += 4
        reasons.append("Override with free text (+4)")
        case_type = case_type or CASE_OVERRIDE

    # Unexpected outcome
    if outcome.get("status") == "Unexpected outcome":
        score += 4
        reasons.append("Unexpected outcome (+4)")
        case_type = case_type or CASE_UNEXPECTED_OUTCOME

    # Learning-adjusted recommendation
    if recommendation.get("learning_adjustment_applied"):
        score += 3
        reasons.append("Learning-adjusted recommendation (+3)")
        case_type = case_type or CASE_LEARNING_ADJUSTED

    # Override with reason tag
    if is_override and rationale_mode == RATIONALE_REASON_TAGS:
        score += 3
        reasons.append("Override with reason tag (+3)")
        case_type = case_type or CASE_OVERRIDE

    # Generic override (no reason)
    if is_override and case_type is None:
        case_type = CASE_OVERRIDE

    # Pattern confirmation
    if relation == "confirmation":
        score += 2
        reasons.append("Pattern confirmation (+2)")
        case_type = case_type or CASE_PATTERN_CONFIRMATION

    # Informed accept
    if confirmation_mode == CONFIRMATION_INFORMED_ACCEPT:
        score += 1
        reasons.append("Informed accept (+1)")

    # Quick accept
    if confirmation_mode == CONFIRMATION_QUICK_ACCEPT:
        reasons.append("Quick accept (+0)")
        case_type = case_type or CASE_QUICK_ACCEPT

    # Deferred to AI (deadline passed) -- an over-reliance signal
    if confirmation_mode == CONFIRMATION_DEFERRED:
        score += 2
        reasons.append("Deferred to AI / deadline passed (+2)")
        case_type = case_type or CASE_QUICK_ACCEPT

    if case_type is None:
        case_type = CASE_PATTERN_CONFIRMATION

    return {
        "decision_id": episode.get("decision_id"),
        "score": score,
        "case_type": case_type,
        "reasons": reasons,
        "pattern": pattern,
        "pattern_relation": relation,
        "episode": episode,
    }


def _count_quick_accept_runs(episodes: list[dict[str, Any]]) -> list[str]:
    """Return decision_ids that belong to a run of >=3 consecutive quick accepts."""
    run: list[str] = []
    flagged: list[str] = []
    for ep in episodes:
        mode = ep.get("user_decision", {}).get("confirmation_mode")
        if mode in (CONFIRMATION_QUICK_ACCEPT, CONFIRMATION_DEFERRED):
            run.append(ep.get("decision_id"))
        else:
            if len(run) >= 3:
                flagged.extend(run)
            run = []
    if len(run) >= 3:
        flagged.extend(run)
    return flagged


def select_reflection_moments(
    episodes: list[dict[str, Any]],
    max_moments: int = MAX_REFLECTION_MOMENTS,
) -> list[dict[str, Any]]:
    """Score every episode and pick the most interesting, diverse ones."""
    if not episodes:
        return []

    scored = [score_episode(ep, episodes) for ep in episodes]

    # Boost quick-accept runs (over-reliance signal) and mark them as such.
    quick_run_ids = set(_count_quick_accept_runs(episodes))
    for s in scored:
        if s["decision_id"] in quick_run_ids:
            s["score"] += 2
            s["reasons"].append("Part of a quick-accept run (+2)")
            if s["case_type"] == CASE_PATTERN_CONFIRMATION:
                s["case_type"] = CASE_QUICK_ACCEPT

    scored.sort(key=lambda s: s["score"], reverse=True)

    # Prefer diversity of case types: deviation, override, unexpected/learning.
    preferred_order = [
        CASE_PATTERN_DEVIATION,
        CASE_OVERRIDE,
        CASE_UNEXPECTED_OUTCOME,
        CASE_LEARNING_ADJUSTED,
        CASE_QUICK_ACCEPT,
        CASE_PATTERN_CONFIRMATION,
    ]

    selected: list[dict[str, Any]] = []
    used_case_types: set[str] = set()

    for case_type in preferred_order:
        if len(selected) >= max_moments:
            break
        for s in scored:
            if s in selected:
                continue
            if s["case_type"] == case_type and s["score"] > 0:
                selected.append(s)
                used_case_types.add(case_type)
                break

    # Fill remaining slots with the highest scoring leftovers (score > 0).
    if len(selected) < max_moments:
        for s in scored:
            if len(selected) >= max_moments:
                break
            if s in selected or s["score"] <= 0:
                continue
            selected.append(s)

    selected.sort(key=lambda s: s["episode"].get("simulation_step", 0))
    return selected
