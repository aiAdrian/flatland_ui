"""Operator model (Co-Learning Level B): evidence gate, value profile,
prediction, confirmed-learning adaptation, autonomy suggestion — plus the API."""

import warnings

warnings.filterwarnings("ignore")

from app.core.operator_model import (  # noqa: E402
    VALUE_CONNECTION,
    VALUE_PUNCTUALITY,
    VALUE_STABILITY,
    ConfirmedLearning,
    DecisionSignal,
    OperatorModelStore,
    infer_value_axis,
)

CRITICAL = {"connection_critical": True, "low_delay": True, "low_ripple": True}


def _sig(value, deliberate=True, followed_ai=False, context=None, step=0):
    return DecisionSignal(
        step=step,
        handle=0,
        value=value,
        deliberate=deliberate,
        followed_ai=followed_ai,
        context=dict(context if context is not None else CRITICAL),
    )


# ── inverse-RL-lite ─────────────────────────────────────────────────────────
def test_infer_value_axis_from_kpi_deltas():
    fast = {"totalDelay": 10, "deadlocks": 2, "done": 5}
    stable = {"totalDelay": 40, "deadlocks": 0, "done": 5}
    throughput = {"totalDelay": 40, "deadlocks": 2, "done": 9}
    options = [fast, stable, throughput]

    assert infer_value_axis(fast, options) == VALUE_PUNCTUALITY
    assert infer_value_axis(stable, options) == VALUE_STABILITY
    assert infer_value_axis(throughput, options) == "throughput"


def test_infer_value_axis_connection_hint_wins_when_protecting():
    chosen = {"totalDelay": 40, "deadlocks": 1, "done": 4}
    other = {"totalDelay": 10, "deadlocks": 1, "done": 4}
    ctx = {"connection_critical": True, "protects_connection": True}
    assert infer_value_axis(chosen, [chosen, other], ctx) == VALUE_CONNECTION


def test_infer_value_axis_returns_none_for_a_compromise():
    """An option that is strictly beaten on every axis reveals no value axis."""
    chosen = {"totalDelay": 30, "deadlocks": 1, "done": 5}
    best_delay = {"totalDelay": 10, "deadlocks": 1, "done": 6}
    best_stable = {"totalDelay": 30, "deadlocks": 0, "done": 7}
    assert infer_value_axis(chosen, [chosen, best_delay, best_stable]) is None


# ── evidence gate (the overfitting guard) ───────────────────────────────────
def test_passive_accepts_do_not_shape_preferences():
    store = OperatorModelStore()
    store.add_signal("op", _sig(VALUE_PUNCTUALITY, deliberate=False, followed_ai=True))
    store.add_signal("op", _sig(VALUE_PUNCTUALITY, deliberate=False, followed_ai=True))
    profile = store.profile("op")

    assert profile.sample_size == 0
    assert profile.passive_count == 2
    assert profile.value_weights() == {}
    assert profile.value_profile().dominant is None


def test_deliberate_decisions_build_the_value_profile():
    store = OperatorModelStore()
    for _ in range(3):
        store.add_signal("op", _sig(VALUE_CONNECTION))
    store.add_signal("op", _sig(VALUE_PUNCTUALITY))
    vp = store.profile("op").value_profile()

    assert vp.dominant == VALUE_CONNECTION
    assert vp.label == "Connection-first"
    assert vp.dominant_pct >= 60
    assert vp.total == 4


# ── prediction ──────────────────────────────────────────────────────────────
def test_cold_start_prediction_is_empty():
    p = OperatorModelStore().profile("op").predict(CRITICAL)
    assert p.value is None
    assert p.basis == "cold_start"


def test_prediction_uses_similar_context():
    store = OperatorModelStore()
    for _ in range(3):
        store.add_signal("op", _sig(VALUE_CONNECTION))
    p = store.profile("op").predict(CRITICAL)

    assert p.value == VALUE_CONNECTION
    assert p.basis == "similar_context"
    assert p.confidence >= 0.6


