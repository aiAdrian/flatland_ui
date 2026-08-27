"""Learning Moments: short, event-triggered learning interactions mid-episode.

The shift review asks what happened *after* the shift. By then the situation is
cold and the operator has moved on. A Learning Moment instead interrupts shortly
after a decision that turned out to matter, asks the operator to *predict* what
the alternative would have done, and only then reveals the measured answer.

Prediction before reveal is the point. Being told "B would have been better"
teaches little; committing to a guess and being wrong is what makes the
downstream effect stick.

The pipeline, one stage per section below:

    decision → outcome evaluation → detector → counterfactual → interaction → takeaway

Two rules hold throughout:

**Numbers come from the simulator, words come from the narrator.** Every figure
in a moment is produced by forward-simulating forks of the live episode
(:func:`evaluate_branches`). The narrator (:class:`LearningMomentNarrator`) only
phrases what those numbers already say. It never invents an outcome. The API
keeps the two apart in the payload (``evidence`` vs ``narrative``) so a reader
can always tell which is which.

**The comparison is paired.** Both branches fork from the same state with
``copy.deepcopy``, so they inherit the live env's RNG and therefore see the
*same* future malfunction stream — the contract ``replan.rollout_gate`` relies
on. What differs between the branches is the decision, and nothing else. The
comparison is "from this decision point onwards", not "over the whole episode":
whatever happened before the fork is invisible to both branches alike.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# ── event types ────────────────────────────────────────────────────────────

EVENT_MISTAKE = "mistake"
EVENT_NEAR_MISS = "near_miss"
EVENT_SURPRISING_SUCCESS = "surprising_success"

EVENT_TYPES = (EVENT_MISTAKE, EVENT_NEAR_MISS, EVENT_SURPRISING_SUCCESS)

# What the operator can predict about the alternative, and which sign of the
# delay difference each answer corresponds to.
PREDICTION_BETTER = "better"
PREDICTION_SAME = "same"
PREDICTION_WORSE = "worse"

PREDICTIONS = (PREDICTION_BETTER, PREDICTION_SAME, PREDICTION_WORSE)


@dataclass(frozen=True)
class TriggerConfig:
    """Thresholds deciding when a decision is worth interrupting for.

    Deliberately blunt for the first prototype: absolute deltas on simulated
    outcomes, no learned relevance model. The defaults aim at roughly three to
    five moments per episode — ``max_per_episode`` is the hard stop, and
    ``min_steps_between`` keeps two moments from landing back to back when a
    cluster of decisions all turn out badly.
    """

    # A difference this large in total delay (steps, summed over trains) counts
    # as "clearly better/worse" rather than noise.
    delay_threshold: int = 30
    # One more train arriving is never noise.
    arrival_threshold: int = 1
    # A single train this far past its deadline is a near miss even when the
    # episode as a whole worked out.
    near_miss_max_delay: int = 60
    # Frequency guards.
    max_per_episode: int = 5
    min_steps_between: int = 20
    # Each extra alternative costs a full forward simulation, so cap it.
    max_alternatives: int = 2


# ── outcome evaluation ─────────────────────────────────────────────────────


@dataclass
class BranchOutcome:
    """What a simulated branch produced. Every field comes from the simulator."""

    total_delay: int
    max_delay: int
    arrived: int
    trains: int
    all_arrived: bool
    steps: int
    connections_total: int
    connections_kept: int
    kept_ratio: float
    # The planner's own predicted score for this branch, when it planned one.
    # Kept beside the simulated result on purpose: their disagreement is what
    # makes a surprising success detectable.
    predicted_weighted: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Alternative:
    """A road not taken: an option the operator could have chosen instead."""

    id: str
    label: str
    weights: Dict[str, float]
    outcome: Optional[BranchOutcome] = None
    unavailable_reason: Optional[str] = None


def evaluate_branches(
    env,
    chosen_weights: Dict[str, float],
    alternatives: Sequence[Alternative],
    config: TriggerConfig = TriggerConfig(),
) -> tuple[Optional[BranchOutcome], List[Alternative]]:
    """Simulate the committed plan and each alternative to the episode's end.

    The "actual" branch continues the plan that is driving — the operator's
    decision is already committed by the time a moment is evaluated, so
    continuing it *is* the actual outcome. Each alternative re-plans the
    remainder under its own dials and then runs forward.

    Returns ``(actual, alternatives)`` with outcomes filled in, or
    ``(None, alternatives)`` when the session cannot be simulated yet (no
    committed plan, or no models installed). Alternatives that fail to plan
    carry an ``unavailable_reason`` instead of an outcome; a failure to plan one
    option must not cost the whole moment.

    Cost note: one forward simulation per branch to the episode's end, measured
    around 3-4 s each on the demo environment. With the default of two
    alternatives that is three simulations per moment.
    """
    import copy

    from app.policies.goal_based_policies.connections import (
        evaluate_connections,
        observed_times,
        planned_connections,
        station_watch_cells,
    )
    from app.policies.goal_based_policies.replan import (
        apply_residual_plan,
        residual_plan,
        simulate_forward,
    )
    from app.policies.goal_based_policies.schedule import SchedulePlayer
    from app.policies.goal_based_policies.stations import resolve_stations
    from app.policies.goal_directed_policy import (
        loaded_models,
        plan_player,
        plan_schedules,
    )

    player = plan_player(env)
    schedules = plan_schedules(env)
    models = loaded_models()
    if player is None or schedules is None or models is None:
        return None, list(alternatives)

    graph = player.graph
    snapshot = player.snapshot()
    stations = resolve_stations(env)
    connections = planned_connections(env, stations)
    watch = station_watch_cells(stations)

    def outcome_from(raw: Dict[str, Any]) -> BranchOutcome:
        report = evaluate_connections(
            connections, observed_times(stations, raw["occupancy"])
        )
        return BranchOutcome(
            total_delay=int(raw["total_delay"]),
            max_delay=int(raw["max_delay"]),
            arrived=int(raw["arrived"]),
            trains=int(raw["trains"]),
            all_arrived=bool(raw["all_arrived"]),
            steps=int(raw["steps"]),
            connections_total=int(report.total),
            connections_kept=int(report.kept),
            kept_ratio=float(report.kept_ratio),
        )

    def fork():
        clone = copy.deepcopy(env)
        clone_player = SchedulePlayer(graph, clone)
        clone_player.restore(snapshot)
        return clone, clone_player

    # Actual: the committed plan, continued.
    fork_a, player_a = fork()
    actual = outcome_from(simulate_forward(fork_a, player_a, watch_cells=watch))

    from app.policies.goal_based_policies.ensemble import DirectorWeights

    evaluated: List[Alternative] = []
    for alternative in list(alternatives)[: config.max_alternatives]:
        w = alternative.weights
        try:
            weights = DirectorWeights(
                float(w["punctuality"]), float(w["connections"]),
                float(w["stability"]),
            )
        except (KeyError, ValueError) as exc:
            alternative.unavailable_reason = f"invalid weights: {exc}"
            evaluated.append(alternative)
            continue
        try:
            fork_b, player_b = fork()
            plan = residual_plan(
                fork_b, graph, weights, *models,
                player=player_b, schedules=schedules,
                reason=f"learning-moment-{alternative.id}",
            )
            apply_residual_plan(player_b, plan)
            result = outcome_from(
                simulate_forward(fork_b, player_b, watch_cells=watch))
            result.predicted_weighted = float(plan.score.weighted)
            alternative.outcome = result
        except Exception as exc:  # planning an option must not kill the moment
            alternative.unavailable_reason = f"could not plan: {exc}"
        evaluated.append(alternative)

    # Keep alternatives the caller passed beyond the cap, marked as skipped, so
    # the payload stays honest about what was and was not compared.
    for skipped in list(alternatives)[config.max_alternatives:]:
        skipped.unavailable_reason = "not simulated (alternative budget reached)"
        evaluated.append(skipped)

    return actual, evaluated


# ── detector ───────────────────────────────────────────────────────────────


@dataclass
class Detection:
    """The detector's verdict on one decision."""

    triggered: bool
    event_type: Optional[str] = None
    reference_id: Optional[str] = None  # the alternative the moment is about
    reasons: List[str] = field(default_factory=list)
    # Signed differences, from the operator's point of view: positive = the
    # alternative would have been better.
    delay_regret: int = 0
    arrival_regret: int = 0
    connection_regret: int = 0
    skip_reason: Optional[str] = None


