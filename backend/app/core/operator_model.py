"""Operator model — Co-Learning **Level B**: the AI learns to work with the human.

See `docs/plans/co-learning-direction.md` ("Suggested order: Level B first —
concrete first building block: an operator model in the backend that (a) estimates
reward weights from overrides/accept-reject → feeds KPI/scoring, and (b) proposes
autonomy / `optionPresentation` from the intervention/trust history").

This module is that building block. It is deliberately:

* **Pure & mode-agnostic** — no FastAPI, no Flatland, no I/O in the logic part;
  the API layer feeds it `DecisionSignal`s and reads derived views back.
* **Inverse-RL-lite** — the operator's *value axis* per decision is inferred from
  which KPI axis the chosen option was best on (their revealed trade-off), not
  from a self-reported slider.
* **Evidence-guarded** — passively accepted recommendations ("just following")
  and timed-out decisions do NOT shape the preference model. Only *deliberate*
  choices count. This is the same overfitting guard the frontend
  `LearningStore` applies to hypotheses ('yes' = rule, 'once' = one-off), lifted
  to the accept/override signal itself.
* **Cross-session** — the profile is keyed by operator, so a later session starts
  *warm* and confirmed preferences can re-rank recommendations.

No LLM and no training loop: light, transparent rules (as the plan requires).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

# ── Value axes ──────────────────────────────────────────────────────────────
# Mapped onto the KPI vocabulary the HMI already speaks (`ScenarioKpis`):
#   punctuality -> totalDelay / meanDelay      stability  -> deadlocks
#   throughput  -> done                        connection -> connection proxy
VALUE_PUNCTUALITY = "punctuality"
VALUE_THROUGHPUT = "throughput"
VALUE_STABILITY = "stability"
VALUE_CONNECTION = "connection"

VALUE_AXES = (VALUE_PUNCTUALITY, VALUE_THROUGHPUT, VALUE_STABILITY, VALUE_CONNECTION)

VALUE_LABELS = {
    VALUE_PUNCTUALITY: "Punctuality-first",
    VALUE_THROUGHPUT: "Throughput-first",
    VALUE_STABILITY: "Stability-first",
    VALUE_CONNECTION: "Connection-first",
}

# Recency weighting: the newest deliberate decision counts up to this much more
# than the oldest, so a changing stance shows up instead of being averaged away.
_RECENCY_MAX_WEIGHT = 2.0
# Carried-over (previous sessions) evidence is damped relative to this session.
_PRIOR_WEIGHT = 0.6
# Thresholds before a learned preference is allowed to re-rank a recommendation.
_MIN_EVIDENCE_FOR_ADAPT = 2
_MIN_CONFIDENCE_FOR_ADAPT = 0.6
# Deliberate decisions needed before a dial proposal reaches full strength.
_FULL_CONFIDENCE_EVIDENCE = 6


# ── Signals ─────────────────────────────────────────────────────────────────
@dataclass
class DecisionSignal:
    """One interaction signal: what the operator did at a decision point.

    ``deliberate`` is the evidence gate — True when the operator gave a reason,
    overrode the AI, or otherwise engaged; False for a passive accept
    ("just following the recommendation") or a timed-out/auto-applied decision.
    """

    step: int
    handle: int
    option_id: Optional[str] = None
    #: value axis this choice optimised, if known (see ``infer_value_axis``)
    value: Optional[str] = None
    #: was the AI's own recommendation taken?
    followed_ai: bool = False
    #: deliberate (reasoned / override) vs. passive (silent accept / timeout)
    deliberate: bool = False
    #: situation snapshot (``connection_critical`` / ``low_delay`` / ``low_ripple``)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def is_evidence(self) -> bool:
        return self.deliberate and self.value is not None


@dataclass
class ConfirmedLearning:
    """A preference the operator explicitly confirmed ('yes' in the HMI)."""

    statement: str
    target_value: str
    conditions: dict[str, Any] = field(default_factory=dict)


# ── Derived views ───────────────────────────────────────────────────────────
@dataclass
class ValueProfile:
    dominant: Optional[str]
    label: str
    dominant_pct: int
    distribution: list[tuple[str, float, int]]
    total: int


@dataclass
class Prediction:
    value: Optional[str]
    confidence: float
    #: "similar_context" | "overall_preference" | "profile" | "cold_start"
    basis: str
    sample_size: int


@dataclass
class Adjustment:
    """A re-ranking hint for the recommender: prefer ``target_value``."""

    target_value: str
    reason: str
    applied_learning: Optional[str] = None
    confidence: float = 0.0


# ── Inverse-RL-lite: which axis did this option optimise? ───────────────────
def infer_value_axis(
    chosen: dict[str, Any],
    alternatives: Iterable[dict[str, Any]],
    context: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Infer the value axis a chosen option expresses from its KPI deltas.

    ``chosen`` / ``alternatives`` are ``ScenarioKpis``-shaped dicts (the deltas).
    The axis is the one where the chosen option is (co-)best among the offered
    options — i.e. the trade-off the operator revealed by picking it. Returns
    ``None`` when the option is best on nothing (a compromise) and no context
    hint applies.
    """
    others = [a for a in alternatives if a is not chosen]
    if not others:
        # Nothing to compare against: fall back to the context hint.
        return VALUE_CONNECTION if (context or {}).get("connection_critical") else None

    def best_on(key: str, lower_is_better: bool) -> bool:
        mine = chosen.get(key)
        if mine is None:
            return False
        vals = [o.get(key) for o in others if o.get(key) is not None]
        if not vals:
            return False
        return all(mine <= v for v in vals) if lower_is_better else all(mine >= v for v in vals)

    # Order matters only for ties; connection is checked first because it is the
    # axis the KPI set cannot express numerically.
    if (context or {}).get("connection_critical") and (context or {}).get("protects_connection"):
        return VALUE_CONNECTION
    if best_on("deadlocks", lower_is_better=True):
        return VALUE_STABILITY
    if best_on("totalDelay", lower_is_better=True) or best_on("meanDelay", True):
        return VALUE_PUNCTUALITY
    if best_on("done", lower_is_better=False):
        return VALUE_THROUGHPUT
    return None


