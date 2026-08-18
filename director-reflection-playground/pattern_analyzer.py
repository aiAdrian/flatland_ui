"""Rule-based user pattern analysis.

No machine learning here. Given the decision episodes of the current session we
find episodes with a *similar* context to a reference episode and report which
strategy the user tends to pick in those situations, plus a naive confidence.
"""

from __future__ import annotations

from typing import Any


def _ripple_bucket(value: str | None) -> str:
    if value in ("low", "medium"):
        return "low_or_medium"
    return value or "unknown"


def _is_similar(ref_ctx: dict[str, Any], other_ctx: dict[str, Any]) -> bool:
    """Simple rule-based similarity between two decision contexts."""
    if ref_ctx.get("critical_connection") != other_ctx.get("critical_connection"):
        return False

    # extra delay must be in the same "limited" bucket (<= 3 min)
    ref_delay = ref_ctx.get("extra_delay_minutes") or 0
    other_delay = other_ctx.get("extra_delay_minutes") or 0
    if (ref_delay <= 3) != (other_delay <= 3):
        return False

    if _ripple_bucket(ref_ctx.get("ripple_risk")) != _ripple_bucket(
        other_ctx.get("ripple_risk")
    ):
        return False

    return True


def analyze_pattern(
    episodes: list[dict[str, Any]],
    reference_episode: dict[str, Any],
    exclude_reference: bool = True,
) -> dict[str, Any]:
    """Return the expected user pattern for contexts similar to the reference.

    Only episodes *before* the reference (by simulation step) plus the reference
    itself when ``exclude_reference`` is False are considered similar evidence.
    """
    ref_ctx = reference_episode.get("context", {})
    ref_step = reference_episode.get("simulation_step", -1)

    counts: dict[str, int] = {}
    similar_ids: list[str] = []
    for ep in episodes:
        if ep.get("simulation_step", -1) >= ref_step:
            # only look at prior decisions to model an evolving pattern
            if not (
                not exclude_reference
                and ep.get("decision_id") == reference_episode.get("decision_id")
            ):
                continue
        if not _is_similar(ref_ctx, ep.get("context", {})):
            continue
        strategy = ep.get("user_decision", {}).get("selected_strategy")
        if strategy:
            counts[strategy] = counts.get(strategy, 0) + 1
            similar_ids.append(ep.get("decision_id"))

    total = sum(counts.values())
    if total == 0:
        return {
            "expected_strategy": None,
            "confidence": 0.0,
            "counts": {},
            "sample_size": 0,
            "similar_decision_ids": [],
        }

    expected_strategy = max(counts, key=counts.get)
    confidence = round(counts[expected_strategy] / total, 2)
    return {
        "expected_strategy": expected_strategy,
        "confidence": confidence,
        "counts": counts,
        "sample_size": total,
        "similar_decision_ids": similar_ids,
    }


def pattern_relation(pattern: dict[str, Any], selected_strategy: str) -> str:
    """Classify the selected strategy against the expected pattern."""
    expected = pattern.get("expected_strategy")
    if not expected or pattern.get("sample_size", 0) == 0:
        return "no_pattern"
    if expected == selected_strategy:
        return "confirmation"
    return "deviation"