def _best_alternative(
    actual: BranchOutcome, alternatives: Sequence[Alternative]
) -> Optional[Alternative]:
    """The alternative that would have hurt the most to miss.

    Ranked the way ``replan.rollout_gate`` ranks branches — arrivals first, then
    delay — so "better" means the same thing here as it does when the planner
    itself decides whether to switch plans.
    """
    scored = [a for a in alternatives if a.outcome is not None]
    if not scored:
        return None
    return max(
        scored,
        key=lambda a: (a.outcome.arrived, -a.outcome.total_delay),
    )


def detect(
    actual: Optional[BranchOutcome],
    alternatives: Sequence[Alternative],
    config: TriggerConfig = TriggerConfig(),
) -> Detection:
    """Classify a decision as mistake, near miss, surprising success — or noise.

    Only one verdict per decision, checked in order of how much it is worth
    interrupting for: a clearly better alternative (mistake) outranks an
    unexpectedly good result (surprising success), which outranks a result that
    worked but nearly did not (near miss).
    """
    if actual is None:
        return Detection(False, skip_reason="session cannot be simulated yet")
    best = _best_alternative(actual, alternatives)
    if best is None or best.outcome is None:
        return Detection(False, skip_reason="no alternative could be simulated")

    alt = best.outcome
    # Positive = the alternative would have been better.
    delay_regret = actual.total_delay - alt.total_delay
    arrival_regret = alt.arrived - actual.arrived
    connection_regret = alt.connections_kept - actual.connections_kept

    reasons: List[str] = []

    # 1) Mistake — a feasible alternative was clearly better.
    if arrival_regret >= config.arrival_threshold:
        reasons.append(
            f"{best.label} hätte {arrival_regret} Zug/Züge mehr ans Ziel gebracht"
        )
    if delay_regret >= config.delay_threshold:
        reasons.append(
            f"{best.label} hätte {delay_regret} Schritte Verspätung gespart"
        )
    if reasons:
        return Detection(
            True, EVENT_MISTAKE, best.id, reasons,
            delay_regret, arrival_regret, connection_regret,
        )

    # 2) Surprising success — the choice beat an option the planner rated
    #    higher. Model-versus-ground-truth, not merely "it went well".
    chosen_beat_alternative = (
        -arrival_regret >= config.arrival_threshold
        or -delay_regret >= config.delay_threshold
    )
    model_favoured_alternative = (
        actual.predicted_weighted is not None
        and alt.predicted_weighted is not None
        and alt.predicted_weighted > actual.predicted_weighted
    )
    if chosen_beat_alternative:
        if model_favoured_alternative:
            reasons.append(
                f"der Planer bewertete {best.label} höher, deine Wahl lag "
                f"trotzdem vorn"
            )
        else:
            reasons.append(f"deine Wahl lag klar vor {best.label}")
        return Detection(
            True, EVENT_SURPRISING_SUCCESS, best.id, reasons,
            delay_regret, arrival_regret, connection_regret,
        )

    # 3) Near miss — it worked, but one train came far too close to the edge,
    #    and an alternative existed that did not.
    if (
        actual.max_delay >= config.near_miss_max_delay
        and alt.max_delay < actual.max_delay
    ):
        return Detection(
            True, EVENT_NEAR_MISS, best.id,
            [
                f"schlimmster einzelner Zug lief {actual.max_delay} Schritte zu "
                f"spät; {best.label} hielt das bei {alt.max_delay}"
            ],
            delay_regret, arrival_regret, connection_regret,
        )

    return Detection(
        False,
        skip_reason=(
            "Ergebnisse zu ähnlich, um dafür zu unterbrechen "
            f"(Verspätung {delay_regret:+d}, Ankünfte {arrival_regret:+d})"
        ),
    )


