"""Learning Moment endpoints: detect, ask, reveal, and hand to the reflection.

Three calls make up one interaction:

1. ``POST /session/{id}/learning-moment/evaluate`` — right after a decision.
   Simulates the alternatives, classifies the event and, if it clears the bar,
   returns a *question* and nothing else about the answer.
2. ``POST /session/{id}/learning-moment/{moment_id}/answer`` — the operator's
   prediction goes in, the measured result and the narrator's reading come back.
3. ``GET /session/{id}/learning-moments`` — everything stored this episode, plus
   the cross-moment summary the shift review needs.

The split in step 1/2 is deliberate: the reveal is not in the payload that
carries the question, so a client cannot show the answer early even by accident.

See ``app.core.learning_moments`` for the pipeline and for the rule that keeps
simulator numbers and narrator prose apart.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.learning_moments import (
    Alternative,
    LearningMoment,
    PREDICTIONS,
    TemplateNarrator,
    detect,
    evaluate_branches,
    learning_moment_store,
    new_moment_id,
    prediction_options,
    summarise,
)
from app.core.session_manager import session_manager

router = APIRouter()

# The offline default. Swap here for a model-backed narrator; nothing else in
# this module needs to change, because the narrator only ever produces prose.
narrator = TemplateNarrator()


class OptionIn(BaseModel):
    """One strategy focus, as the A/B/C tiles express it."""

    id: str
    label: str
    weights: Dict[str, float]


class EvaluateIn(BaseModel):
    """The decision just taken, and what it was chosen over.

    ``alternatives`` may be omitted: the other Director strategy presets are
    then used, which is what the A/B/C tiles offer anyway.
    """

    chosen: OptionIn
    alternatives: Optional[List[OptionIn]] = None
    # Client-side decision id, so a moment can be tied back to the decision log.
    decision_seq: Optional[int] = Field(default=None, alias="decisionSeq")

    model_config = {"populate_by_name": True}


class AnswerIn(BaseModel):
    prediction: str


def _situation(env, weights: Dict[str, float]) -> Dict[str, Any]:
    """The state the decision was taken in, as far as it is readable cheaply."""
    from flatland.envs.step_utils.states import TrainState

    step = int(getattr(env, "_elapsed_steps", 0) or 0)
    on_map = 0
    done = 0
    malfunctioning = 0
    overdue = 0
    for agent in env.agents:
        state = getattr(agent, "state", None)
        if state == TrainState.DONE:
            done += 1
        elif getattr(agent, "position", None) is not None:
            on_map += 1
        if int(getattr(agent, "malfunction_handler", None).malfunction_down_counter
               if getattr(agent, "malfunction_handler", None) else 0) > 0:
            malfunctioning += 1
        latest = getattr(agent, "latest_arrival", None)
        if latest is not None and step > int(latest) and state != TrainState.DONE:
            overdue += 1
    return {
        "step": step,
        "trains": len(env.agents),
        "onMap": on_map,
        "arrived": done,
        "malfunctioning": malfunctioning,
        "overdue": overdue,
        "weights": dict(weights),
    }


def _default_alternatives(chosen_id: str) -> List[OptionIn]:
    """The other strategy focuses — the options the operator actually saw."""
    from app.api.sessions import DIRECTOR_STRATEGY_PRESETS

    out: List[OptionIn] = []
    for preset in DIRECTOR_STRATEGY_PRESETS:
        if str(preset["id"]) == chosen_id:
            continue
        out.append(
            OptionIn(
                id=str(preset["id"]),
                label=f"Focus {preset['ident']} ({preset['focus']})",
                weights={k: float(v) for k, v in dict(preset["weights"]).items()},
            )
        )
    return out


def _moment_payload(moment: LearningMoment, *, reveal: bool) -> Dict[str, Any]:
    """One moment as the client sees it.

    ``evidence`` is simulator output, ``narrative`` is the narrator's reading.
    They stay in separate objects so the boundary survives into the UI. Before
    the operator has predicted, neither the counterfactual numbers nor the
    narrative are included at all.
    """
    payload: Dict[str, Any] = {
        "id": moment.id,
        "step": moment.step,
        "eventType": moment.event_type,
        "situation": moment.situation,
        "chosen": {
            "id": moment.chosen_id,
            "label": moment.chosen_label,
            "weights": moment.chosen_weights,
        },
        "alternative": {
            "id": moment.alternative_id,
            "label": moment.alternative_label,
            "weights": moment.alternative_weights,
        },
        "question": moment.question,
        "options": moment.options,
        "answered": moment.answered,
        "userPrediction": moment.user_prediction,
    }
    if not reveal:
        return payload
    payload["evidence"] = {
        "source": "simulation",
        "actual": moment.actual_outcome,
        "counterfactual": moment.counterfactual_outcome,
        "delayRegret": moment.delay_regret,
        "arrivalRegret": moment.arrival_regret,
        "connectionRegret": moment.connection_regret,
        "detectionReasons": moment.detection_reasons,
    }
    payload["narrative"] = {
        "source": "narrator",
        "explanation": moment.explanation,
        "takeaway": moment.takeaway,
    }
    payload["predictionCorrect"] = moment.prediction_correct
    return payload


@router.post("/{session_id}/learning-moment/evaluate")
def evaluate_learning_moment(session_id: str, req: EvaluateIn):
    """Decide whether the decision just taken is worth a Learning Moment.

    Runs the counterfactual first and the frequency guards second: the budget
    check is cheap, but knowing *why* a decision was not worth interrupting for
    is only possible once the outcomes are known, and the reason is useful in the
    response. When the budget is exhausted the simulation is skipped outright.

    Blocking for the duration of the simulations (roughly 3-4 s per branch, so
    around 10 s for a chosen plus two alternatives). Returns
    ``{"triggered": false, "reason": ...}`` rather than an error when the
    decision is unremarkable, the session cannot be simulated yet, or the budget
    is spent — none of those are failures.
    """
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")

    env = session.env
    step = int(getattr(env, "_elapsed_steps", 0) or 0)

    budget = learning_moment_store.budget_check(session_id, step)
    if budget:
        return {"session_id": session_id, "step": step,
                "triggered": False, "reason": budget}

    alternatives_in = req.alternatives
    if alternatives_in is None:
        alternatives_in = _default_alternatives(req.chosen.id)
    if not alternatives_in:
        return {"session_id": session_id, "step": step, "triggered": False,
                "reason": "no alternative to compare against"}

    candidates = [
        Alternative(id=a.id, label=a.label, weights=dict(a.weights))
        for a in alternatives_in
    ]
    actual, evaluated = evaluate_branches(
        env, dict(req.chosen.weights), candidates,
        config=learning_moment_store.config,
    )

    # The planner's predicted score for the plan that is driving, so a
    # surprising success can be told apart from a merely good outcome.
    if actual is not None:
        from app.policies.goal_directed_policy import plan_info

        info = plan_info(env) or {}
        weighted = info.get("weighted")
        if isinstance(weighted, (int, float)):
            actual.predicted_weighted = float(weighted)

    verdict = detect(actual, evaluated, config=learning_moment_store.config)
    if not verdict.triggered:
        return {
            "session_id": session_id,
            "step": step,
            "triggered": False,
            "reason": verdict.skip_reason,
            "comparisons": [
                {
                    "id": a.id,
                    "label": a.label,
                    "outcome": a.outcome.to_dict() if a.outcome else None,
                    "unavailableReason": a.unavailable_reason,
                }
                for a in evaluated
            ],
        }

    reference = next(a for a in evaluated if a.id == verdict.reference_id)
    moment = LearningMoment(
        id=new_moment_id(),
        session_id=session_id,
        step=step,
        event_type=verdict.event_type,
        situation=_situation(env, dict(req.chosen.weights)),
        chosen_id=req.chosen.id,
        chosen_label=req.chosen.label,
        chosen_weights=dict(req.chosen.weights),
        actual_outcome=actual.to_dict(),
        alternative_id=reference.id,
        alternative_label=reference.label,
        alternative_weights=dict(reference.weights),
        counterfactual_outcome=reference.outcome.to_dict(),
        detection_reasons=verdict.reasons,
        delay_regret=verdict.delay_regret,
        arrival_regret=verdict.arrival_regret,
        connection_regret=verdict.connection_regret,
        question="",
        options=prediction_options(),
    )
    moment.question = narrator.question(moment)
    if req.decision_seq is not None:
        moment.situation["decisionSeq"] = int(req.decision_seq)
    learning_moment_store.add(moment)

    return {
        "session_id": session_id,
        "step": step,
        "triggered": True,
        "moment": _moment_payload(moment, reveal=False),
    }


@router.post("/{session_id}/learning-moment/{moment_id}/answer")
def answer_learning_moment(session_id: str, moment_id: str, req: AnswerIn):
    """Take the operator's prediction, then reveal the measured comparison."""
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    if req.prediction not in PREDICTIONS:
        raise HTTPException(
            422, f"prediction must be one of {list(PREDICTIONS)}")

    moment = learning_moment_store.record_answer(
        session_id, moment_id, req.prediction, narrator)
    if moment is None:
        raise HTTPException(404, f"Learning moment {moment_id} not found")

    return {
        "session_id": session_id,
        "moment": _moment_payload(moment, reveal=True),
    }


@router.get("/{session_id}/learning-moments")
def list_learning_moments(session_id: str):
    """Every moment of this episode plus the pattern across them.

    This is what the final reflection reads: the individual moments are single
    events, the summary is what they say together.
    """
    session = session_manager.get(session_id)
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    moments = learning_moment_store.all(session_id)
    return {
        "session_id": session_id,
        "moments": [
            _moment_payload(m, reveal=m.answered) for m in moments
        ],
        "summary": summarise(moments),
        "config": {
            "maxPerEpisode": learning_moment_store.config.max_per_episode,
            "minStepsBetween": learning_moment_store.config.min_steps_between,
            "delayThreshold": learning_moment_store.config.delay_threshold,
            "arrivalThreshold": learning_moment_store.config.arrival_threshold,
            "nearMissMaxDelay": learning_moment_store.config.near_miss_max_delay,
        },
    }


@router.delete("/{session_id}/learning-moments")
def clear_learning_moments(session_id: str):
    """Drop this episode's moments — used when the episode is reset."""
    learning_moment_store.clear_session(session_id)
    return {"session_id": session_id, "cleared": True}
