"""Learning Moment detection, budget guards and narration.

Pure logic only — no Flatland, no session. The counterfactual itself is a thin
wrapper over `replan.simulate_forward`, which `test_goal_based_replan.py` already
covers; what needs pinning down here is the classification on top of it and the
promise that the narrator never invents a number.
"""

import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

from app.core.learning_moments import (  # noqa: E402
    EVENT_MISTAKE,
    EVENT_NEAR_MISS,
    EVENT_SURPRISING_SUCCESS,
    PREDICTION_BETTER,
    PREDICTION_SAME,
    PREDICTION_WORSE,
    Alternative,
    BranchOutcome,
    LearningMoment,
    LearningMomentStore,
    TemplateNarrator,
    TriggerConfig,
    detect,
    prediction_options,
    summarise,
)

CONFIG = TriggerConfig()


def outcome(
    total_delay=100, max_delay=20, arrived=3, trains=4, all_arrived=False,
    connections_kept=2, connections_total=3, predicted=None,
) -> BranchOutcome:
    return BranchOutcome(
        total_delay=total_delay,
        max_delay=max_delay,
        arrived=arrived,
        trains=trains,
        all_arrived=all_arrived,
        steps=200,
        connections_total=connections_total,
        connections_kept=connections_kept,
        kept_ratio=connections_kept / max(connections_total, 1),
        predicted_weighted=predicted,
    )


def alt(out: BranchOutcome | None, id="focus_connections", label="Focus B") -> Alternative:
    return Alternative(
        id=id, label=label,
        weights={"punctuality": 2, "connections": 5, "stability": 2},
        outcome=out,
    )


# ── detection ──────────────────────────────────────────────────────────────


def test_no_alternative_means_no_moment():
    assert detect(outcome(), [], CONFIG).triggered is False
    assert detect(None, [alt(outcome())], CONFIG).triggered is False
    assert detect(outcome(), [alt(None)], CONFIG).skip_reason


def test_close_outcomes_do_not_interrupt():
    verdict = detect(outcome(total_delay=100), [alt(outcome(total_delay=90))], CONFIG)
    assert verdict.triggered is False
    assert "zu ähnlich" in verdict.skip_reason


def test_clearly_better_alternative_is_a_mistake():
    verdict = detect(
        outcome(total_delay=200, arrived=3),
        [alt(outcome(total_delay=120, arrived=3))],
        CONFIG,
    )
    assert verdict.triggered
    assert verdict.event_type == EVENT_MISTAKE
    assert verdict.delay_regret == 80
    assert verdict.reasons


def test_one_more_arrival_is_always_a_mistake():
    """An arrival difference is never noise, however small the delay gap."""
    verdict = detect(
        outcome(arrived=2, total_delay=100),
        [alt(outcome(arrived=3, total_delay=100))],
        CONFIG,
    )
    assert verdict.event_type == EVENT_MISTAKE
    assert verdict.arrival_regret == 1


def test_beating_a_higher_rated_option_is_a_surprising_success():
    verdict = detect(
        outcome(total_delay=100, predicted=0.4),
        [alt(outcome(total_delay=180, predicted=0.9))],
        CONFIG,
    )
    assert verdict.event_type == EVENT_SURPRISING_SUCCESS
    assert "bewertete" in verdict.reasons[0]


def test_beating_a_lower_rated_option_is_still_reported_as_success():
    verdict = detect(
        outcome(total_delay=100, predicted=0.9),
        [alt(outcome(total_delay=180, predicted=0.4))],
        CONFIG,
    )
    assert verdict.event_type == EVENT_SURPRISING_SUCCESS
    assert "bewertete" not in verdict.reasons[0]


def test_a_delay_spike_an_alternative_would_have_avoided_is_a_near_miss():
    verdict = detect(
        outcome(total_delay=100, max_delay=80),
        [alt(outcome(total_delay=95, max_delay=20))],
        CONFIG,
    )
    assert verdict.event_type == EVENT_NEAR_MISS
    assert "80" in verdict.reasons[0]