def test_prediction_falls_back_to_overall_preference_for_new_context():
    store = OperatorModelStore()
    for _ in range(3):
        store.add_signal("op", _sig(VALUE_CONNECTION))
    other = {"connection_critical": False, "low_delay": False, "low_ripple": False}
    p = store.profile("op").predict(other)

    assert p.value == VALUE_CONNECTION
    assert p.basis == "overall_preference"


# ── adaptation ──────────────────────────────────────────────────────────────
def test_confirmed_learning_drives_the_adjustment():
    store = OperatorModelStore()
    store.add_learning(
        "op",
        ConfirmedLearning(
            statement="Protect critical connections when delay stays limited.",
            target_value=VALUE_CONNECTION,
            conditions={"connection_critical": True},
        ),
    )
    adj = store.profile("op").adjustment_for(CRITICAL)

    assert adj is not None
    assert adj.target_value == VALUE_CONNECTION
    assert adj.applied_learning
    assert adj.reason == "confirmed preference"


def test_confirmed_learning_does_not_fire_outside_its_condition():
    store = OperatorModelStore()
    store.add_learning(
        "op",
        ConfirmedLearning(
            statement="Protect critical connections.",
            target_value=VALUE_CONNECTION,
            conditions={"connection_critical": True},
        ),
    )
    adj = store.profile("op").adjustment_for({"connection_critical": False})
    assert adj is None


def test_learned_preference_needs_enough_consistent_evidence():
    store = OperatorModelStore()
    store.add_signal("op", _sig(VALUE_CONNECTION))
    assert store.profile("op").adjustment_for(CRITICAL) is None  # 1 signal: too thin

    store.add_signal("op", _sig(VALUE_CONNECTION))
    adj = store.profile("op").adjustment_for(CRITICAL)
    assert adj is not None
    assert adj.target_value == VALUE_CONNECTION


def test_adjustment_respects_available_values():
    store = OperatorModelStore()
    for _ in range(3):
        store.add_signal("op", _sig(VALUE_CONNECTION))
    adj = store.profile("op").adjustment_for(CRITICAL, available_values=[VALUE_STABILITY])
    assert adj is None


# ── inferred preferences -> Director dials ──────────────────────────────────
def test_cold_profile_proposes_neutral_dials():
    dials = OperatorModelStore().profile("op").suggested_director_weights()
    assert dials == {"punctuality": 1.0, "connections": 1.0, "stability": 1.0}


def test_dials_shift_toward_the_revealed_preference():
    store = OperatorModelStore()
    for _ in range(6):
        store.add_signal("op", _sig(VALUE_CONNECTION))
    dials = store.profile("op").suggested_director_weights()

    assert dials["connections"] > dials["punctuality"]
    assert dials["connections"] > dials["stability"]
    # non-negative and at least one positive: the planner's contract
    assert min(dials.values()) >= 0
    assert sum(dials.values()) > 0


def test_dial_proposal_is_damped_while_evidence_is_thin():
    store = OperatorModelStore()
    store.add_signal("op", _sig(VALUE_CONNECTION))
    thin = store.profile("op").suggested_director_weights()
    for _ in range(5):
        store.add_signal("op", _sig(VALUE_CONNECTION))
    strong = store.profile("op").suggested_director_weights()

    # one decision barely moves the dials; six move them clearly
    assert thin["connections"] < strong["connections"]
    assert abs(thin["connections"] - 1.0) < abs(strong["connections"] - 1.0)


def test_passive_accepts_do_not_move_the_dials():
    store = OperatorModelStore()
    for _ in range(6):
        store.add_signal("op", _sig(VALUE_PUNCTUALITY, deliberate=False, followed_ai=True))
    assert store.profile("op").suggested_director_weights() == {
        "punctuality": 1.0,
        "connections": 1.0,
        "stability": 1.0,
    }


def test_throughput_folds_into_the_punctuality_dial():
    store = OperatorModelStore()
    for _ in range(6):
        store.add_signal("op", _sig("throughput"))
    dials = store.profile("op").suggested_director_weights()
    assert dials["punctuality"] > dials["connections"]
    assert dials["punctuality"] > dials["stability"]


