"""The Co-Learning loop, end to end over HTTP.

Walks the whole Level B cycle the way the HMI bridge drives it
(`docs/plans/co-learning-direction.md`):

    deliberate decisions → inferred reward weights → confirmed preference
    → session ends → next session starts *warm* → the preference re-ranks the
    recommendation and shifts the Director dials

Needs neither Flatland nor a simulation session: the operator model is
deliberately independent of the simulator.
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

OP = "/operator/gereon"
#: critical connection, delay still limited, no ripple — the trade-off situation
CRITICAL = {"connection_critical": True, "low_delay": True, "low_ripple": True}


@pytest.fixture(autouse=True)
def _clean():
    operator_model_store.reset()
    yield
    operator_model_store.reset()


def _protect(deliberate=True):
    """The operator holds the train to keep the connection, and says why."""
    return client.post(
        f"{OP}/signal",
        json={
            "step": 10,
            "handle": 3,
            "value": "connection",
            "followedAi": False,
            "deliberate": deliberate,
            "context": CRITICAL,
        },
    )


def test_full_co_learning_loop():
    # ── session 1: cold start ────────────────────────────────────────────
    profile = client.get(OP).json()
    assert profile["isWarm"] is False
    assert profile["suggestedDirectorWeights"] == {
        "punctuality": 1.0,
        "connections": 1.0,
        "stability": 1.0,
    }
    assert client.post(f"{OP}/predict", json=CRITICAL).json()["basis"] == "cold_start"

    # the AI has no reason to nudge the ranking yet
    assert client.post(f"{OP}/adjustment", json={"context": CRITICAL}).json()[
        "adjustment"
    ] is None

    # ── the operator protects the connection three times, deliberately ───
    for _ in range(3):
        assert _protect().status_code == 200

    # …and once passively accepts a punctuality recommendation. This must NOT
    # count as evidence (the over-reliance guard).
    client.post(
        f"{OP}/signal",
        json={
            "value": "punctuality",
            "followedAi": True,
            "deliberate": False,
            "context": CRITICAL,
        },
    )

    profile = client.get(OP).json()
    assert profile["evidenceCount"] == 3
    assert profile["passiveCount"] == 1
    assert profile["valueProfile"]["dominant"] == "connection"
    # the passive punctuality accept left no trace in the weights
    assert "punctuality" not in profile["valueWeights"]

    # the model now nudges the ranking from its own statistics
    stat_adj = client.post(f"{OP}/adjustment", json={"context": CRITICAL}).json()[
        "adjustment"
    ]
    assert stat_adj["targetValue"] == "connection"
    assert stat_adj["appliedLearning"] is None  # not confirmed yet, just learned

    # ── the operator confirms the hypothesis in the reflection ('yes') ───
    client.post(
        f"{OP}/learning",
        json={
            "statement": "Bei kritischem Anschluss und geringer Zusatzverspätung "
            "bevorzugst du Halten.",
            "targetValue": "connection",
            "conditions": {"connection_critical": True},
        },
    )
    confirmed_adj = client.post(f"{OP}/adjustment", json={"context": CRITICAL}).json()[
        "adjustment"
    ]
    assert confirmed_adj["reason"] == "confirmed preference"
    assert "Halten" in confirmed_adj["appliedLearning"]  # the callout's quote

    # ── the shift ends: evidence folds into the carried-over profile ─────
    ended = client.post(f"{OP}/end-session").json()
    assert ended["priorSessions"] == 1
    assert ended["isWarm"] is True
    assert ended["evidenceCount"] == 0  # session-scoped signals cleared

    # ── session 2 starts warm ───────────────────────────────────────────
    warm = client.get(OP).json()
    assert warm["isWarm"] is True
    assert warm["valueProfile"]["dominant"] == "connection"

    # the AI predicts the operator before they have decided anything
    pred = client.post(f"{OP}/predict", json=CRITICAL).json()
    assert pred["value"] == "connection"
    assert pred["basis"] == "profile"

    # the confirmed preference still re-ranks — this drives the
    # "weil du mir das bestätigt hast" callout in the HMI
    adj = client.post(f"{OP}/adjustment", json={"context": CRITICAL}).json()["adjustment"]
    assert adj["targetValue"] == "connection"
    assert adj["appliedLearning"]

    # and the inferred reward weights now favour connections on the dials
    dials = warm["suggestedDirectorWeights"]
    assert dials["connections"] > dials["punctuality"]
    assert dials["connections"] > dials["stability"]
    assert min(dials.values()) >= 0 and sum(dials.values()) > 0


def test_loop_stays_neutral_for_a_purely_passive_operator():
    """Someone who only clicks 'accept' teaches the model nothing — by design."""
    for _ in range(6):
        client.post(
            f"{OP}/signal",
            json={
                "value": "punctuality",
                "followedAi": True,
                "deliberate": False,
                "context": CRITICAL,
            },
        )
    client.post(f"{OP}/end-session")

    profile = client.get(OP).json()
    assert profile["valueProfile"]["dominant"] is None
    assert profile["suggestedDirectorWeights"] == {
        "punctuality": 1.0,
        "connections": 1.0,
        "stability": 1.0,
    }
    assert client.post(f"{OP}/adjustment", json={"context": CRITICAL}).json()[
        "adjustment"
    ] is None


def test_overrides_lower_the_autonomy_suggestion_across_the_shift():
    """Frequent overrides → the AI should explain more and assert less."""
    assert client.get(OP).json()["optionPresentation"] == "recommend"
    for _ in range(4):
        _protect()  # deliberate, and not following the AI
    assert client.get(OP).json()["optionPresentation"] == "neutral"


def test_learning_outside_its_condition_does_not_fire():
    client.post(
        f"{OP}/learning",
        json={
            "statement": "Bei kritischem Anschluss bevorzugst du Halten.",
            "targetValue": "connection",
            "conditions": {"connection_critical": True},
        },
    )
    calm = {"connection_critical": False, "low_delay": True, "low_ripple": True}
    assert client.post(f"{OP}/adjustment", json={"context": calm}).json()[
        "adjustment"
    ] is None
