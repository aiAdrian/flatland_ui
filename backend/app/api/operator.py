"""Operator-model endpoints — Co-Learning Level B (`docs/plans/co-learning-direction.md`).

The HMI posts interaction signals (accept / override, deliberate or passive) and
confirmed preferences; it reads back the derived operator view: value profile,
prediction, a re-ranking hint for the recommender, and an autonomy/framing
suggestion (`optionPresentation`).

Ranking adjustment only — the model never overrides the optimiser.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.operator_model import (
    VALUE_AXES,
    ConfirmedLearning,
    DecisionSignal,
    infer_value_axis,
    operator_model_store,
)

router = APIRouter()


# ── request / response models ───────────────────────────────────────────────
class SignalIn(BaseModel):
    """One decision the operator made."""

    step: int = 0
    handle: int = 0
    optionId: Optional[str] = None
    #: value axis, if the client already knows it; otherwise send the KPI deltas
    value: Optional[str] = None
    followedAi: bool = False
    #: deliberate = reasoned/override; passive = silent accept or timeout
    deliberate: bool = False
    context: dict[str, Any] = Field(default_factory=dict)
    #: `ScenarioKpis`-shaped deltas of the chosen option (for inverse-RL-lite)
    chosenKpis: Optional[dict[str, Any]] = None
    #: deltas of the options that were on the table (including the chosen one)
    optionKpis: list[dict[str, Any]] = Field(default_factory=list)


class LearningIn(BaseModel):
    statement: str
    targetValue: str
    conditions: dict[str, Any] = Field(default_factory=dict)


class ValueProfileOut(BaseModel):
    dominant: Optional[str]
    label: str
    dominantPct: int
    distribution: list[dict[str, Any]]
    total: int


class PredictionOut(BaseModel):
    value: Optional[str]
    confidence: float
    basis: str
    sampleSize: int


class AdjustmentOut(BaseModel):
    targetValue: str
    reason: str
    appliedLearning: Optional[str] = None
    confidence: float = 0.0


class ProfileOut(BaseModel):
    operatorId: str
    isWarm: bool
    priorSessions: int
    evidenceCount: int
    passiveCount: int
    trustRatio: float
    valueWeights: dict[str, float]
    valueProfile: ValueProfileOut
    confirmedLearnings: list[LearningIn]
    optionPresentation: str
    #: proposal for the Director dials, ready to POST to /session/{id}/director/weights
    suggestedDirectorWeights: dict[str, float]


def _profile_out(operator_id: str) -> ProfileOut:
    profile = operator_model_store.profile(operator_id)
    vp = profile.value_profile()
    return ProfileOut(
        operatorId=profile.operator_id,
        isWarm=profile.is_warm,
        priorSessions=profile.prior_sessions,
        evidenceCount=profile.sample_size,
        passiveCount=profile.passive_count,
        trustRatio=round(profile.trust_ratio(), 3),
        valueWeights={k: round(v, 3) for k, v in profile.value_weights().items()},
        valueProfile=ValueProfileOut(
            dominant=vp.dominant,
            label=vp.label,
            dominantPct=vp.dominant_pct,
            distribution=[
                {"value": v, "weight": w, "count": c} for v, w, c in vp.distribution
            ],
            total=vp.total,
        ),
        confirmedLearnings=[
            LearningIn(
                statement=lg.statement,
                targetValue=lg.target_value,
                conditions=lg.conditions,
            )
            for lg in profile.confirmed_learnings
        ],
        optionPresentation=profile.suggested_option_presentation(),
        suggestedDirectorWeights=profile.suggested_director_weights(),
    )


# ── endpoints ───────────────────────────────────────────────────────────────
@router.get("/operator/{operator_id}", response_model=ProfileOut)
def get_profile(operator_id: str) -> ProfileOut:
    """The AI's current model of this operator."""
    return _profile_out(operator_id)


@router.post("/operator/{operator_id}/signal", response_model=ProfileOut)
def post_signal(operator_id: str, body: SignalIn) -> ProfileOut:
    """Record one decision. Passive accepts are stored but never shape preferences."""
    if body.value is not None and body.value not in VALUE_AXES:
        raise HTTPException(status_code=422, detail=f"unknown value axis: {body.value}")

    value = body.value
    if value is None and body.chosenKpis is not None:
        value = infer_value_axis(body.chosenKpis, body.optionKpis, body.context)

    operator_model_store.add_signal(
        operator_id,
        DecisionSignal(
            step=body.step,
            handle=body.handle,
            option_id=body.optionId,
            value=value,
            followed_ai=body.followedAi,
            deliberate=body.deliberate,
            context=body.context,
        ),
    )
    return _profile_out(operator_id)


@router.post("/operator/{operator_id}/learning", response_model=ProfileOut)
def post_learning(operator_id: str, body: LearningIn) -> ProfileOut:
    """Register a preference the operator confirmed ('yes' in the HMI)."""
    if body.targetValue not in VALUE_AXES:
        raise HTTPException(
            status_code=422, detail=f"unknown value axis: {body.targetValue}"
        )
    operator_model_store.add_learning(
        operator_id,
        ConfirmedLearning(
            statement=body.statement,
            target_value=body.targetValue,
            conditions=body.conditions,
        ),
    )
    return _profile_out(operator_id)


@router.post("/operator/{operator_id}/predict", response_model=PredictionOut)
def predict(operator_id: str, context: dict[str, Any] | None = None) -> PredictionOut:
    """Which value axis will this operator optimise for in this situation?"""
    p = operator_model_store.profile(operator_id).predict(context or {})
    return PredictionOut(
        value=p.value, confidence=p.confidence, basis=p.basis, sampleSize=p.sample_size
    )


class AdjustmentQuery(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    availableValues: Optional[list[str]] = None


@router.post("/operator/{operator_id}/adjustment")
def adjustment(operator_id: str, body: AdjustmentQuery) -> dict[str, Any]:
    """Re-ranking hint for the recommender, or ``{"adjustment": null}``."""
    adj = operator_model_store.profile(operator_id).adjustment_for(
        body.context, body.availableValues
    )
    if adj is None:
        return {"adjustment": None}
    return {
        "adjustment": AdjustmentOut(
            targetValue=adj.target_value,
            reason=adj.reason,
            appliedLearning=adj.applied_learning,
            confidence=adj.confidence,
        ).model_dump()
    }


@router.post("/operator/{operator_id}/end-session", response_model=ProfileOut)
def end_session(operator_id: str) -> ProfileOut:
    """Fold this session's deliberate evidence into the carried-over prior."""
    operator_model_store.end_session(operator_id)
    return _profile_out(operator_id)


@router.delete("/operator/{operator_id}", response_model=ProfileOut)
def reset_profile(operator_id: str) -> ProfileOut:
    """Forget everything about this operator (demo / test reset)."""
    operator_model_store.reset(operator_id)
    return _profile_out(operator_id)
