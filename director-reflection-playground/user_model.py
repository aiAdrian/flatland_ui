"""The AI's evolving belief about the human operator.

This is the piece that makes co-learning *felt* during a session: after each
committed decision the model updates, so its live recommendation adapts, it can
predict the operator's next choice, and it can expose "what I currently believe
about you". Still fully rule-based (no ML/LLM) -- it is a thin, transparent layer
on top of the existing ``pattern_analyzer``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pattern_analyzer import analyze_pattern
from strategies import (
    CONFIRMATION_DEFERRED,
    CONFIRMATION_QUICK_ACCEPT,
    STRATEGIES,
)

# confirmation modes that do NOT count as confirmed preference evidence
_NON_EVIDENCE_MODES = {CONFIRMATION_QUICK_ACCEPT, CONFIRMATION_DEFERRED}


def _is_evidence(episode: dict[str, Any]) -> bool:
    mode = episode.get("user_decision", {}).get("confirmation_mode")
    return mode not in _NON_EVIDENCE_MODES

# thresholds controlling when a *learned* preference overrides the scenario's
# baseline recommendation
_MIN_SAMPLE_FOR_ADAPT = 2
_MIN_CONFIDENCE_FOR_ADAPT = 0.6


@dataclass
class Prediction:
    strategy: str | None
    confidence: float
    basis: str  # "similar_context" | "overall_preference" | "cold_start"
    sample_size: int


@dataclass
class AdaptiveRecommendation:
    baseline: str
    recommended: str
    adjusted: bool
    source: str  # "baseline" | "scenario" | "learned" | "learned_confirmed"
    explanation: str
    learned_strategy: str | None = None
    confidence: float = 0.0
    applied_learning: str | None = None  # statement of a confirmed learning, if any


def learning_target(learning: dict[str, Any]) -> str | None:
    conditions = learning.get("conditions", {})
    return conditions.get("target_strategy") or learning.get("evidence", {}).get(
        "expected_pattern"
    )


def learning_applies(learning: dict[str, Any], context: dict[str, Any]) -> bool:
    """Rule-based check whether a confirmed learning fits the current context."""
    target = learning_target(learning)
    if not target:
        return False
    critical = bool(context.get("critical_connection"))
    ripple = str(context.get("ripple_risk", "")).lower()
    follow = int(context.get("expected_follow_up_conflicts", 0) or 0)

    if target == "protect_critical_connection":
        # protect when there IS a critical connection and no major follow-up risk
        return critical and follow == 0
    if target == "stabilize_network":
        # stabilise when the network is under stress
        return ripple in ("medium", "high") or follow > 0
    if target == "avoid_follow_up_conflicts":
        return follow > 0
    # generic: applies when a critical connection is at stake
    return critical


@dataclass
class UserModel:
    """Belief state about the operator.

    Combines within-session decisions with an optional cross-session profile:
    ``prior_preferences`` (decision tendencies carried over) and
    ``confirmed_learnings`` (explicitly agreed rules that steer recommendations).
    """

    episodes: list[dict[str, Any]] = field(default_factory=list)
    prior_preferences: dict[str, int] = field(default_factory=dict)
    confirmed_learnings: list[dict[str, Any]] = field(default_factory=list)

    def _evidence_episodes(self) -> list[dict[str, Any]]:
        """Only decisions that reflect a *deliberate* preference count toward the
        model — passive accepts and deadline deferrals are excluded."""
        return [ep for ep in self.episodes if _is_evidence(ep)]

    # -- overall preferences ---------------------------------------------- #
    def preferences(self) -> list[tuple[str, float, int]]:
        """Return (strategy_id, weight, count) sorted by weight, recency-weighted.

        More recent decisions count a little more so the belief visibly shifts as
        the operator changes behaviour.
        """
        counts: dict[str, float] = {}
        raw: dict[str, int] = {}
        # carried-over tendencies from prior sessions (as a warm-start base)
        for strat, c in self.prior_preferences.items():
            counts[strat] = counts.get(strat, 0.0) + c * 0.6
            raw[strat] = raw.get(strat, 0) + c
        evidence = self._evidence_episodes()
        n = len(evidence)
        for i, ep in enumerate(evidence):
            strat = ep.get("user_decision", {}).get("selected_strategy")
            if not strat:
                continue
            # linear recency weight from 1.0 (oldest) to 2.0 (newest)
            weight = 1.0 + (i / max(n - 1, 1))
            counts[strat] = counts.get(strat, 0.0) + weight
            raw[strat] = raw.get(strat, 0) + 1
        total = sum(counts.values())
        if total == 0:
            return []
        result = [(s, round(w / total, 3), raw[s]) for s, w in counts.items()]
        result.sort(key=lambda t: t[1], reverse=True)
        return result

    @property
    def sample_size(self) -> int:
        return len(self._evidence_episodes())

    # -- context helpers -------------------------------------------------- #
    @staticmethod
    def _reference_from_decision_point(dp: dict[str, Any], step: int) -> dict[str, Any]:
        s = dp.get("situation", {})
        return {
            "decision_id": f"PENDING-{step}",
            "simulation_step": step,
            "context": {
                "critical_connection": s.get("critical_connection", False),
                "extra_delay_minutes": s.get("current_delay_min"),
                "ripple_risk": s.get("ripple_risk"),
                "expected_follow_up_conflicts": s.get("expected_follow_up_conflicts", 0),
                "forecast_confidence": s.get("forecast_confidence"),
            },
            "user_decision": {},
        }

    def _matching_learning(self, dp: dict[str, Any], strategies: list[str]):
        """Return (learning, target) for the first confirmed learning that
        applies to this context and whose target is available here."""
        context = self._reference_from_decision_point(dp, 0)["context"]
        for learning in self.confirmed_learnings:
            target = learning_target(learning)
            if target in strategies and learning_applies(learning, context):
                return learning, target
        return None, None

    # -- prediction ------------------------------------------------------- #
    def predict(self, dp: dict[str, Any], step: int) -> Prediction:
        """Predict which strategy the operator will pick for this decision point."""
        ref = self._reference_from_decision_point(dp, step)
        pattern = analyze_pattern(self._evidence_episodes(), ref)

        if pattern["sample_size"] > 0:
            return Prediction(
                strategy=pattern["expected_strategy"],
                confidence=pattern["confidence"],
                basis="similar_context",
                sample_size=pattern["sample_size"],
            )

        prefs = self.preferences()
        if prefs:
            strat, weight, count = prefs[0]
            # distinguish a warm start (from the carried-over profile) from a
            # within-session tendency
            basis = "profile" if self.sample_size == 0 and self.prior_preferences \
                else "overall_preference"
            return Prediction(
                strategy=strat,
                confidence=round(weight, 2),
                basis=basis,
                sample_size=self.sample_size,
            )

        return Prediction(strategy=None, confidence=0.0, basis="cold_start",
                          sample_size=0)

    # -- adaptive recommendation ------------------------------------------ #
    def adaptive_recommendation(
        self, dp: dict[str, Any], step: int
    ) -> AdaptiveRecommendation:
        baseline = dp.get("baseline_recommendation")
        scenario_personalized = dp.get("personalized_recommendation")
        strategies = dp.get("strategies", [])

        # 0) a confirmed cross-session learning that matches this context wins.
        learning, target = self._matching_learning(dp, strategies)
        if learning and target:
            base_name = STRATEGIES[baseline].name if baseline in STRATEGIES else baseline
            target_name = STRATEGIES[target].name if target in STRATEGIES else target
            return AdaptiveRecommendation(
                baseline=baseline,
                recommended=target,
                adjusted=target != baseline,
                source="learned_confirmed",
                explanation=(
                    f"Applying a preference you confirmed earlier: "
                    f"\"{learning['statement']}\" → {target_name} "
                    f"(baseline would be {base_name})."
                ),
                learned_strategy=target,
                confidence=0.9,
                applied_learning=learning["statement"],
            )

        ref = self._reference_from_decision_point(dp, step)
        pattern = analyze_pattern(self._evidence_episodes(), ref)
        learned = pattern["expected_strategy"]
        confidence = pattern["confidence"]

        # 1) strong learned preference in a similar context wins
        if (
            learned
            and learned in strategies
            and pattern["sample_size"] >= _MIN_SAMPLE_FOR_ADAPT
            and confidence >= _MIN_CONFIDENCE_FOR_ADAPT
        ):
            name = STRATEGIES[learned].name if learned in STRATEGIES else learned
            base_name = (
                STRATEGIES[baseline].name if baseline in STRATEGIES else baseline
            )
            adjusted = learned != baseline
            explanation = (
                f"You chose {name} in {pattern['sample_size']} similar situation(s) "
                f"({int(confidence * 100)}% of the time). I'm weighting that "
                f"preference and now recommend {name} instead of {base_name}."
                if adjusted
                else f"Your learned preference ({name}) agrees with the baseline here."
            )
            return AdaptiveRecommendation(
                baseline=baseline,
                recommended=learned,
                adjusted=adjusted,
                source="learned",
                explanation=explanation,
                learned_strategy=learned,
                confidence=confidence,
            )

        # 2) fall back to the scenario's own personalization hint
        if scenario_personalized and scenario_personalized != baseline:
            return AdaptiveRecommendation(
                baseline=baseline,
                recommended=scenario_personalized,
                adjusted=True,
                source="scenario",
                explanation=(
                    "Scenario-configured personalization (no strong learned "
                    "preference yet)."
                ),
                confidence=0.0,
            )

        # 3) plain baseline
        return AdaptiveRecommendation(
            baseline=baseline,
            recommended=baseline,
            adjusted=False,
            source="baseline",
            explanation="Baseline recommendation (still learning your preferences).",
            confidence=0.0,
        )
