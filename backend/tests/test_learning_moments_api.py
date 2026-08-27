"""Learning Moment REST surface.

The counterfactual needs a planned Director session, which costs seconds — those
paths are covered by the unit tests. What matters here is the contract: the
question payload must not carry the answer, the reveal must keep simulator
evidence and narrator prose apart, and an unplannable session must degrade
instead of failing.
"""

import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.learning_moments import (  # noqa: E402
    EVENT_MISTAKE,
    PREDICTION_BETTER,
    LearningMoment,
    learning_moment_store,
    prediction_options,
)
from app.main import app  # noqa: E402

client = TestClient(app)

FOCUS_A = {
    "id": "focus_delay",
    "label": "Focus A (punctuality)",
    "weights": {"punctuality": 5, "connections": 2, "stability": 2},
}


@pytest.fixture(autouse=True)
def _clean_store():
    yield
    for session_id in list(learning_moment_store._moments):
        learning_moment_store.clear_session(session_id)


def _make_session() -> str:
    r = client.post("/session", json={
        "width": 25, "height": 25, "number_of_agents": 2,
        "seed": 42, "max_num_cities": 2,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _seed_moment(session_id: str, step: int = 10) -> LearningMoment:
    """Insert a ready-made moment, bypassing the expensive simulation."""
    moment = LearningMoment(
        id=f"lm_seed_{step}",
        session_id=session_id,
        step=step,
        event_type=EVENT_MISTAKE,
        situation={"step": step, "trains": 4, "onMap": 3},
        chosen_id="focus_delay",
        chosen_label="Focus A (punctuality)",
        chosen_weights={"punctuality": 5, "connections": 2, "stability": 2},
        actual_outcome={
            "total_delay": 200, "max_delay": 40, "arrived": 3, "trains": 4,
            "all_arrived": False, "steps": 200, "connections_total": 3,
            "connections_kept": 1, "kept_ratio": 0.33,
            "predicted_weighted": 0.7,
        },
        alternative_id="focus_connections",
        alternative_label="Focus B (connections)",
        alternative_weights={"punctuality": 2, "connections": 5, "stability": 2},
        counterfactual_outcome={
            "total_delay": 120, "max_delay": 30, "arrived": 3, "trains": 4,
            "all_arrived": False, "steps": 200, "connections_total": 3,
            "connections_kept": 3, "kept_ratio": 1.0,
            "predicted_weighted": 0.5,
        },
        detection_reasons=["Focus B would have saved 80 steps of delay"],
        delay_regret=80,
        arrival_regret=0,
        connection_regret=2,
        question="You went with Focus A. What would Focus B have done?",
        options=prediction_options(),
    )
    return learning_moment_store.add(moment)


def test_unknown_session_is_404():
    assert client.post(
        "/session/nope/learning-moment/evaluate",
        json={"chosen": FOCUS_A}).status_code == 404
    assert client.get("/session/nope/learning-moments").status_code == 404
    assert client.post(
        "/session/nope/learning-moment/x/answer",
        json={"prediction": PREDICTION_BETTER}).status_code == 404


def test_without_a_committed_plan_it_declines_instead_of_failing():
    sid = _make_session()
    r = client.post(f"/session/{sid}/learning-moment/evaluate",
                    json={"chosen": FOCUS_A})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["triggered"] is False
    assert body["reason"]
    assert "moment" not in body


def test_the_question_payload_withholds_the_answer():
    sid = _make_session()
    _seed_moment(sid)
    listed = client.get(f"/session/{sid}/learning-moments").json()
    payload = listed["moments"][0]

    assert payload["question"]
    assert [o["id"] for o in payload["options"]] == ["better", "same", "worse"]
    assert payload["answered"] is False
    # The whole point: nothing about the outcome before the operator commits.
    assert "evidence" not in payload
    assert "narrative" not in payload
    assert "120" not in str(payload)


def test_answering_reveals_evidence_and_narrative_separately():
    sid = _make_session()
    moment = _seed_moment(sid)

    r = client.post(
        f"/session/{sid}/learning-moment/{moment.id}/answer",
        json={"prediction": PREDICTION_BETTER},
    )
    assert r.status_code == 200, r.text
    payload = r.json()["moment"]

    assert payload["answered"] is True
    assert payload["userPrediction"] == PREDICTION_BETTER
    # The alternative did save delay, so "better" is the correct guess.
    assert payload["predictionCorrect"] is True

    evidence = payload["evidence"]
    assert evidence["source"] == "simulation"
    assert evidence["actual"]["total_delay"] == 200
    assert evidence["counterfactual"]["total_delay"] == 120
    assert evidence["delayRegret"] == 80

    narrative = payload["narrative"]
    assert narrative["source"] == "narrator"
    assert narrative["explanation"]
    assert narrative["takeaway"]
    # The two stay separable: apart from the provenance label they share no
    # field, so no measurement arrives through the prose and no prose through
    # the measurements.
    assert (set(evidence) - {"source"}) & (set(narrative) - {"source"}) == set()
    assert "explanation" not in evidence and "takeaway" not in evidence
    assert "actual" not in narrative and "counterfactual" not in narrative


def test_a_wrong_prediction_is_graded_as_wrong():
    sid = _make_session()
    moment = _seed_moment(sid)
    r = client.post(f"/session/{sid}/learning-moment/{moment.id}/answer",
                    json={"prediction": "worse"})
    assert r.json()["moment"]["predictionCorrect"] is False


def test_an_invalid_prediction_is_rejected():
    sid = _make_session()
    moment = _seed_moment(sid)
    r = client.post(f"/session/{sid}/learning-moment/{moment.id}/answer",
                    json={"prediction": "maybe"})
    assert r.status_code == 422


def test_unknown_moment_is_404():
    sid = _make_session()
    r = client.post(f"/session/{sid}/learning-moment/lm_nope/answer",
                    json={"prediction": PREDICTION_BETTER})
    assert r.status_code == 404


def test_the_list_carries_the_summary_the_reflection_needs():
    sid = _make_session()
    for step in (10, 40, 70):
        _seed_moment(sid, step=step)
    for moment in learning_moment_store.all(sid):
        client.post(f"/session/{sid}/learning-moment/{moment.id}/answer",
                    json={"prediction": PREDICTION_BETTER})

    body = client.get(f"/session/{sid}/learning-moments").json()
    assert len(body["moments"]) == 3
    summary = body["summary"]
    assert summary["total"] == 3
    assert summary["answered"] == 3
    assert summary["byType"][EVENT_MISTAKE] == 3
    assert summary["pattern"]
    assert len(summary["takeaways"]) == 3
    # The thresholds are part of the answer: a reader can see what "relevant"
    # meant for this episode.
    assert body["config"]["maxPerEpisode"] >= 1


def test_budget_is_reported_rather_than_silently_dropping_moments():
    sid = _make_session()
    for step in range(0, 200, 30):
        _seed_moment(sid, step=step)
    r = client.post(f"/session/{sid}/learning-moment/evaluate",
                    json={"chosen": FOCUS_A})
    body = r.json()
    assert body["triggered"] is False
    assert "budget" in body["reason"]


def test_clearing_removes_the_episodes_moments():
    sid = _make_session()
    _seed_moment(sid)
    assert client.delete(f"/session/{sid}/learning-moments").json()["cleared"]
    assert client.get(f"/session/{sid}/learning-moments").json()["moments"] == []


def test_resetting_the_episode_clears_its_moments():
    sid = _make_session()
    _seed_moment(sid)
    assert client.post(f"/session/{sid}/reset").status_code == 200
    assert client.get(f"/session/{sid}/learning-moments").json()["moments"] == []