# ── the moment itself ──────────────────────────────────────────────────────


@dataclass
class LearningMoment:
    """One stored Learning Moment, complete enough for the final reflection.

    Carries the full chain: what the situation was, what was chosen, what
    actually followed, which alternative it is measured against, what the
    operator predicted, and the narrator's reading of it.
    """

    id: str
    session_id: str
    step: int
    event_type: str
    # State / situation at the decision point.
    situation: Dict[str, Any]
    # Selected action and its measured outcome.
    chosen_id: str
    chosen_label: str
    chosen_weights: Dict[str, float]
    actual_outcome: Dict[str, Any]
    # The counterfactual.
    alternative_id: str
    alternative_label: str
    alternative_weights: Dict[str, float]
    counterfactual_outcome: Dict[str, Any]
    # Detector evidence.
    detection_reasons: List[str]
    delay_regret: int
    arrival_regret: int
    connection_regret: int
    # Interaction.
    question: str
    options: List[Dict[str, str]]
    user_prediction: Optional[str] = None
    prediction_correct: Optional[bool] = None
    # Narrator output, only filled once the operator has answered.
    explanation: Optional[str] = None
    takeaway: Optional[str] = None
    answered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── narrator: the interpretation seam ──────────────────────────────────────


class LearningMomentNarrator:
    """Turns measured differences into a question, an explanation, a takeaway.

    This is the seam a language model belongs behind. It receives the moment —
    which already holds every number — and returns only prose. Nothing it
    returns may introduce a quantity that is not already in the moment, because
    the API presents its output as interpretation next to the simulator's
    evidence, and a reader has to be able to trust that split.

    :class:`TemplateNarrator` is the offline default so the prototype runs with
    no model and no network.
    """

    def question(self, moment: LearningMoment) -> str:
        raise NotImplementedError

    def explain(self, moment: LearningMoment) -> str:
        raise NotImplementedError

    def takeaway(self, moment: LearningMoment) -> str:
        raise NotImplementedError


