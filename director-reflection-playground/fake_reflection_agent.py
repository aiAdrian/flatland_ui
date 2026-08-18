"""Reflection agent abstraction + a rule/template based fake implementation.

The rest of the application depends ONLY on the ``ReflectionAgent`` interface.
Version 0.1 ships ``FakeReflectionAgent`` (no LLM). A future
``LocalLLMReflectionAgent`` can be dropped in without touching the UI, as long
as it implements the same three methods.
"""

from __future__ import annotations

import abc
from typing import Any

from strategies import (
    CASE_LEARNING_ADJUSTED,
    CASE_OVERRIDE,
    CASE_PATTERN_CONFIRMATION,
    CASE_PATTERN_DEVIATION,
    CASE_QUICK_ACCEPT,
    CASE_UNEXPECTED_OUTCOME,
    strategy_name,
)

# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #


class ReflectionAgent(abc.ABC):
    """Stable interface for anything that drives the reflection dialogue."""

    @abc.abstractmethod
    def generate_reflection_question(self, case: dict[str, Any]) -> dict[str, Any]:
        """Return a question dict: {summary, expected, actual, question, options}."""

    @abc.abstractmethod
    def interpret_answer(
        self, case: dict[str, Any], answer: dict[str, Any]
    ) -> dict[str, Any]:
        """Turn a raw user answer into a normalised interpretation."""

    @abc.abstractmethod
    def propose_learning(
        self, case: dict[str, Any], answer: dict[str, Any]
    ) -> dict[str, Any]:
        """Propose a learning candidate based on the case and interpreted answer."""


# --------------------------------------------------------------------------- #
# Fake implementation
# --------------------------------------------------------------------------- #

# Answer option tags reused across several case types.
_DIFFERENCE_OPTIONS = [
    "Follow-up conflicts expected",
    "Network stability was more important",
    "Forecast confidence was low",
    "Time pressure",
    "Other",
]