def test_a_spike_both_options_share_is_not_a_near_miss():
    verdict = detect(
        outcome(total_delay=100, max_delay=80),
        [alt(outcome(total_delay=95, max_delay=80))],
        CONFIG,
    )
    assert verdict.triggered is False


def test_the_reference_is_the_strongest_alternative():
    """Ranked arrivals first, then delay — the way the planner ranks branches."""
    weak = alt(outcome(arrived=3, total_delay=90), id="weak", label="Weak")
    strong = alt(outcome(arrived=4, total_delay=300), id="strong", label="Strong")
    verdict = detect(outcome(arrived=3, total_delay=100), [weak, strong], CONFIG)
    assert verdict.reference_id == "strong"


def test_thresholds_are_configurable():
    loose = TriggerConfig(delay_threshold=200)
    verdict = detect(
        outcome(total_delay=200), [alt(outcome(total_delay=120))], loose)
    assert verdict.triggered is False


# ── frequency guards ───────────────────────────────────────────────────────


def moment(step=10, event_type=EVENT_MISTAKE, session="s1", **kw) -> LearningMoment:
    base = dict(
        id=f"lm_{step}",
        session_id=session,
        step=step,
        event_type=event_type,
        situation={"step": step},
        chosen_id="focus_delay",
        chosen_label="Focus A",
        chosen_weights={"punctuality": 5, "connections": 2, "stability": 2},
        actual_outcome=outcome(total_delay=200, arrived=3).to_dict(),
        alternative_id="focus_connections",
        alternative_label="Focus B",
        alternative_weights={"punctuality": 2, "connections": 5, "stability": 2},
        counterfactual_outcome=outcome(total_delay=120, arrived=3).to_dict(),
        detection_reasons=["would have saved 80 steps"],
        delay_regret=80,
        arrival_regret=0,
        connection_regret=0,
        question="What would Focus B have done?",
        options=prediction_options(),
    )
    base.update(kw)
    return LearningMoment(**base)


def test_episode_budget_stops_further_moments():
    store = LearningMomentStore(TriggerConfig(max_per_episode=2,
                                              min_steps_between=0))
    assert store.budget_check("s1", 10) is None
    store.add(moment(step=10))
    store.add(moment(step=20))
    assert "budget" in store.budget_check("s1", 30)


def test_moments_are_spaced_out():
    store = LearningMomentStore(TriggerConfig(min_steps_between=20))
    store.add(moment(step=10))
    assert "too soon" in store.budget_check("s1", 25)
    assert store.budget_check("s1", 30) is None


def test_budget_is_per_session():
    store = LearningMomentStore(TriggerConfig(max_per_episode=1))
    store.add(moment(step=10, session="s1"))
    assert store.budget_check("s1", 40) is not None
    assert store.budget_check("s2", 40) is None


def test_clearing_a_session_frees_the_budget():
    store = LearningMomentStore(TriggerConfig(max_per_episode=1))
    store.add(moment(step=10))
    store.clear_session("s1")
    assert store.budget_check("s1", 40) is None
    assert store.all("s1") == []


# ── prediction grading ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "delay_regret,arrival_regret,truth",
    [
        (80, 0, PREDICTION_BETTER),    # the alternative saves delay
        (-80, 0, PREDICTION_WORSE),    # the alternative costs delay
        (0, 1, PREDICTION_BETTER),     # the alternative gets one more home
        (0, 0, PREDICTION_SAME),
    ],
)
def test_prediction_is_graded_against_the_measured_difference(
    delay_regret, arrival_regret, truth
):
    store = LearningMomentStore(TriggerConfig())
    store.add(moment(delay_regret=delay_regret, arrival_regret=arrival_regret))
    graded = store.record_answer("s1", "lm_10", truth, TemplateNarrator())
    assert graded.prediction_correct is True
    assert graded.user_prediction == truth

    store2 = LearningMomentStore(TriggerConfig())
    store2.add(moment(delay_regret=delay_regret, arrival_regret=arrival_regret))
    wrong = PREDICTION_SAME if truth != PREDICTION_SAME else PREDICTION_BETTER
    assert store2.record_answer(
        "s1", "lm_10", wrong, TemplateNarrator()).prediction_correct is False