# ── Profile ─────────────────────────────────────────────────────────────────
@dataclass
class OperatorProfile:
    """Everything the AI believes about one operator, across sessions."""

    operator_id: str
    signals: list[DecisionSignal] = field(default_factory=list)
    prior_values: dict[str, int] = field(default_factory=dict)
    confirmed_learnings: list[ConfirmedLearning] = field(default_factory=list)
    prior_sessions: int = 0

    # -- bookkeeping ------------------------------------------------------- #
    @property
    def is_warm(self) -> bool:
        return bool(self.prior_values) or bool(self.confirmed_learnings)

    def evidence(self) -> list[DecisionSignal]:
        return [s for s in self.signals if s.is_evidence]

    @property
    def sample_size(self) -> int:
        return len(self.evidence())

    @property
    def passive_count(self) -> int:
        return sum(1 for s in self.signals if not s.deliberate)

    def trust_ratio(self) -> float:
        """Share of decisions where the operator went with the AI (0..1)."""
        if not self.signals:
            return 0.0
        return sum(1 for s in self.signals if s.followed_ai) / len(self.signals)

    # -- preferences ------------------------------------------------------- #
    def value_weights(self) -> dict[str, float]:
        """Recency-weighted, normalised weights per value axis (reward weights)."""
        weights: dict[str, float] = {
            v: c * _PRIOR_WEIGHT for v, c in self.prior_values.items()
        }
        evidence = self.evidence()
        n = len(evidence)
        for i, sig in enumerate(evidence):
            recency = 1.0 + (i / max(n - 1, 1)) * (_RECENCY_MAX_WEIGHT - 1.0)
            weights[sig.value] = weights.get(sig.value, 0.0) + recency
        total = sum(weights.values())
        if total <= 0:
            return {}
        return {v: w / total for v, w in weights.items()}

    def value_profile(self) -> ValueProfile:
        raw_counts: dict[str, int] = dict(self.prior_values)
        for sig in self.evidence():
            raw_counts[sig.value] = raw_counts.get(sig.value, 0) + 1
        weights = self.value_weights()
        if not weights:
            return ValueProfile(None, "—", 0, [], 0)
        distribution = sorted(
            ((v, round(w, 3), raw_counts.get(v, 0)) for v, w in weights.items()),
            key=lambda t: t[1],
            reverse=True,
        )
        dominant = distribution[0][0]
        return ValueProfile(
            dominant=dominant,
            label=VALUE_LABELS.get(dominant, dominant),
            dominant_pct=round(distribution[0][1] * 100),
            distribution=distribution,
            total=sum(raw_counts.values()),
        )

    # -- prediction -------------------------------------------------------- #
    def predict(self, context: Optional[dict[str, Any]] = None) -> Prediction:
        """Predict which value axis the operator will optimise for next."""
        context = context or {}
        similar = [
            s for s in self.evidence() if _context_matches(s.context, context)
        ]
        if similar:
            counts: dict[str, int] = {}
            for s in similar:
                counts[s.value] = counts.get(s.value, 0) + 1
            top = max(counts, key=counts.get)
            return Prediction(
                value=top,
                confidence=round(counts[top] / len(similar), 2),
                basis="similar_context",
                sample_size=len(similar),
            )
        weights = self.value_weights()
        if weights:
            top = max(weights, key=weights.get)
            basis = "profile" if self.sample_size == 0 else "overall_preference"
            return Prediction(
                value=top,
                confidence=round(weights[top], 2),
                basis=basis,
                sample_size=self.sample_size,
            )
        return Prediction(None, 0.0, "cold_start", 0)

    # -- adaptation (feeds the recommender / KPI scoring) ------------------ #
    def adjustment_for(
        self,
        context: Optional[dict[str, Any]] = None,
        available_values: Optional[Iterable[str]] = None,
    ) -> Optional[Adjustment]:
        """Propose a re-ranking hint, or ``None`` to leave the baseline alone.

        A *confirmed* learning that fits the context wins; otherwise a
        sufficiently strong learned preference may nudge the ranking. Ranking
        adjustment only — never a hard override of the optimiser.
        """
        context = context or {}
        allowed = set(available_values) if available_values is not None else set(VALUE_AXES)

        for learning in self.confirmed_learnings:
            if learning.target_value in allowed and _learning_applies(learning, context):
                return Adjustment(
                    target_value=learning.target_value,
                    reason="confirmed preference",
                    applied_learning=learning.statement,
                    confidence=0.9,
                )

        prediction = self.predict(context)
        if (
            prediction.value in allowed
            and prediction.basis == "similar_context"
            and prediction.sample_size >= _MIN_EVIDENCE_FOR_ADAPT
            and prediction.confidence >= _MIN_CONFIDENCE_FOR_ADAPT
        ):
            return Adjustment(
                target_value=prediction.value,
                reason=(
                    f"learned from {prediction.sample_size} similar decision(s) "
                    f"({int(prediction.confidence * 100)}%)"
                ),
                confidence=prediction.confidence,
            )
        return None

    # -- inferred preferences -> the Director dials (inverse-RL-lite) ------ #
    def suggested_director_weights(self) -> dict[str, float]:
        """Propose the Director's ``punctuality`` / ``connections`` / ``stability``
        dials from the operator's revealed preferences.

        This is the "inferred preferences → KPI / scoring" lever from
        `docs/plans/co-learning-direction.md`. Deliberately damped: the proposal
        blends from the neutral default ``(1, 1, 1)`` toward the inferred shares,
        reaching full strength only after ``_FULL_CONFIDENCE_EVIDENCE`` deliberate
        decisions — a thin profile must not swing the planner.

        Throughput folds into ``punctuality``: both express "keep trains moving".
        """
        weights = self.value_weights()
        if not weights:
            return {"punctuality": 1.0, "connections": 1.0, "stability": 1.0}

        shares = {
            "punctuality": weights.get(VALUE_PUNCTUALITY, 0.0)
            + weights.get(VALUE_THROUGHPUT, 0.0),
            "connections": weights.get(VALUE_CONNECTION, 0.0),
            "stability": weights.get(VALUE_STABILITY, 0.0),
        }
        evidence = self.sample_size + sum(self.prior_values.values())
        alpha = min(1.0, evidence / _FULL_CONFIDENCE_EVIDENCE)

        dials = {
            dial: round((1.0 - alpha) * 1.0 + alpha * (3.0 * share), 2)
            for dial, share in shares.items()
        }
        if sum(dials.values()) <= 0:  # keep the planner's contract satisfiable
            return {"punctuality": 1.0, "connections": 1.0, "stability": 1.0}
        return dials

    # -- autonomy / framing (the second half of Level B) ------------------- #
    def suggested_option_presentation(self) -> str:
        """Adjustable autonomy: how much the AI should assert itself.

        Frequent overrides → explain more, act less (``"neutral"``);
        consistently following → the AI may lead (``"recommend"``).
        Deliberately conservative: needs a few signals before it moves.
        """
        if len(self.signals) < 3:
            return "recommend"
        trust = self.trust_ratio()
        if trust < 0.4:
            return "neutral"
        return "recommend"