# ── autonomy / framing ──────────────────────────────────────────────────────
def test_frequent_overrides_lower_the_autonomy_suggestion():
    store = OperatorModelStore()
    for _ in range(4):
        store.add_signal("op", _sig(VALUE_CONNECTION, followed_ai=False))
    assert store.profile("op").suggested_option_presentation() == "neutral"


def test_following_the_ai_keeps_it_recommending():
    store = OperatorModelStore()
    for _ in range(4):
        store.add_signal("op", _sig(VALUE_PUNCTUALITY, followed_ai=True))
    assert store.profile("op").suggested_option_presentation() == "recommend"


# ── cross-session ───────────────────────────────────────────────────────────
def test_end_session_carries_evidence_into_the_next_session():
    store = OperatorModelStore()
    for _ in range(3):
        store.add_signal("op", _sig(VALUE_CONNECTION))
    store.end_session("op")
    profile = store.profile("op")

    assert profile.prior_sessions == 1
    assert profile.signals == []          # session-scoped signals cleared
    assert profile.is_warm                # but the profile is warm
    assert profile.prior_values[VALUE_CONNECTION] == 3
    # a fresh session predicts from the carried-over profile
    p = profile.predict(CRITICAL)
    assert p.value == VALUE_CONNECTION
    assert p.basis == "profile"


def test_profiles_are_isolated_per_operator():
    store = OperatorModelStore()
    store.add_signal("a", _sig(VALUE_CONNECTION))
    assert store.profile("b").sample_size == 0


# ── persistence ─────────────────────────────────────────────────────────────
def test_ended_shift_survives_a_restart(tmp_path):
    """The carried-over profile must outlive the process, not just the session.

    A demo that promises "your preferences carry over" restarts the backend on
    every code change; from memory alone the profile silently emptied while the
    UI still claimed a warm start.
    """
    path = tmp_path / "profiles.json"
    store = OperatorModelStore(path)
    for _ in range(3):
        store.add_signal("op", _sig(VALUE_CONNECTION))
    store.add_learning(
        "op", ConfirmedLearning(statement="Anschluss zuerst", target_value=VALUE_CONNECTION)
    )
    store.end_session("op")

    restarted = OperatorModelStore(path)
    profile = restarted.profile("op")
    assert profile.is_warm
    assert profile.prior_sessions == 1
    assert profile.prior_values[VALUE_CONNECTION] == 3
    assert [lrn.statement for lrn in profile.confirmed_learnings] == ["Anschluss zuerst"]


def test_running_session_signals_are_not_persisted(tmp_path):
    """Only what the operator ended the shift with is written down."""
    path = tmp_path / "profiles.json"
    store = OperatorModelStore(path)
    store.add_signal("op", _sig(VALUE_CONNECTION))
    store.add_learning(
        "op", ConfirmedLearning(statement="X", target_value=VALUE_CONNECTION)
    )  # triggers a save while the session is still open

    restarted = OperatorModelStore(path)
    assert restarted.profile("op").prior_values == {}
    assert restarted.profile("op").prior_sessions == 0


def test_reset_clears_the_persisted_profile(tmp_path):
    path = tmp_path / "profiles.json"
    store = OperatorModelStore(path)
    store.add_signal("op", _sig(VALUE_CONNECTION))
    store.end_session("op")
    store.reset("op")

    assert not OperatorModelStore(path).profile("op").is_warm


def test_no_path_means_no_file(tmp_path, monkeypatch):
    """A store built without a path stays in memory — test isolation depends on it."""
    monkeypatch.chdir(tmp_path)
    store = OperatorModelStore()
    store.add_signal("op", _sig(VALUE_CONNECTION))
    store.end_session("op")
    assert list(tmp_path.iterdir()) == []


def test_corrupt_file_starts_cold_instead_of_failing(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{not json", encoding="utf-8")
    assert OperatorModelStore(path).profile("op").is_warm is False
