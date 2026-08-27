"""Rule-based user pattern analysis.

No machine learning here. Given the decision episodes of the current session we
find episodes with a *similar* context to a reference episode and report which
strategy the user tends to pick in those situations, plus a naive confidence.
"""

from __future__ import annotations

from typing import Any


# Confirmation modes that do not express a preference: the operator either
# clicked the recommendation through or let the deadline decide. Kept in sync
# with ``user_model._NON_EVIDENCE_MODES`` and ``values._NON_EVIDENCE``.
NON_EVIDENCE_MODES = {"quick_accept", "deferred_to_ai"}

# A pattern claim needs at least this many similar prior decisions before it may
# be phrased as a tendency ("you mostly choose X") rather than a single case.
MIN_SAMPLE_FOR_TENDENCY = 2


def is_preference_evidence(episode: dict[str, Any]) -> bool:
    mode = episode.get("user_decision", {}).get("confirmation_mode")
    return mode not in NON_EVIDENCE_MODES


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
    evidence_only: bool = False,
) -> dict[str, Any]:
    """Return the expected user pattern for contexts similar to the reference.

    Only episodes *before* the reference (by simulation step) plus the reference
    itself when ``exclude_reference`` is False are considered similar evidence.

    With ``evidence_only`` the passive confirmation modes are dropped, so a
    recommendation the operator merely clicked through cannot later be quoted
    back to them as their own preference.
    """
    ref_ctx = reference_episode.get("context", {})
    ref_step = reference_episode.get("simulation_step", -1)

    counts: dict[str, int] = {}
    similar_ids: list[str] = []
    ids_by_strategy: dict[str, list[dict[str, Any]]] = {}
    for ep in episodes:
        if evidence_only and not is_preference_evidence(ep):
            # a passively accepted recommendation is not a stated preference
            continue
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
            ids_by_strategy.setdefault(strategy, []).append(
                {
                    "decision_id": ep.get("decision_id"),
                    "time_label": ep.get("context", {}).get("time_label", ""),
                }
            )

    total = sum(counts.values())
    if total == 0:
        return {
            "expected_strategy": None,
            "confidence": 0.0,
            "counts": {},
            "sample_size": 0,
            "similar_decision_ids": [],
            "decisions_by_strategy": {},
        }

    expected_strategy = max(counts, key=counts.get)
    confidence = round(counts[expected_strategy] / total, 2)
    return {
        "expected_strategy": expected_strategy,
        "confidence": confidence,
        "counts": counts,
        "sample_size": total,
        "similar_decision_ids": similar_ids,
        # which decisions back which strategy -- lets the UI name the evidence
        # instead of only counting it
        "decisions_by_strategy": ids_by_strategy,
    }


def pattern_relation(pattern: dict[str, Any], selected_strategy: str) -> str:
    """Classify the selected strategy against the expected pattern."""
    expected = pattern.get("expected_strategy")
    if not expected or pattern.get("sample_size", 0) == 0:
        return "no_pattern"
    if expected == selected_strategy:
        return "confirmation"
    return "deviation"
