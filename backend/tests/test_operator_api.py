"""Operator-model REST surface (Co-Learning Level B).

Mounts only the operator router, so these tests need neither Flatland nor a
session — the model is deliberately independent of the simulator.
"""

import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.operator import router  # noqa: E402
from app.core.operator_model import operator_model_store  # noqa: E402

app = FastAPI()
app.include_router(router)
client = TestClient(app)

CRITICAL = {"connection_critical": True, "low_delay": True, "low_ripple": True}


@pytest.fixture(autouse=True)
def _clean_store():
    operator_model_store.reset()
    yield
    operator_model_store.reset()


def _signal(**kw):
    body = {
        "step": 0,
        "handle": 0,
        "value": "connection",
        "deliberate": True,
        "followedAi": False,
        "context": CRITICAL,
    }
    body.update(kw)
    return client.post("/operator/op/signal", json=body)


def test_cold_profile_is_empty():
    r = client.get("/operator/op")
    assert r.status_code == 200
    body = r.json()
    assert body["operatorId"] == "op"
    assert body["isWarm"] is False
    assert body["evidenceCount"] == 0
    assert body["valueProfile"]["dominant"] is None


def test_signal_round_trip_builds_the_profile():
    for _ in range(3):
        assert _signal().status_code == 200
    body = client.get("/operator/op").json()

    assert body["evidenceCount"] == 3
    assert body["valueProfile"]["dominant"] == "connection"
    assert body["valueProfile"]["label"] == "Connection-first"


def test_passive_signal_is_counted_but_not_evidence():
    _signal(deliberate=False, followedAi=True)
    body = client.get("/operator/op").json()

    assert body["passiveCount"] == 1
    assert body["evidenceCount"] == 0
    assert body["valueWeights"] == {}


def test_unknown_value_axis_is_rejected():
    r = _signal(value="teleportation")
    assert r.status_code == 422


def test_value_axis_is_inferred_from_kpis_when_not_given():
    chosen = {"totalDelay": 40, "deadlocks": 0, "done": 5}
    other = {"totalDelay": 10, "deadlocks": 3, "done": 5}
    r = _signal(value=None, chosenKpis=chosen, optionKpis=[chosen, other])
    assert r.status_code == 200
    assert r.json()["valueProfile"]["dominant"] == "stability"


def test_predict_endpoint():
    for _ in range(3):
        _signal()
    r = client.post("/operator/op/predict", json=CRITICAL)
    assert r.status_code == 200
    body = r.json()
    assert body["value"] == "connection"
    assert body["basis"] == "similar_context"


def test_learning_drives_adjustment_endpoint():
    r = client.post(
        "/operator/op/learning",
        json={
            "statement": "Protect critical connections when delay stays limited.",
            "targetValue": "connection",
            "conditions": {"connection_critical": True},
        },
    )
    assert r.status_code == 200
    assert len(r.json()["confirmedLearnings"]) == 1

    r = client.post("/operator/op/adjustment", json={"context": CRITICAL})
    adj = r.json()["adjustment"]
    assert adj["targetValue"] == "connection"
    assert adj["appliedLearning"]

    # outside its condition the learning must not fire
    r = client.post(
        "/operator/op/adjustment", json={"context": {"connection_critical": False}}
    )
    assert r.json()["adjustment"] is None


def test_unknown_learning_axis_is_rejected():
    r = client.post(
        "/operator/op/learning", json={"statement": "x", "targetValue": "nope"}
    )
    assert r.status_code == 422


def test_end_session_makes_the_profile_warm():
    for _ in range(2):
        _signal()
    body = client.post("/operator/op/end-session").json()

    assert body["priorSessions"] == 1
    assert body["isWarm"] is True
    assert body["evidenceCount"] == 0  # session signals cleared
    # the carried-over profile still predicts
    p = client.post("/operator/op/predict", json=CRITICAL).json()
    assert p["value"] == "connection"
    assert p["basis"] == "profile"


def test_reset_forgets_the_operator():
    _signal()
    client.delete("/operator/op")
    assert client.get("/operator/op").json()["evidenceCount"] == 0


def test_option_presentation_reflects_trust():
    for _ in range(4):
        _signal(followedAi=False)
    assert client.get("/operator/op").json()["optionPresentation"] == "neutral"