class FakeReflectionAgent(ReflectionAgent):
    """Template + rule driven reflection agent (no LLM)."""

    def _situation_summary(self, case: dict[str, Any]) -> str:
        ep = case["episode"]
        ctx = ep.get("context", {})
        parts = []
        if ctx.get("critical_connection"):
            parts.append("a critical connection was involved")
        buf = ctx.get("connection_buffer_min")
        if buf is not None:
            parts.append(f"connection buffer {buf} min")
        parts.append(f"ripple risk {ctx.get('ripple_risk', 'unknown')}")
        fu = ctx.get("expected_follow_up_conflicts")
        if fu is not None:
            parts.append(f"{fu} expected follow-up conflicts")
        time_label = ctx.get("time_label", "")
        return f"At {time_label}: " + ", ".join(parts) + "."

    def generate_reflection_question(self, case: dict[str, Any]) -> dict[str, Any]:
        ep = case["episode"]
        case_type = case["case_type"]
        pattern = case.get("pattern", {})
        selected = ep.get("user_decision", {}).get("selected_strategy")
        expected_pattern = pattern.get("expected_strategy")

        summary = self._situation_summary(case)
        expected_txt = strategy_name(expected_pattern)
        actual_txt = strategy_name(selected)

        if case_type == CASE_PATTERN_DEVIATION:
            question = (
                f"In similar situations you have mostly chosen "
                f"'{expected_txt}'. This time you chose '{actual_txt}'. "
                f"What was different this time?"
            )
            options = _DIFFERENCE_OPTIONS
        elif case_type == CASE_PATTERN_CONFIRMATION:
            question = (
                "This decision matches your existing pattern. "
                "Was the critical connection the main reason again?"
            )
            options = [
                "Yes, critical connection",
                "Low ripple risk",
                "Limited additional delay",
                "Other",
            ]
        elif case_type == CASE_UNEXPECTED_OUTCOME:
            question = (
                "You chose a strategy in line with your pattern, but the outcome "
                "was worse than expected. Would you make the same decision again "
                "under these conditions?"
            )
            options = [
                "Yes, same decision",
                "No, I would change it",
                "Only if forecast confidence were higher",
                "Other",
            ]
        elif case_type == CASE_QUICK_ACCEPT:
            question = (
                "During the stressful phase you accepted several recommendations "
                "quickly. Should these decisions count as evidence for your "
                "preferences?"
            )
            options = [
                "Yes, they reflect my preference",
                "No, they were just time pressure",
                "Only the non-trivial ones",
                "Other",
            ]
        elif case_type == CASE_OVERRIDE:
            question = (
                f"You overrode the recommendation and chose '{actual_txt}'. "
                f"What was the main driver behind that override?"
            )
            options = _DIFFERENCE_OPTIONS
        elif case_type == CASE_LEARNING_ADJUSTED:
            question = (
                "This recommendation was adjusted based on a learned preference. "
                "Did the adjusted recommendation match your intent?"
            )
            options = [
                "Yes, it matched",
                "No, the baseline was better",
                "Partly",
                "Other",
            ]
        else:
            question = "Would you like to reflect on this decision?"
            options = ["Yes", "No"]

        return {
            "case_type": case_type,
            "summary": summary,
            "expected_pattern": expected_txt,
            "actual_decision": actual_txt,
            "question": question,
            "options": options,
        }

    def interpret_answer(
        self, case: dict[str, Any], answer: dict[str, Any]
    ) -> dict[str, Any]:
        selected_options = answer.get("selected_options", [])
        free_text = (answer.get("free_text") or "").strip()

        interpretation = {
            "case_type": case["case_type"],
            "selected_options": selected_options,
            "free_text": free_text,
            "signals": {},
        }

        signals = interpretation["signals"]
        if "Follow-up conflicts expected" in selected_options:
            signals["follow_up_conflicts_expected"] = True
        if "Network stability was more important" in selected_options:
            signals["network_priority"] = True
        if "Forecast confidence was low" in selected_options:
            signals["low_forecast_confidence"] = True
        if "Time pressure" in selected_options:
            signals["time_pressure"] = True
        if any(o.startswith("Yes") for o in selected_options):
            signals["affirmative"] = True
        if any(o.startswith("No") for o in selected_options):
            signals["negative"] = True
        if free_text:
            signals["has_free_text"] = True

        return interpretation

    def propose_learning(
        self, case: dict[str, Any], answer: dict[str, Any]
    ) -> dict[str, Any]:
        ep = case["episode"]
        interpretation = self.interpret_answer(case, answer)
        signals = interpretation["signals"]
        pattern = case.get("pattern", {})
        expected_pattern = pattern.get("expected_strategy")
        selected = ep.get("user_decision", {}).get("selected_strategy")
        free_text = interpretation["free_text"]

        counts = pattern.get("counts", {})
        supporting = counts.get(expected_pattern, 0) if expected_pattern else 0
        contradictory = sum(counts.values()) - supporting

        statement = None
        conditions: dict[str, Any] = {}
        boundaries: list[str] = []

        # Rule: follow-up conflicts expected + protect pattern -> boundary learning
        if (
            signals.get("follow_up_conflicts_expected")
            and expected_pattern == "protect_critical_connection"
        ):
            statement = (
                "Protect critical connections when additional delay is limited "
                "and no significant follow-up conflicts are expected."
            )
            conditions = {
                "extra_delay_limited": True,
                "follow_up_conflicts_expected": False,
            }
            boundaries = [
                "Reconsider when follow-up conflicts are expected.",
            ]
        elif signals.get("network_priority"):
            statement = (
                "Prefer network stabilisation over connection protection when "
                "network stability is the greater concern."
            )
            conditions = {"network_priority": True}
        elif signals.get("low_forecast_confidence"):
            statement = (
                "Treat recommendations cautiously when forecast confidence is low."
            )
            conditions = {"low_forecast_confidence": True}

        # Free text always produces a template exception learning if present.
        if free_text:
            statement = (
                f"User indicated an exception to the existing preference: {free_text}"
            )
            conditions = conditions or {"user_specified": True}

        if statement is None and expected_pattern:
            # generic confirmation learning
            statement = (
                f"User tends to choose '{strategy_name(expected_pattern)}' in "
                f"similar situations."
            )
            conditions = {"pattern_confirmation": True}

        if statement is None:
            statement = "No clear learning could be derived from this reflection."

        confidence = self._confidence_label(supporting, contradictory)

        # the strategy this learning nudges future recommendations toward
        if signals.get("network_priority"):
            target = "stabilize_network"
        elif expected_pattern:
            target = expected_pattern
        else:
            target = selected
        conditions = {**conditions, "target_strategy": target}

        return {
            "case_type": case["case_type"],
            "statement": statement,
            "conditions": conditions,
            "boundaries": boundaries,
            "confidence": confidence,
            "evidence": {
                "supporting_decisions": supporting,
                "contradictory_decisions": contradictory,
                "reference_decision_id": ep.get("decision_id"),
                "expected_pattern": expected_pattern,
                "actual_decision": selected,
            },
            "user_reflection_text": free_text or None,
        }

    @staticmethod
    def _confidence_label(supporting: int, contradictory: int) -> str:
        if supporting >= 4 and contradictory <= 1:
            return "High"
        if supporting >= 2:
            return "Medium"
        return "Low"