def _truth(moment: LearningMoment) -> str:
    """Which prediction the numbers actually support."""
    if moment.arrival_regret > 0 or moment.delay_regret > 0:
        return PREDICTION_BETTER
    if moment.arrival_regret < 0 or moment.delay_regret < 0:
        return PREDICTION_WORSE
    return PREDICTION_SAME


class TemplateNarrator(LearningMomentNarrator):
    """Rule and template based narrator. Deterministic, no model, no network."""

    _QUESTIONS = {
        EVENT_MISTAKE: (
            "Du hast {chosen} gewählt. Was glaubst du, wäre mit {alternative} "
            "passiert?"
        ),
        EVENT_NEAR_MISS: (
            "{chosen} ist aufgegangen, aber ein Zug kam dicht an die Grenze. Was "
            "glaubst du, hätte {alternative} bewirkt?"
        ),
        EVENT_SURPRISING_SUCCESS: (
            "Du hast {chosen} gewählt. Was glaubst du, wäre mit {alternative} "
            "passiert?"
        ),
    }

    def question(self, moment: LearningMoment) -> str:
        template = self._QUESTIONS.get(
            moment.event_type, self._QUESTIONS[EVENT_MISTAKE])
        return template.format(
            chosen=moment.chosen_label, alternative=moment.alternative_label
        )

    def explain(self, moment: LearningMoment) -> str:
        actual = moment.actual_outcome
        alt = moment.counterfactual_outcome
        parts: List[str] = []

        if moment.arrival_regret:
            direction = "mehr" if moment.arrival_regret > 0 else "weniger"
            parts.append(
                f"{moment.alternative_label} bringt "
                f"{abs(moment.arrival_regret)} Zug/Züge {direction} ans Ziel "
                f"({alt['arrived']} von {alt['trains']} gegen "
                f"{actual['arrived']} von {actual['trains']})"
            )
        if moment.delay_regret:
            verb = "spart" if moment.delay_regret > 0 else "kostet"
            parts.append(
                f"es {verb} {abs(moment.delay_regret)} Schritte "
                f"Gesamtverspätung ({alt['total_delay']} gegen "
                f"{actual['total_delay']})"
            )
        if moment.connection_regret:
            verb = "hält" if moment.connection_regret > 0 else "verliert"
            parts.append(
                f"es {verb} {abs(moment.connection_regret)} Anschluss/Anschlüsse "
                f"mehr"
            )
        if moment.event_type == EVENT_NEAR_MISS:
            parts.append(
                f"der schlimmste einzelne Zug lief bei deiner Wahl "
                f"{actual['max_delay']} Schritte zu spät, bei "
                f"{moment.alternative_label} {alt['max_delay']}"
            )

        if not parts:
            return (
                "Beide Optionen landen an derselben Stelle — diese Entscheidung "
                "war hier nicht die entscheidende."
            )
        body = "; ".join(parts) + "."
        return body[0].upper() + body[1:]

    def takeaway(self, moment: LearningMoment) -> str:
        axis = _dominant_axis(moment.alternative_weights)
        if moment.event_type == EVENT_MISTAKE:
            if moment.arrival_regret > 0:
                return (
                    "Wenn Züge drohen gar nicht anzukommen, wiegen Ankünfte "
                    "schwerer als die Verspätung einzelner Züge."
                )
            if moment.connection_regret > 0:
                return (
                    "Ein gehaltener Anschluss kann mehr wert sein als die "
                    "Minuten, die er kostet — prüfe, was daran hängt."
                )
            return (
                f"In Lagen wie dieser zahlt sich {axis} mehr aus als der Fokus, "
                f"den du gewählt hast."
            )
        if moment.event_type == EVENT_NEAR_MISS:
            return (
                "Ein Plan, der in der Summe aufgeht, kann trotzdem einen Zug am "
                "Rand stehen lassen — schau auf den schlechtesten Fall, nicht "
                "nur auf die Summe."
            )
        return (
            "Die Rangfolge des Planers ist nicht das Ergebnis. Wenn dein Blick "
            "auf die Lage der Bewertung widerspricht, lohnt es sich, ihm zu "
            "trauen."
        )


