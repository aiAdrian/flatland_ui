"""Controller for Live Director Mode.

Wraps a ``DirectorSession`` with a running ``Shift`` and accumulating KPIs. It is
Streamlit-free and clock-agnostic (elapsed seconds are passed in), so the whole
live loop can be driven and unit-tested headlessly.

The UI layer only:
- feeds elapsed real seconds via ``tick``,
- calls ``decide(...)`` when the operator acts, or ``defer()`` on timeout,
- reads ``current`` / ``kpis`` / ``last_outcome`` to render.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import event_logger as ev
from director_mode import DirectorSession
from scenario_engine import select_observed_outcome
from simulation import STATUS_RUNNING, Shift, build_shift
from strategies import CONFIRMATION_DEFERRED, strategy_name
from user_model import AdaptiveRecommendation, Prediction, UserModel


@dataclass
class PendingDecision:
    step: int
    decision_point: dict[str, Any]
    recommended: str
    adaptive: AdaptiveRecommendation
    prediction: Prediction
    carry_forward: dict[str, Any] | None = None  # knock-on from an earlier decision


@dataclass
class LiveDirector:
    session: DirectorSession
    speed: float = 3.0
    prior_preferences: dict[str, int] = field(default_factory=dict)
    confirmed_learnings: list[dict[str, Any]] = field(default_factory=list)
    shift: Shift = field(init=False)
    current: PendingDecision | None = field(default=None, init=False)
    last_decision: dict[str, Any] | None = field(default=None, init=False)
    pending: list[dict[str, Any]] = field(default_factory=list, init=False)
    resolved_queue: list[dict[str, Any]] = field(default_factory=list, init=False)
    feed: list[dict[str, Any]] = field(default_factory=list, init=False)
    applied_learnings: list[dict[str, Any]] = field(default_factory=list, init=False)
    pending_consequence: dict[str, Any] | None = field(default=None, init=False)
    knock_on_count: int = field(default=0, init=False)
    kpis: dict[str, Any] = field(init=False)

    def _user_model(self) -> UserModel:
        return UserModel(
            self.session.episodes(),
            prior_preferences=self.prior_preferences,
            confirmed_learnings=self.confirmed_learnings,
        )

    def __post_init__(self) -> None:
        self.shift = build_shift(self.session.scenario, speed=self.speed)
        self.kpis = {
            "added_delay_min": 0,
            "connections_kept": 0,
            "connections_lost": 0,
            "follow_up_conflicts": 0,
            "network_state": "stable",
            "decisions": 0,
            "deferrals": 0,
            "open_problems": 0,
            "passengers_affected": 0,
        }

    @staticmethod
    def _passengers(situation: dict[str, Any]) -> int:
        """How many passengers ride on the connection at stake here."""
        p = situation.get("passengers")
        if isinstance(p, (int, float)):
            return int(p)
        return 90 if situation.get("critical_connection") else 0

    # -- clock ------------------------------------------------------------- #
    def tick(self, elapsed_s: float) -> str | None:
        token = self.shift.tick(elapsed_s)
        self._fire_due_resolutions()
        if token == "await":
            self._open_decision(self.shift.pending_index)
        elif token == "auto":
            self._auto_handle(self.shift.pending_index)
        elif token == "ended":
            self.finalize()
        return token

    def skip_to_next_moment(self, max_events: int = 100) -> str | None:
        """Fast-forward through running time until the next intervention or end
        (for presentations — removes dead air between director moments)."""
        token = None
        for _ in range(max_events):
            token = self.tick(10_000)  # large jump; the clock snaps to each event
            if self.status != STATUS_RUNNING:
                break
        return token

    def _fire_due_resolutions(self) -> None:
        """Materialise the outcome of past decisions once enough time passed."""
        due = [p for p in self.pending if p["resolve_at"] <= self.shift.clock_min]
        for p in due:
            self._apply_resolution(p)
            self.pending.remove(p)

    def finalize(self) -> None:
        """Flush any still-pending resolutions (e.g. at shift end)."""
        for p in list(self.pending):
            self._apply_resolution(p)
        self.pending = []

    @staticmethod
    def _is_bad_outcome(observed: dict[str, Any]) -> bool:
        return (
            int(observed.get("follow_up_conflicts", 0) or 0) > 0
            or str(observed.get("connection", "")).lower() == "broken"
            or str(observed.get("network_state", "")).lower() in ("strained", "unstable")
        )

    @staticmethod
    def _consequence_cause(observed: dict[str, Any], deferred: bool) -> tuple[str, str]:
        """Return (cause, mechanism) describing concretely what went wrong."""
        conn = str(observed.get("connection", "")).lower()
        if conn == "broken":
            cause = "the connection was broken"
            mechanism = "stranded passengers now compete for the next paths"
        elif int(observed.get("follow_up_conflicts", 0) or 0) > 0:
            cause = "a follow-up conflict was left unresolved"
            mechanism = "it has cascaded into a new conflict here"
        elif str(observed.get("network_state", "")).lower() in ("strained", "unstable"):
            cause = "the network was pushed into an unstable state"
            mechanism = "congestion has spread down the corridor"
        else:
            cause = "delay was absorbed instead of recovered"
            mechanism = "that delay has propagated to this junction"
        if deferred:
            cause = "you let the AI decide and " + cause
        return cause, mechanism

    _STABILISING_STRATEGIES = {"stabilize_network", "avoid_follow_up_conflicts"}

    def _apply_resolution(self, p: dict[str, Any]) -> None:
        observed = p["observed"]
        self._update_kpis(observed, deferred=p["deferred"])
        # System load couples the two mechanics: a bad outcome opens a new problem
        # (the future gets uncertain); it only clears when the operator makes a
        # *deliberate stabilising* decision that relaxes the future.
        selected = (
            p.get("episode", {}).get("user_decision", {}).get("selected_strategy")
        )
        stabilising = selected in self._STABILISING_STRATEGIES
        if stabilising and self.kpis["open_problems"] > 0:
            # a deliberate decision that relaxes the future closes a problem
            self.kpis["open_problems"] -= 1
        elif p["deferred"] or self._is_bad_outcome(observed):
            # left to the AI (unattended) or a bad outcome -> the problem lingers
            self.kpis["open_problems"] += 1
        # broken connection strands the passengers riding on it (the hidden cost
        # of a punctuality-first bias)
        if str(observed.get("connection", "")).lower() == "broken":
            self.kpis["passengers_affected"] += int(p.get("passengers", 0) or 0)
        # a carry-forward moment bites harder: the propagated delay + a new conflict
        if p.get("carry_penalty"):
            self.kpis["follow_up_conflicts"] += 1
            self.kpis["added_delay_min"] += int(p.get("carried_delay", 0) or 0)
        if p.get("kind") == "human":
            self.kpis["decisions"] += 1
            if p["deferred"]:
                self.kpis["deferrals"] += 1
            self.resolved_queue.append(p)
        # a bad outcome seeds a concrete knock-on effect for the next moment
        if self._is_bad_outcome(observed):
            cause, mechanism = self._consequence_cause(observed, p["deferred"])
            carried_delay = max(1, int(observed.get("additional_delay_min", 0) or 0))
            self.pending_consequence = {
                "source_time": p.get("time_label", ""),
                "cause": cause,
                "mechanism": mechanism,
                "carried_delay": carried_delay,
            }
            self._push_feed(
                p.get("time_label", ""),
                f"⚠ Knock-on building: +{carried_delay} min delay propagating — {mechanism}",
                "", "AI",
            )

    def _push_feed(self, time_label: str, text: str, strategy: str, by: str) -> None:
        self.feed.insert(0, {"time_label": time_label, "text": text,
                             "strategy": strategy_name(strategy), "by": by})
        del self.feed[12:]

    def _auto_handle(self, index: int) -> None:
        """The AI resolves a routine (info) event autonomously; no human needed."""
        dp = self.session.decision_point(index)
        model = self._user_model()
        recommended = model.adaptive_recommendation(dp, index).recommended
        observed = select_observed_outcome(dp, recommended, self.session.seed, index)
        situation = dp.get("situation", {})
        buf = situation.get("connection_buffer_min")
        resolve_delay = max(4, min(12, int(buf) if isinstance(buf, (int, float)) else 6))
        self.pending.append(
            {
                "resolve_at": self.shift.clock_min + resolve_delay,
                "observed": observed,
                "deferred": False,
                "kind": "auto",
                "time_label": situation.get("time_label", ""),
                "passengers": self._passengers(situation),
            }
        )
        event = dp.get("event", {})
        self._push_feed(situation.get("time_label", ""),
                        event.get("text", "Routine event"), recommended, "AI")
        self.session.logger.log(
            ev.EVENT_AI_AUTONOMOUS, ev.ACTOR_DIRECTOR_MODE,
            {"strategy": recommended, "event": event.get("text", "")},
            simulation_step=index,
        )

    def consume_resolution(self) -> dict[str, Any] | None:
        return self.resolved_queue.pop(0) if self.resolved_queue else None

    @property
    def status(self) -> str:
        return self.shift.status

    @property
    def clock_min(self) -> float:
        return self.shift.clock_min

    @property
    def remaining_decide_s(self) -> float:
        return self.shift.remaining_decide_s

    # -- decision lifecycle ------------------------------------------------ #
    def _open_decision(self, step: int) -> None:
        dp = self.session.decision_point(step)
        model = self._user_model()
        adaptive = model.adaptive_recommendation(dp, step)
        prediction = model.predict(dp, step)
        # a bad earlier outcome carries forward and aggravates this moment
        carry = self.pending_consequence
        self.pending_consequence = None
        if carry:
            self.knock_on_count += 1
            carry = {**carry, "chain_index": self.knock_on_count}
        self.current = PendingDecision(
            step=step,
            decision_point=dp,
            recommended=adaptive.recommended,
            adaptive=adaptive,
            prediction=prediction,
            carry_forward=carry,
        )
        self.session.log_recommendation(step, dp)
        self.session.log_prediction(step, prediction.strategy,
                                    prediction.confidence, prediction.basis)

    def decide(
        self,
        selected_strategy: str,
        confirmation_mode: str,
        rationale_mode: str = "none",
        reason_tags: list[str] | None = None,
        rationale_text: str | None = None,
        interaction: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert self.current is not None, "no pending decision"
        cur = self.current
        prediction = cur.prediction
        prediction_correct = (
            prediction.strategy is not None
            and prediction.strategy == selected_strategy
        )
        interaction = dict(interaction or {})
        interaction.update(
            {
                "predicted_strategy": prediction.strategy,
                "prediction_confidence": prediction.confidence,
                "prediction_basis": prediction.basis,
                "prediction_correct": prediction_correct,
            }
        )
        if cur.carry_forward:
            interaction["carry_forward"] = cur.carry_forward.get("reason")
        episode = self.session.commit_decision(
            step=cur.step,
            decision_point=cur.decision_point,
            selected_strategy=selected_strategy,
            confirmation_mode=confirmation_mode,
            rationale_mode=rationale_mode,
            rationale_text=rationale_text,
            reason_tags=reason_tags,
            interaction=interaction,
            recommended_strategy=cur.recommended,
            learning_adjusted=(cur.adaptive.source in ("learned", "learned_confirmed")
                               and cur.adaptive.adjusted),
            recommendation_source=cur.adaptive.source,
            applied_learning=cur.adaptive.applied_learning,
        )
        # record cross-session learning influence for the evaluation
        if cur.adaptive.source == "learned_confirmed":
            self.applied_learnings.append(
                {
                    "time_label": cur.decision_point.get("situation", {}).get(
                        "time_label", ""),
                    "statement": cur.adaptive.applied_learning,
                    "recommended": cur.recommended,
                    "baseline": cur.adaptive.baseline,
                    "selected": selected_strategy,
                    "followed": selected_strategy == cur.recommended,
                }
            )
        # The operational effect unfolds *later*, not at the moment of deciding.
        situation = cur.decision_point.get("situation", {})
        buf = situation.get("connection_buffer_min")
        resolve_delay = max(4, min(12, int(buf) if isinstance(buf, (int, float)) else 6))
        deferred = confirmation_mode == CONFIRMATION_DEFERRED
        self.pending.append(
            {
                "resolve_at": self.shift.clock_min + resolve_delay,
                "episode": episode,
                "observed": episode.get("outcome", {}).get("observed", {}),
                "deferred": deferred,
                "kind": "human",
                "time_label": situation.get("time_label", ""),
                # an aggravated (carry-forward) moment bites harder downstream
                "carry_penalty": bool(cur.carry_forward),
                "carried_delay": (cur.carry_forward or {}).get("carried_delay", 0),
                "passengers": self._passengers(situation),
            }
        )
        self._push_feed(
            situation.get("time_label", ""),
            cur.decision_point.get("event", {}).get("text", "Decision"),
            selected_strategy,
            "AI (deferred)" if deferred else "You",
        )
        # The prediction reveal (about the human choice) is known immediately.
        self.last_decision = {
            "predicted_strategy": prediction.strategy,
            "selected_strategy": selected_strategy,
            "prediction_correct": prediction_correct,
            "deferred": confirmation_mode == CONFIRMATION_DEFERRED,
            "time_label": situation.get("time_label", ""),
        }
        self.current = None
        self.shift.resolve()
        return episode

    def defer(self) -> dict[str, Any]:
        """Deadline passed: the AI executes its recommendation by default."""
        assert self.current is not None
        return self.decide(
            selected_strategy=self.current.recommended,
            confirmation_mode=CONFIRMATION_DEFERRED,
            rationale_mode="none",
            interaction={"deferred": True},
        )

    # -- kpis -------------------------------------------------------------- #
    def _update_kpis(self, outcome: dict[str, Any], deferred: bool) -> None:
        self.kpis["added_delay_min"] += int(outcome.get("additional_delay_min", 0) or 0)
        connection = str(outcome.get("connection", "")).lower()
        if connection in ("protected", "kept"):
            self.kpis["connections_kept"] += 1
        elif connection == "broken":
            self.kpis["connections_lost"] += 1
        self.kpis["follow_up_conflicts"] += int(outcome.get("follow_up_conflicts", 0) or 0)
        if outcome.get("network_state"):
            self.kpis["network_state"] = outcome["network_state"]