def _context_matches(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Coarse, rule-based context similarity over the HMI's proxy booleans."""
    keys = ("connection_critical", "low_delay", "low_ripple")
    shared = [k for k in keys if k in a and k in b]
    if not shared:
        return False
    return all(bool(a[k]) == bool(b[k]) for k in shared)


def _learning_applies(learning: ConfirmedLearning, context: dict[str, Any]) -> bool:
    """A confirmed learning fires when its conditions hold in this context."""
    for key, expected in (learning.conditions or {}).items():
        if key in context and bool(context[key]) != bool(expected):
            return False
    if learning.target_value == VALUE_CONNECTION:
        return bool(context.get("connection_critical"))
    if learning.target_value == VALUE_STABILITY:
        return not bool(context.get("low_ripple", True))
    return True


# ── Store (cross-session, file-backed) ──────────────────────────────────────
def _default_store_path() -> Optional[Path]:
    """Where the carried-over profiles live.

    ``OPERATOR_MODEL_STORE`` overrides it; an empty value switches persistence
    off entirely (tests, throwaway runs).
    """
    env = os.environ.get("OPERATOR_MODEL_STORE")
    if env is not None:
        return Path(env) if env.strip() else None
    # app/core/operator_model.py -> app -> backend
    return Path(__file__).resolve().parents[2] / "data" / "operator-profiles.json"


class OperatorModelStore:
    """Keeps one :class:`OperatorProfile` per operator, across process restarts.

    Only the **carried-over** part is written to disk: the counted prior evidence,
    the number of finished shifts and the explicitly confirmed learnings. The
    current session's raw signals are not — they belong to the session, and
    `end_session` is the moment the operator decides they should count. That
    keeps the file a record of confirmed preferences rather than a transcript.

    A demo that promises "your preferences carry over to the next shift" cannot
    hold that promise from process memory alone: restarting the backend (which
    happens on every code change) silently emptied the profile while the UI kept
    claiming a warm start.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        # ``None`` = in-memory only. Opt-in rather than opt-out, so a store built
        # in a test never touches the deployment's profile file.
        self._profiles: dict[str, OperatorProfile] = {}
        self._path = path
        self._load()

    # -- persistence ------------------------------------------------------- #
    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A corrupt file must not take the backend down; a cold start is a
            # recoverable outcome, a 500 on every request is not.
            return
        for operator_id, entry in (raw.get("operators") or {}).items():
            self._profiles[operator_id] = OperatorProfile(
                operator_id=operator_id,
                prior_values={
                    str(k): int(v)
                    for k, v in (entry.get("priorValues") or {}).items()
                    if k in VALUE_AXES
                },
                prior_sessions=int(entry.get("priorSessions") or 0),
                confirmed_learnings=[
                    ConfirmedLearning(
                        statement=str(item.get("statement", "")),
                        target_value=str(item.get("targetValue", "")),
                        conditions=dict(item.get("conditions") or {}),
                    )
                    for item in (entry.get("confirmedLearnings") or [])
                    if item.get("targetValue") in VALUE_AXES
                ],
            )

    def _save(self) -> None:
        if self._path is None:
            return
        payload = {
            "version": 1,
            "operators": {
                operator_id: {
                    "priorValues": p.prior_values,
                    "priorSessions": p.prior_sessions,
                    "confirmedLearnings": [
                        {
                            "statement": lrn.statement,
                            "targetValue": lrn.target_value,
                            "conditions": lrn.conditions,
                        }
                        for lrn in p.confirmed_learnings
                    ],
                }
                for operator_id, p in self._profiles.items()
            },
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            # Losing the carry-over is bad; failing the request the operator just
            # made is worse. The API reports the in-memory profile either way.
            return

    # -- profiles ---------------------------------------------------------- #
    def profile(self, operator_id: str) -> OperatorProfile:
        return self._profiles.setdefault(
            operator_id, OperatorProfile(operator_id=operator_id)
        )

    def add_signal(self, operator_id: str, signal: DecisionSignal) -> OperatorProfile:
        profile = self.profile(operator_id)
        profile.signals.append(signal)
        return profile

    def add_learning(
        self, operator_id: str, learning: ConfirmedLearning
    ) -> OperatorProfile:
        profile = self.profile(operator_id)
        profile.confirmed_learnings.append(learning)
        self._save()
        return profile

    def end_session(self, operator_id: str) -> OperatorProfile:
        """Fold this session's deliberate evidence into the carried-over prior."""
        profile = self.profile(operator_id)
        for sig in profile.evidence():
            profile.prior_values[sig.value] = profile.prior_values.get(sig.value, 0) + 1
        profile.signals.clear()
        profile.prior_sessions += 1
        self._save()
        return profile

    def reset(self, operator_id: Optional[str] = None) -> None:
        if operator_id is None:
            self._profiles.clear()
        else:
            self._profiles.pop(operator_id, None)
        self._save()


#: Process-wide store used by the API layer — the only one that persists.
operator_model_store = OperatorModelStore(_default_store_path())