_AXIS_PHRASES = {
    "punctuality": "auf Pünktlichkeit zu drücken",
    "connections": "Anschlüsse zu schützen",
    "stability": "das Netz stabil zu halten",
}


def _dominant_axis(weights: Dict[str, float]) -> str:
    if not weights:
        return "ein anderer Fokus"
    axis = max(weights, key=lambda k: float(weights.get(k) or 0))
    return _AXIS_PHRASES.get(axis, axis)


def prediction_options() -> List[Dict[str, str]]:
    """The three answers offered, in the order they are shown."""
    return [
        {"id": PREDICTION_BETTER, "label": "Besseres Ergebnis"},
        {"id": PREDICTION_SAME, "label": "Etwa gleich"},
        {"id": PREDICTION_WORSE, "label": "Schlechteres Ergebnis"},
    ]


# ── store ──────────────────────────────────────────────────────────────────


class LearningMomentStore:
    """Session-scoped, in-memory, like the other managers in ``app.core``.

    Holds the moments of the running episode so the final reflection can read
    them back and look across them. Also owns the frequency guards, because
    "should this decision interrupt the operator" depends on what already
    interrupted them.
    """

    def __init__(self, config: TriggerConfig = TriggerConfig()) -> None:
        self._moments: Dict[str, List[LearningMoment]] = {}
        self.config = config

    def all(self, session_id: str) -> List[LearningMoment]:
        return list(self._moments.get(session_id, []))

    def get(self, session_id: str, moment_id: str) -> Optional[LearningMoment]:
        for moment in self._moments.get(session_id, []):
            if moment.id == moment_id:
                return moment
        return None

    def budget_check(self, session_id: str, step: int) -> Optional[str]:
        """Why this step may not trigger a moment, or None when it may."""
        existing = self._moments.get(session_id, [])
        if len(existing) >= self.config.max_per_episode:
            return (
                f"episode budget reached "
                f"({self.config.max_per_episode} learning moments)"
            )
        if existing:
            last = max(m.step for m in existing)
            waited = step - last
            if waited < self.config.min_steps_between:
                return (
                    f"too soon after the last moment "
                    f"({waited} of {self.config.min_steps_between} steps)"
                )
        return None

    def add(self, moment: LearningMoment) -> LearningMoment:
        self._moments.setdefault(moment.session_id, []).append(moment)
        return moment

    def record_answer(
        self,
        session_id: str,
        moment_id: str,
        prediction: str,
        narrator: LearningMomentNarrator,
    ) -> Optional[LearningMoment]:
        """Store the operator's guess and fill in the narrator's reading.

        The explanation and takeaway are produced here rather than up front: the
        operator has to commit to a prediction before the answer exists to be
        read, and generating the text earlier would risk leaking it into the
        payload that carries the question.
        """
        moment = self.get(session_id, moment_id)
        if moment is None:
            return None
        moment.user_prediction = prediction
        moment.prediction_correct = prediction == _truth(moment)
        moment.explanation = narrator.explain(moment)
        moment.takeaway = narrator.takeaway(moment)
        moment.answered = True
        return moment

    def clear_session(self, session_id: str) -> None:
        self._moments.pop(session_id, None)