def test_answering_an_unknown_moment_returns_none():
    store = LearningMomentStore(TriggerConfig())
    assert store.record_answer(
        "s1", "nope", PREDICTION_SAME, TemplateNarrator()) is None


# ── narration ──────────────────────────────────────────────────────────────


def test_the_question_does_not_give_the_answer_away():
    text = TemplateNarrator().question(moment())
    assert "Focus B" in text
    assert "80" not in text  # no measured figure before the operator commits
    for word in ("besser", "schlechter", "spart"):
        assert word not in text.lower()


def test_explanation_only_uses_numbers_from_the_moment():
    """The narrator interprets; it must not introduce quantities of its own."""
    m = moment()
    text = TemplateNarrator().explain(m)
    import re

    numbers = {int(n) for n in re.findall(r"\d+", text)}
    known = {
        m.delay_regret,
        m.actual_outcome["total_delay"],
        m.counterfactual_outcome["total_delay"],
        m.actual_outcome["arrived"],
        m.counterfactual_outcome["arrived"],
        m.actual_outcome["trains"],
        m.actual_outcome["max_delay"],
        m.counterfactual_outcome["max_delay"],
        abs(m.arrival_regret),
        abs(m.connection_regret),
    }
    assert numbers <= known, f"narrator invented {numbers - known}"


def test_every_event_type_gets_a_question_and_a_takeaway():
    narrator = TemplateNarrator()
    for event_type in (EVENT_MISTAKE, EVENT_NEAR_MISS, EVENT_SURPRISING_SUCCESS):
        m = moment(event_type=event_type)
        assert narrator.question(m).strip()
        assert narrator.takeaway(m).strip()
        assert narrator.explain(m).strip()


def test_an_arrival_difference_drives_the_takeaway():
    m = moment(arrival_regret=1)
    assert "ankünfte" in TemplateNarrator().takeaway(m).lower()


# ── cross-moment summary, what the final reflection reads ──────────────────


def test_summary_names_a_repeated_direction():
    store = LearningMomentStore(TriggerConfig(max_per_episode=9,
                                              min_steps_between=0))
    for step in (10, 30, 50):
        store.add(moment(step=step))
    for m in store.all("s1"):
        store.record_answer("s1", m.id, PREDICTION_SAME, TemplateNarrator())

    report = summarise(store.all("s1"))
    assert report["total"] == 3
    assert report["answered"] == 3
    assert report["byType"][EVENT_MISTAKE] == 3
    assert "Anschlüsse" in report["pattern"]
    assert len(report["takeaways"]) == 3


def test_summary_reports_repeated_mispredictions():
    store = LearningMomentStore(TriggerConfig(max_per_episode=9,
                                              min_steps_between=0))
    # Alternating alternatives, so no single direction repeats.
    store.add(moment(step=10, delay_regret=80,
                     alternative_weights={"punctuality": 5, "connections": 2,
                                          "stability": 2}))
    store.add(moment(step=30, delay_regret=80,
                     alternative_weights={"punctuality": 2, "connections": 2,
                                          "stability": 5}))
    for m in store.all("s1"):
        store.record_answer("s1", m.id, PREDICTION_WORSE, TemplateNarrator())

    report = summarise(store.all("s1"))
    assert report["mispredicted"] == 2
    assert "Intuition" in report["pattern"]


def test_summary_of_nothing_is_empty_not_a_claim():
    report = summarise([])
    assert report["total"] == 0
    assert report["pattern"] is None