learning_moment_store = LearningMomentStore()


# ── cross-moment patterns, for the final reflection ────────────────────────


def summarise(moments: Sequence[LearningMoment]) -> Dict[str, Any]:
    """What the moments of one shift say together.

    The individual moments are episodes; the reflection needs the pattern. Kept
    on the backend beside the moments so both the API and any later consumer
    read the same aggregation.
    """
    total = len(moments)
    answered = [m for m in moments if m.answered]
    by_type: Dict[str, int] = {}
    for moment in moments:
        by_type[moment.event_type] = by_type.get(moment.event_type, 0) + 1

    surprised = [
        m for m in answered
        if m.prediction_correct is False
    ]
    repeated_axis: Dict[str, int] = {}
    for moment in moments:
        if moment.event_type != EVENT_MISTAKE:
            continue
        axis = max(
            moment.alternative_weights,
            key=lambda k: float(moment.alternative_weights.get(k) or 0),
        ) if moment.alternative_weights else None
        if axis:
            repeated_axis[axis] = repeated_axis.get(axis, 0) + 1

    pattern: Optional[str] = None
    if repeated_axis:
        axis, count = max(repeated_axis.items(), key=lambda kv: kv[1])
        if count >= 2:
            pattern = (
                f"{count} deiner Momente zeigten in dieselbe Richtung: "
                f"{_AXIS_PHRASES.get(axis, axis)} hätte sich ausgezahlt."
            )
    if pattern is None and len(surprised) >= 2:
        pattern = (
            f"In {len(surprised)} von {len(answered)} Momenten lag die "
            f"Alternative anders als du geschätzt hast — die Fernwirkung läuft "
            f"häufiger gegen deine Intuition als mit ihr."
        )

    return {
        "total": total,
        "answered": len(answered),
        "mispredicted": len(surprised),
        "byType": by_type,
        "takeaways": [m.takeaway for m in answered if m.takeaway],
        "pattern": pattern,
    }


def new_moment_id() -> str:
    return f"lm_{uuid.uuid4().hex[:10]}"
