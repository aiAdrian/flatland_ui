"""Director Mode Reflection Playground -- Streamlit entry point.

Run with:  streamlit run app.py

Version 0.1: no real LLM, no real simulator. The reflection agent, the
optimiser and the outcomes are all simulated by rules, templates and prepared
scenario data. The reflection agent sits behind the ``ReflectionAgent``
interface so it can later be swapped for a local LLM implementation.
"""

from __future__ import annotations

import os
import time

import streamlit as st

import event_logger as ev
from database import Database
from demo_profile import DEMO_PROFILE_ID, reset_profile, seed_demo_profile
from director_mode import DirectorSession
from fake_reflection_agent import FakeReflectionAgent
from live_director import LiveDirector
from profile_store import ProfileStore
from simulation import STATUS_AWAITING, STATUS_ENDED, STATUS_RUNNING, format_clock
from learning_store import (
    STATUS_CONFIRMED,
    STATUS_CORRECTED,
    STATUS_REJECTED,
)
from reflection_selector import selection_report
from forecast import build_forecast, strategy_score
from baseline import ai_only_shift
from scenario_engine import classify_outcome, list_scenarios, load_scenario
from user_model import UserModel
from values import value_profile
from strategies import (
    CONFIRM_REASON_JUST_FOLLOWING,
    CONFIRM_REASON_OTHER,
    CONFIRM_REASONS,
    CONFIRMATION_OVERRIDE,
    CONFIRMATION_QUICK_ACCEPT,
    CONFIRMATION_REASONED_ACCEPT,
    RATIONALE_FREE_TEXT,
    RATIONALE_NONE,
    RATIONALE_REASON_TAGS,
    STRATEGIES,
    strategy_name,
)
from visualizations import (
    COLOR_CONFLICT,
    COLOR_PROTECTED,
    COLOR_RISK,
    COLOR_TRAIN,
    COLOR_NORMAL,
    attention_feed,
    countdown_bar,
    event_banner,
    fmt_passengers,
    forecast_table,
    kpi_badge,
    kpi_strip,
    network_svg,
    pattern_bars,
    prediction_card,
    prediction_reveal,
    preference_panel,
    pressure_gauge,
    projected_network,
    relationship_panel,
    timeline,
)

st.set_page_config(page_title="Director Mode Reflection Playground", layout="wide")


# --------------------------------------------------------------------------- #
# Session state helpers
# --------------------------------------------------------------------------- #
def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("phase", "select")
    ss.setdefault("session", None)
    ss.setdefault("db", Database())
    ss.setdefault("agent", FakeReflectionAgent())
    ss.setdefault("controller", None)
    ss.setdefault("operator_id", "operator1")
    ss.setdefault("profile", None)
    ss.setdefault("live_last_wall", None)
    ss.setdefault("live_paused", False)
    ss.setdefault("live_speed", 3.0)
    ss.setdefault("decision_reveal", None)
    ss.setdefault("resolution_reveal", None)
    ss.setdefault("pending_choice", None)
    ss.setdefault("reason_other", False)
    ss.setdefault("moments", [])
    ss.setdefault("selection_report", None)
    ss.setdefault("reflection_index", 0)
    ss.setdefault("reflection_stage", "question")
    ss.setdefault("current_question", None)
    ss.setdefault("current_candidate", None)
    ss.setdefault("current_learning_id", None)
    ss.setdefault("edit_mode", False)


def reset_session() -> None:
    for key in (
        "session",
        "controller",
        "profile",
        "live_last_wall",
        "live_paused",
        "decision_reveal",
        "resolution_reveal",
        "pending_choice",
        "reason_other",
        "moments",
        "selection_report",
        "reflection_index",
        "reflection_stage",
        "current_question",
        "current_candidate",
        "current_learning_id",
        "edit_mode",
    ):
        st.session_state.pop(key, None)
    _init_state()
    st.session_state.phase = "select"


_init_state()


# --------------------------------------------------------------------------- #
# Small render helpers
# --------------------------------------------------------------------------- #
def render_header(session: DirectorSession, step: int) -> None:
    sc = session.scenario
    dp = session.decision_point(step)
    situation = dp.get("situation", {})
    sim_step = dp.get("sim_step", step + 1)
    total = sc.total_steps
    progress = min(1.0, sim_step / total) if total else 0.0

    n_critical = 1 if situation.get("critical_connection") else 0
    n_conflicts = 1 + len(situation.get("affected_trains", [])) // 3
    next_event = dp.get("next_event_min", 15)
    pressure = dp.get("operational_pressure", "LOW")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(
            f"### 🚦 Flatland Dispatcher &nbsp;<span style='color:{COLOR_TRAIN};'>"
            f"– Director Mode</span>",
            unsafe_allow_html=True,
        )
        st.caption(f"Scenario: {sc.name} · {sc.difficulty}")
    with c2:
        st.markdown(
            f"<div style='text-align:right;font-weight:600;'>Step {sim_step} / {total}"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.progress(progress)

    # status strip
    disruption = (
        f"<span style='color:{COLOR_RISK};'>● New disruption detected "
        f"(step {sim_step}, {situation.get('time_label','')})</span>"
        if pressure in ("HIGH", "STRESS")
        else "<span style='color:#8b8d98;'>● No new disruptions</span>"
    )
    st.markdown(
        f"<div style='display:flex;gap:18px;align-items:center;font-size:13px;"
        f"padding:6px 0;'>"
        f"<span style='color:{COLOR_CONFLICT};font-weight:600;'>⚠ {n_conflicts} conflicts</span>"
        f"<span style='color:{COLOR_PROTECTED};font-weight:600;'>🔗 {n_critical} critical connection(s)</span>"
        f"<span style='color:#555;'>🕒 Next significant event in {next_event} min</span>"
        f"<span style='margin-left:auto;'>{disruption}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_active_strategy_bar(recommended: str) -> None:
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;background:#eefaf3;
             border:1px solid {COLOR_PROTECTED}44;border-radius:8px;padding:8px 14px;
             margin:6px 0;">
          <span style="color:{COLOR_PROTECTED};font-weight:700;">🛡 ACTIVE STRATEGY</span>
          <span style="font-weight:600;">{strategy_name(recommended)}</span>
          <span style="background:{COLOR_PROTECTED};color:#fff;border-radius:10px;
                padding:1px 8px;font-size:11px;">Running</span>
          <span style="margin-left:auto;color:#888;font-size:12px;">
            🔄 Optimizer adapting actions within strategy</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def strategy_card_html(dp: dict, sid: str, recommended: str, index: int,
                       previewed: bool = False) -> str:
    strat = STRATEGIES.get(sid)
    eff = dp.get("strategy_effects", {}).get(sid, {})
    score = strategy_score(eff)
    is_reco = sid == recommended
    if is_reco:
        border = f"2px solid {COLOR_PROTECTED}"
    elif previewed:
        border = f"2px solid {COLOR_TRAIN}"
    else:
        border = "1px solid #e0e3ea"
    score_color = COLOR_PROTECTED if is_reco else COLOR_TRAIN
    badge = (
        f"<div style='color:{COLOR_PROTECTED};font-weight:700;font-size:11px;'>"
        f"ACTIVE · RECOMMENDED</div>"
        if is_reco
        else "<div style='font-size:11px;color:transparent;'>.</div>"
    )
    letter = strat.short if strat else chr(65 + index)
    reco_note = (
        f"<div style='background:{COLOR_PROTECTED}18;color:{COLOR_PROTECTED};"
        f"border-radius:6px;padding:4px 6px;font-size:11px;margin-top:6px;'>"
        f"⭐ Recommended because of confirmed preference</div>"
        if is_reco
        else ""
    )
    return f"""
    <div style="border:{border};border-radius:10px;padding:8px 10px;
         background:#fff;min-height:118px;">
      <div style="display:flex;justify-content:space-between;align-items:start;">
        <div>
          <span style="background:{score_color};color:#fff;border-radius:5px;
            padding:1px 6px;font-weight:700;">{letter}</span>
          <span style="font-weight:700;font-size:13px;"> {strategy_name(sid)}</span>
          {badge}
        </div>
        <div style="text-align:right;">
          <div style="font-size:20px;font-weight:800;color:{score_color};line-height:1;">
            {score}</div>
          <div style="font-size:9px;color:#999;">/100</div>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-top:6px;font-size:11px;">
        <div><span style="color:#999;">Delay </span>
          <b>{eff.get('delay_impact', '-')}</b></div>
        <div><span style="color:#999;">Conn </span>
          <b>{eff.get('connection_impact', '-')}</b></div>
        <div><span style="color:#999;">Ripple </span>
          <b>{eff.get('ripple_risk', '-')}</b></div>
      </div>
      {reco_note}
    </div>
    """


def render_why_panel(dp: dict, recommended: str, adaptive) -> None:
    """The 'WHY OPTION X' panel with reasons + co-learning effect."""
    strat = STRATEGIES.get(recommended)
    eff = dp.get("strategy_effects", {}).get(recommended, {})
    situation = dp.get("situation", {})
    letter = strat.short if strat else "?"

    reasons = []
    if situation.get("critical_connection") and eff.get("connection_impact") in (
        "Protected", "Excellent", "Kept"
    ):
        buf = situation.get("connection_buffer_min")
        reasons.append(
            ("🔗", "Protects a critical connection",
             f"Only {buf} min buffer at the junction." if buf else "")
        )
    if str(eff.get("ripple_risk", "")).lower() == "low":
        reasons.append(
            ("🌊", "Low ripple risk",
             f"Limited delay ({eff.get('delay_impact','-')}), no significant "
             f"follow-up conflicts expected.")
        )
    if adaptive.source == "learned":
        reasons.append(
            ("🧭", "Matches confirmed preference",
             "You tend to prioritise this when delay impact is limited and "
             "ripple risk is low.")
        )

    reason_html = "".join(
        f"<div style='margin:8px 0;'><b>{icon} {title}</b>"
        f"<div style='font-size:12px;color:#666;'>{sub}</div></div>"
        for icon, title, sub in reasons
    ) or "<div style='color:#888;font-size:13px;'>Balanced default option.</div>"

    base_name = strategy_name(adaptive.baseline)
    reco_name = strategy_name(recommended)
    if adaptive.adjusted:
        effect_txt = (
            f"Without your profile: <b>{base_name}</b>.<br>"
            f"With it: <b>{reco_name}</b>."
        )
    else:
        effect_txt = (
            f"Your profile and the baseline agree here — both point to "
            f"<b>{reco_name}</b>."
        )
    co_learning = (
        f"<div style='margin-top:12px;padding-top:10px;border-top:1px solid #eee;'>"
        f"<b>🔁 CO-LEARNING EFFECT</b>"
        f"<div style='font-size:12px;color:#666;margin-top:4px;'>{effect_txt}</div>"
        # the model already spells out *why* it shifted; show it instead of hiding it
        f"<div style='font-size:11px;color:#777;margin-top:6px;'>"
        f"{adaptive.explanation}</div>"
        f"<div style='font-size:11px;color:#999;margin-top:6px;'>"
        f"Applied as ranking adjustment only, not a hard rule.</div></div>"
    )

    st.markdown(
        f"<div style='border:1px solid #e0e3ea;border-radius:10px;padding:12px;"
        f"background:#fff;'><b>WHY OPTION {letter}</b>{reason_html}{co_learning}</div>",
        unsafe_allow_html=True,
    )


def render_outcome(episode: dict) -> None:
    outcome = episode.get("outcome", {})
    expected = outcome.get("expected", {})
    observed = outcome.get("observed", {})
    status = outcome.get("status", "")
    status_color = COLOR_PROTECTED if status == "Mostly as expected" else COLOR_CONFLICT

    st.markdown("#### Outcome")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Expected**")
        st.markdown(
            f"- Additional Delay: **{expected.get('additional_delay_min', '-')} min**\n"
            f"- Connection: **{expected.get('connection', '-')}**\n"
            f"- Follow-up Conflicts: **{expected.get('follow_up_conflicts', '-')}**\n"
            f"- Network: **{expected.get('network_state', '-')}**"
        )
    with c2:
        st.markdown("**Observed**")
        st.markdown(
            f"- Additional Delay: **{observed.get('additional_delay_min', '-')} min**\n"
            f"- Connection: **{observed.get('connection', '-')}**\n"
            f"- Follow-up Conflicts: **{observed.get('follow_up_conflicts', '-')}**\n"
            f"- Network: **{observed.get('network_state', '-')}**"
        )
    st.markdown(
        f"<div style='color:{status_color};font-weight:700;margin-top:6px;'>"
        f"Status: {status}</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Debug view
# --------------------------------------------------------------------------- #
def _debug_enabled() -> bool:
    """Developer view, off by default.

    Enable with ``PLAYGROUND_DEBUG=1`` or by appending ``?debug=1`` to the URL.
    It shows raw JSON and is not meant for the people the demo is shown to.
    """
    if os.getenv("PLAYGROUND_DEBUG", "").strip().lower() not in ("", "0", "false"):
        return True
    try:
        return str(st.query_params.get("debug", "")).strip().lower() in ("1", "true")
    except Exception:  # query params unavailable in older Streamlit
        return False


def render_debug(session: DirectorSession) -> None:
    if not _debug_enabled():
        return
    with st.expander("🛠 Debug view (raw events, episodes, patterns, learnings)"):
        tabs = st.tabs(["Events", "Decision Episodes", "Learnings"])
        with tabs[0]:
            st.json(session.logger.events())
        with tabs[1]:
            st.json(session.episodes())
        with tabs[2]:
            st.json(session.learning_store.learnings(session.session_id))


# --------------------------------------------------------------------------- #
# Phase: scenario selection
# --------------------------------------------------------------------------- #
def view_select() -> None:
    st.title("🎛️ Director Mode Reflection Playground")
    st.caption(
        "Version 0.1 · fully local · no LLM · human–AI co-learning prototype"
    )
    # operator identity drives the cross-session profile
    st.session_state.operator_id = st.text_input(
        "👤 Operator (your profile — learnings persist across sessions under this name)",
        value=st.session_state.operator_id,
    )
    prof = ProfileStore(st.session_state.db, st.session_state.operator_id).load()
    if prof.is_warm:
        st.success(
            f"Welcome back, **{prof.profile_id}**. Carrying over "
            f"{prof.prior_sessions} prior session(s), "
            f"{prof.prior_decisions} decision(s) and "
            f"**{len(prof.confirmed_learnings)} confirmed learning(s)** into this shift."
        )
        with st.expander(
            f"What the AI stores about you ({len(prof.confirmed_learnings)} "
            f"learning(s)) — and how to delete it",
            expanded=False,
        ):
            for lg in prof.confirmed_learnings:
                st.markdown(f"- {lg['statement']}")
            if prof.preferences:
                st.caption(
                    "Counted tendencies: "
                    + ", ".join(
                        f"{strategy_name(s)} ×{c}"
                        for s, c in sorted(prof.preferences.items(),
                                           key=lambda kv: -kv[1])
                    )
                )
            st.caption(
                "Only decisions you confirmed with a reason are counted. Quick "
                "accepts and deadline defaults are not."
            )
            if st.button("🗑 Delete this profile", key="reset_profile"):
                reset_profile(st.session_state.db, st.session_state.operator_id)
                st.rerun()
    else:
        st.info(
            f"New profile **{prof.profile_id}** — the AI has no picture of you yet. "
            f"Confirm learnings in the reflection to make future shifts start warm."
        )
        st.caption(
            "A cold start cannot show the cross-session effect: there is nothing "
            "carried over yet. Load the prepared profile to see a shift that starts "
            "warm, or work two shifts under the same name."
        )
        if st.button(f"🔥 Load prepared profile · {DEMO_PROFILE_ID}",
                     key="seed_profile"):
            seed_demo_profile(st.session_state.db, DEMO_PROFILE_ID)
            st.session_state.operator_id = DEMO_PROFILE_ID
            st.rerun()

    st.markdown("### Choose a scenario")

    scenarios = list_scenarios()
    cols = st.columns(2)
    diff_color = {
        "Easy": COLOR_PROTECTED,
        "Medium": COLOR_TRAIN,
        "Hard": COLOR_RISK,
        "Stress": COLOR_CONFLICT,
    }
    for i, sc in enumerate(scenarios):
        with cols[i % 2]:
            color = diff_color.get(sc.difficulty, COLOR_TRAIN)
            st.markdown(
                f"""
                <div style="border:1px solid #e0e3ea;border-left:5px solid {color};
                     border-radius:10px;padding:12px;margin-bottom:8px;background:#fff;">
                  <div style="font-size:18px;font-weight:700;">{sc.name}</div>
                  <div style="color:{color};font-weight:600;">{sc.difficulty}
                     · {sc.num_decisions} decisions</div>
                  <div style="font-size:13px;color:#555;margin-top:4px;">{sc.description}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            seed = st.number_input(
                "Seed", value=sc.seed, key=f"seed_{sc.scenario_id}", step=1
            )
            if st.button(f"▶ Start shift · {sc.name}", key=f"start_{sc.scenario_id}"):
                scenario = load_scenario(sc.scenario_id)
                operator_id = st.session_state.operator_id
                profile = ProfileStore(st.session_state.db, operator_id).load()
                st.session_state.profile = profile
                session = DirectorSession(st.session_state.db, scenario,
                                          seed=int(seed), profile_id=operator_id)
                st.session_state.session = session
                st.session_state.controller = LiveDirector(
                    session, speed=st.session_state.live_speed,
                    prior_preferences=profile.preferences,
                    confirmed_learnings=profile.confirmed_learnings,
                )
                st.session_state.live_last_wall = None
                st.session_state.live_paused = False
                st.session_state.flash_until = 0.0
                st.session_state.phase = "live"
                st.rerun()

    st.info(
        "Live mode: the railway runs continuously. You'll be pulled in at "
        "director moments with a real deadline — if you don't act in time, the "
        "AI executes its recommendation by default."
    )


# --------------------------------------------------------------------------- #
# Phase: live director mode
# --------------------------------------------------------------------------- #
LIVE_TICK = 0.6  # real seconds between auto-refresh ticks


def _ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def _live_header(controller: LiveDirector) -> None:
    sc = controller.session.scenario
    clock = format_clock(controller.clock_min)
    status_map = {
        STATUS_RUNNING: ("▶ Running", COLOR_PROTECTED),
        STATUS_AWAITING: ("⏸ Director attention required", COLOR_CONFLICT),
        STATUS_ENDED: ("■ Shift complete", COLOR_NORMAL),
    }
    status_txt, status_color = status_map.get(controller.status, ("", COLOR_NORMAL))
    pct = controller.shift.progress * 100
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:14px;'>"
        f"<span style='font-weight:800;'>🚦 Flatland Dispatcher</span>"
        f"<span style='color:{COLOR_TRAIN};font-size:13px;'>Director Mode · Live</span>"
        f"<span style='font-size:12px;color:#888;'>{sc.name} · {sc.difficulty}</span>"
        f"<span style='margin-left:auto;font-size:22px;font-weight:800;'>🕒 {clock}</span>"
        f"<span style='color:{status_color};font-weight:700;'>{status_txt}</span></div>"
        f"<div style='background:#e6e8ee;border-radius:5px;height:6px;margin:4px 0;'>"
        f"<div style='background:{COLOR_TRAIN};height:6px;border-radius:5px;"
        f"width:{pct:.0f}%;'></div></div>",
        unsafe_allow_html=True,
    )


def _render_decision_reveal(reveal: dict) -> None:
    """Immediate feedback about the *choice* — not yet the operational outcome."""
    if reveal.get("deferred"):
        st.warning(
            f"⏱ Deadline passed — the AI executed its recommendation: "
            f"**{strategy_name(reveal['selected_strategy'])}**"
        )
    pred = reveal.get("predicted_strategy")
    if pred:
        st.markdown(
            prediction_reveal(strategy_name(pred),
                              strategy_name(reveal["selected_strategy"]),
                              reveal["prediction_correct"]),
            unsafe_allow_html=True,
        )
    # deliberate confirmation vs. passive click-through
    if "preference_evidence" in reveal:
        if reveal["preference_evidence"]:
            st.success("✓ Preference evidence recorded — confidence increased.")
        else:
            st.warning("ℹ Logged as acceptance — not used as confirmed preference.")
    st.caption(
        f"Decision registered at {reveal.get('time_label','')} — the operational "
        f"effect will unfold as the shift continues."
    )


def _render_resolution_reveal(reveal: dict) -> None:
    """Later feedback: the operational outcome once it has materialised."""
    st.markdown(
        f"<div style='font-weight:700;color:{COLOR_TRAIN};'>📊 Result of your "
        f"{reveal.get('time_label','')} decision (now unfolding)</div>",
        unsafe_allow_html=True,
    )
    render_outcome(reveal["episode"])


def _render_running(controller: LiveDirector) -> None:
    shift = controller.shift
    # next event (for the map) and next *intervention* (for the heads-up banner)
    nxt = shift.events[shift.next_i] if shift.next_i < len(shift.events) else None
    next_intervention = next(
        (e for e in shift.events[shift.next_i:] if e.severity == "intervention"), None
    )
    if nxt:
        dp = controller.session.decision_point(nxt.index)
        st.caption(
            "▶ Traffic running — the optimizer is handling routine conflicts "
            "autonomously."
        )
        if next_intervention is not None:
            idp = controller.session.decision_point(next_intervention.index)
            st.markdown(event_banner(idp.get("event")), unsafe_allow_html=True)
        lc, rc = st.columns([2, 1])
        with lc:
            st.markdown(network_svg(dp.get("network", {}), display_height=280),
                        unsafe_allow_html=True)
        with rc:
            st.markdown(attention_feed(controller.feed), unsafe_allow_html=True)
    else:
        st.caption("Winding down the shift…")
        st.markdown(attention_feed(controller.feed), unsafe_allow_html=True)


def _commit_reasoned(controller: LiveDirector, selected: str, reason: str,
                     free_text: str | None = None) -> None:
    """Commit a decision together with the reason picked in the reflection card.

    The reason determines whether this counts as *confirmed preference evidence*
    (deliberate) or merely a logged acceptance ("just following" = passive)."""
    cur = controller.current
    step = cur.step
    recommended = cur.recommended
    is_override = selected != recommended
    explanation_viewed = bool(st.session_state.get(f"expl_{step}")) or (
        st.session_state.get(f"live_sel_{step}") not in (None, recommended)
    )

    reason_tags: list[str] = []
    rationale_text = None
    if reason == CONFIRM_REASON_OTHER:
        rationale_text = (free_text or "").strip() or None
        rationale_mode = RATIONALE_FREE_TEXT if rationale_text else RATIONALE_NONE
        preference_evidence = bool(rationale_text)
    elif reason == CONFIRM_REASON_JUST_FOLLOWING:
        rationale_mode = RATIONALE_NONE
        preference_evidence = False
    else:
        reason_tags = [reason]
        rationale_mode = RATIONALE_REASON_TAGS
        preference_evidence = True

    if is_override:
        confirmation_mode = CONFIRMATION_OVERRIDE
    elif preference_evidence:
        confirmation_mode = CONFIRMATION_REASONED_ACCEPT
    else:
        confirmation_mode = CONFIRMATION_QUICK_ACCEPT  # passive accept

    controller.decide(
        selected_strategy=selected,
        confirmation_mode=confirmation_mode,
        rationale_mode=rationale_mode,
        reason_tags=reason_tags,
        rationale_text=rationale_text,
        interaction={
            "explanation_viewed": explanation_viewed,
            "confirm_reason": reason,
            "preference_evidence": preference_evidence,
        },
    )
    st.session_state.decision_reveal = {
        **controller.last_decision,
        "preference_evidence": preference_evidence,
        "confirm_reason": reason,
        "until": time.time() + 4.5,
    }
    st.session_state.pending_choice = None
    st.session_state.reason_other = False


def _render_decision_ui(controller: LiveDirector) -> None:
    """Compact, single-screen decision layout (matches the MVP mockup)."""
    cur = controller.current
    dp = cur.decision_point
    recommended = cur.recommended
    adaptive = cur.adaptive
    prediction = cur.prediction
    situation = dp.get("situation", {})
    step = cur.step

    # trigger announcement (e.g. "Track blocked", "Train delayed")
    st.markdown(event_banner(dp.get("event")), unsafe_allow_html=True)

    # knock-on consequence of an earlier decision (carry-forward)
    if cur.carry_forward:
        cf = cur.carry_forward
        chain = cf.get("chain_index", 1)
        chain_note = (
            f" This is the {_ordinal(chain)} problem cascading from earlier calls — "
            f"unfavourable decisions keep spawning the next one."
            if chain >= 2 else
            " Unfavourable decisions tend to spawn the next problem."
        )
        st.markdown(
            f"<div style='background:{COLOR_CONFLICT}14;border-left:6px solid "
            f"{COLOR_CONFLICT};border-radius:8px;padding:8px 12px;margin-bottom:6px;'>"
            f"<b style='color:{COLOR_CONFLICT};'>⚠ Knock-on #{chain} from your "
            f"{cf.get('source_time','')} decision</b><br>"
            f"<span style='font-size:13px;color:#555;'>Back then {cf.get('cause','')}; "
            f"{cf.get('mechanism','')}, carrying <b>+{cf.get('carried_delay',0)} min</b> "
            f"of delay into this moment.{chain_note}</span></div>",
            unsafe_allow_html=True,
        )

    # cross-session payoff: make it unmistakable when a confirmed learning fires
    if adaptive.source == "learned_confirmed" and adaptive.adjusted:
        st.markdown(
            f"<div style='background:{COLOR_PROTECTED}18;border:2px solid "
            f"{COLOR_PROTECTED};border-radius:10px;padding:10px 14px;margin-bottom:6px;'>"
            f"<span style='font-size:15px;'>🧠 <b>Because you taught me this before</b>, "
            f"I changed my recommendation from "
            f"<b>{strategy_name(adaptive.baseline)}</b> to "
            f"<b>{strategy_name(adaptive.recommended)}</b>.</span><br>"
            f"<span style='font-size:12px;color:#555;'>Learned from your profile: "
            f"\"{adaptive.applied_learning}\"</span></div>",
            unsafe_allow_html=True,
        )

    _evt = controller.shift.events[controller.shift.next_i]
    st.markdown(
        countdown_bar(controller.remaining_decide_s, _evt.decide_s,
                      lead_min=_evt.window_min),
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='font-size:13px;color:#444;margin:-2px 0 4px;'>"
        f"{situation.get('description','')}</div>",
        unsafe_allow_html=True,
    )

    # currently previewed strategy (defaults to the recommendation)
    strategies = dp.get("strategies", [])
    shown = strategies[:3]
    if recommended not in shown and recommended in strategies:
        shown[-1] = recommended
    sel_key = f"live_sel_{step}"
    selected = st.session_state.get(sel_key, recommended)
    if selected not in shown:
        selected = recommended

    left, right = st.columns([2, 1])

    with left:
        # click a card to preview its consequences on the map below
        ccols = st.columns(len(shown) or 1)
        for i, sid in enumerate(shown):
            with ccols[i]:
                st.markdown(
                    strategy_card_html(dp, sid, recommended, i, previewed=sid == selected),
                    unsafe_allow_html=True,
                )
                is_sel = sid == selected
                if st.button("● Previewing" if is_sel else "Preview",
                             key=f"prev_{step}_{sid}", use_container_width=True,
                             type="primary" if is_sel else "secondary"):
                    st.session_state[sel_key] = sid
                    st.rerun()

        # map shows the PROJECTED consequences of the previewed strategy
        eff = dp.get("strategy_effects", {}).get(selected, {})
        expected = dp.get("outcomes", {}).get(selected, {}).get("expected", {})
        proj = projected_network(dp.get("network", {}), eff, expected)
        st.caption(f"Projected effect of **{strategy_name(selected)}** on the network:")
        st.markdown(network_svg(proj, display_height=230), unsafe_allow_html=True)
        st.markdown(
            forecast_table(build_forecast(
                situation, eff,
                open_problems=controller.kpis.get("open_problems", 0),
                expected=expected,
                strategy_label=strategy_name(selected))),
            unsafe_allow_html=True,
        )

        pending = st.session_state.get("pending_choice")
        pending_here = bool(pending and pending.get("step") == step)

        # confirm the previewed strategy -> opens the reflection card
        if not pending_here:
            if selected == recommended:
                confirm_label = f"▶ Let it run · {strategy_name(selected)}"
            else:
                confirm_label = f"✏ Apply adjustment · {strategy_name(selected)}"
            if st.button(confirm_label, key=f"confirm_{step}", type="primary",
                         use_container_width=True):
                st.session_state.pending_choice = {"step": step, "strategy": selected}
                st.session_state.reason_other = False
                st.rerun()

    with right:
        if pending_here:
            _render_reflection_card(controller, pending["strategy"])
        else:
            if prediction.strategy:
                st.markdown(
                    prediction_card(strategy_name(prediction.strategy),
                                    prediction.confidence, prediction.basis),
                    unsafe_allow_html=True,
                )
            render_why_panel(dp, recommended, adaptive)
            if st.button("👁 View AI reasoning", key=f"expl_btn_{step}",
                         use_container_width=True):
                st.session_state[f"expl_{step}"] = True
                controller.session.log_explanation_opened(step, recommended)
            if st.session_state.get(f"expl_{step}"):
                eff = dp.get("strategy_effects", {}).get(recommended, {})
                st.info(
                    f"Recommended **{strategy_name(recommended)}**: delay "
                    f"{eff.get('delay_impact','-')}, connection "
                    f"{eff.get('connection_impact','-')}, ripple "
                    f"{eff.get('ripple_risk','-')}."
                )
        st.markdown(attention_feed(controller.feed), unsafe_allow_html=True)


def _render_reflection_card(controller: LiveDirector, strategy: str) -> None:
    """Post-click reflection: confirm the main reason (deliberate vs. passive)."""
    cur = controller.current
    step = cur.step
    uses_learning = cur.adaptive.source == "learned_confirmed"
    st.markdown(
        f"<div style='border:1px solid {COLOR_TRAIN};border-radius:10px;padding:10px;"
        f"background:#f5f8ff;'><b>✨ Reflection</b><br>"
        + ("This recommendation uses a learning you confirmed. "
           if uses_learning else "")
        + f"Please confirm the main reason for choosing "
        f"<b>{strategy_name(strategy)}</b>.</div>",
        unsafe_allow_html=True,
    )
    for reason in CONFIRM_REASONS:
        if reason == CONFIRM_REASON_OTHER:
            continue
        is_passive = reason == CONFIRM_REASON_JUST_FOLLOWING
        if st.button(("🔁 " if is_passive else "") + reason,
                     key=f"reason_{step}_{reason}", use_container_width=True):
            _commit_reasoned(controller, strategy, reason)
            st.rerun()

    if st.button("✎ Other (free text)", key=f"reason_other_btn_{step}",
                 use_container_width=True):
        st.session_state.reason_other = True
        st.rerun()
    if st.session_state.get("reason_other"):
        txt = st.text_input("Your reason", key=f"free_{step}",
                            placeholder="in your own words")
        if st.button("Submit reason", key=f"submit_reason_{step}", type="primary",
                     use_container_width=True):
            _commit_reasoned(controller, strategy, CONFIRM_REASON_OTHER, txt)
            st.rerun()

    if st.button("← Back", key=f"cancel_reason_{step}"):
        st.session_state.pending_choice = None
        st.session_state.reason_other = False
        st.rerun()


@st.fragment(run_every=LIVE_TICK)
def _live_loop() -> None:
    controller: LiveDirector = st.session_state.controller
    if controller is None:
        return

    now = time.time()
    if st.session_state.live_last_wall is None:
        st.session_state.live_last_wall = now
    elapsed = now - st.session_state.live_last_wall
    st.session_state.live_last_wall = now
    if st.session_state.live_paused or st.session_state.get("pending_choice"):
        elapsed = 0.0  # pause the clock while the operator picks a reason

    controller.shift.speed = st.session_state.live_speed
    token = controller.tick(elapsed)
    if token == "timeout":
        controller.defer()
        st.session_state.decision_reveal = {**controller.last_decision,
                                            "until": time.time() + 3.5}
    elif token == "ended":
        controller.finalize()
        _enter_reflection_intro()
        st.rerun(scope="app")
        return

    # an outcome may have materialised this tick (delayed effect)
    resolution = controller.consume_resolution()
    if resolution:
        st.session_state.resolution_reveal = {**resolution, "until": time.time() + 4.5}

    _live_header(controller)
    st.markdown(kpi_strip(controller.kpis), unsafe_allow_html=True)

    now_t = time.time()
    dr = st.session_state.decision_reveal
    if dr and now_t < dr["until"]:
        _render_decision_reveal(dr)
    rr = st.session_state.resolution_reveal
    if rr and now_t < rr["until"]:
        _render_resolution_reveal(rr)

    if controller.status == STATUS_AWAITING and controller.current:
        _render_decision_ui(controller)
    elif controller.status == STATUS_RUNNING:
        _render_running(controller)
    elif controller.status == STATUS_ENDED:
        controller.finalize()
        _enter_reflection_intro()
        st.rerun(scope="app")


def view_live() -> None:
    controller: LiveDirector = st.session_state.controller
    if controller is None:
        st.session_state.phase = "select"
        st.rerun()
        return

    # slim control row (speed lives in the sidebar to save vertical space)
    c1, c2, c3, _ = st.columns([1.2, 1.4, 1, 2.4])
    with c1:
        if st.button("⏸ Pause" if not st.session_state.live_paused else "▶ Resume",
                     use_container_width=True):
            st.session_state.live_paused = not st.session_state.live_paused
            st.rerun()
    with c2:
        # presentation aid: jump straight to the next director moment
        if controller.status == STATUS_RUNNING and st.button(
                "⏭ Skip to next moment", use_container_width=True):
            controller.skip_to_next_moment()
            if controller.status == STATUS_ENDED:
                controller.finalize()
                _enter_reflection_intro()
            st.rerun()
    with c3:
        if st.button("⏹ End shift", use_container_width=True):
            controller.finalize()
            _enter_reflection_intro()
            st.rerun()

    _live_loop()
    render_debug(controller.session)


# --------------------------------------------------------------------------- #
# Phase: reflection intro
# --------------------------------------------------------------------------- #
def _enter_reflection_intro() -> None:
    session: DirectorSession = st.session_state.session
    session.start_reflection()
    report = selection_report(session.episodes())
    moments = report["selected"]
    for m in moments:
        session.logger.log(
            ev.EVENT_REFLECTION_CASE_SELECTED,
            ev.ACTOR_REFLECTION_AGENT,
            {"decision_id": m["decision_id"], "case_type": m["case_type"],
             "score": m["score"], "reasons": m["reasons"]},
        )
    st.session_state.selection_report = report
    st.session_state.moments = moments
    st.session_state.reflection_index = 0
    st.session_state.reflection_stage = "question"
    st.session_state.phase = "reflection_intro"


def render_cross_session_influence() -> None:
    """Show how the persisted profile shaped THIS shift, with concrete examples."""
    profile = st.session_state.profile
    controller = st.session_state.controller
    applied = controller.applied_learnings if controller else []

    st.markdown("### 🔁 Cross-session learning")
    if profile is None or not profile.is_warm:
        st.info(
            "This was a **cold start** — no prior profile. Confirm learnings below "
            "and they'll steer the AI's recommendations in your next shift."
        )
    else:
        st.caption(
            f"Carried in from your profile **{profile.profile_id}**: "
            f"{profile.prior_sessions} prior session(s), "
            f"{len(profile.confirmed_learnings)} confirmed learning(s)."
        )
        if applied:
            st.markdown(
                f"Your confirmed learnings **changed the AI's recommendation "
                f"{len(applied)} time(s)** this shift:"
            )
            for a in applied:
                verb = "✅ you followed it" if a["followed"] else "↩ you overrode it"
                st.markdown(
                    f"<div style='border-left:4px solid {COLOR_TRAIN};padding:6px 10px;"
                    f"margin:5px 0;background:#fff;border-radius:6px;'>"
                    f"<b>{a['time_label']}</b> — because of "
                    f"<i>\"{a['statement']}\"</i><br>"
                    f"I recommended <b>{strategy_name(a['recommended'])}</b> instead of "
                    f"the baseline <b>{strategy_name(a['baseline'])}</b> — {verb}.</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "None of your confirmed learnings matched today's situations, so "
                "the AI fell back to its baseline/within-session model."
            )


def _counts_to_panel(counts: dict) -> tuple[list, int]:
    total = sum(counts.values())
    if total == 0:
        return [], 0
    rows = sorted(
        ((s, c / total, c) for s, c in counts.items()),
        key=lambda t: t[1], reverse=True,
    )
    return rows, total


def _render_profile_evolution(session: DirectorSession, confirmed: list) -> None:
    """Before vs. after: what the AI knew, and what it now carries forward."""
    profile = st.session_state.profile
    st.markdown("### 📈 Profile evolution")

    before = dict(profile.preferences) if profile else {}
    after = dict(before)
    for ep in session.episodes():
        strat = ep.get("user_decision", {}).get("selected_strategy")
        if strat:
            after[strat] = after.get(strat, 0) + 1

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Before this shift")
        rows, n = _counts_to_panel(before)
        st.markdown(preference_panel(rows, n), unsafe_allow_html=True)
    with col2:
        st.caption("After this shift (carried forward)")
        rows, n = _counts_to_panel(after)
        st.markdown(preference_panel(rows, n), unsafe_allow_html=True)

    prior_learnings = len(profile.confirmed_learnings) if profile else 0
    total_learnings = prior_learnings + len(confirmed)
    st.success(
        f"Your profile now holds **{total_learnings} confirmed learning(s)** "
        f"({prior_learnings} carried in + {len(confirmed)} new). Your next shift as "
        f"**{st.session_state.operator_id}** will start with these applied."
    )


def view_reflection_intro() -> None:
    session: DirectorSession = st.session_state.session
    summary = session.decision_summary()
    moments = st.session_state.moments

    st.title("✅ SESSION COMPLETED")
    st.markdown("### Session Summary")
    c = st.columns(6)
    c[0].metric("Decisions", summary["total"])
    c[1].metric("Quick Accepts", summary["quick_accepts"])
    c[2].metric("Informed Accepts", summary["informed_accepts"])
    c[3].metric("Reasoned Accepts", summary["reasoned_accepts"])
    c[4].metric("Overrides", summary["overrides"])
    c[5].metric("Overrides (free text)", summary["overrides_free_text"])

    st.divider()
    render_cross_session_influence()

    st.divider()
    st.markdown(f"### 🔎 I found {len(moments)} moment(s) worth reflecting on.")
    report = st.session_state.get("selection_report") or {}
    if report:
        st.caption(
            f"Out of {report['considered']} decisions this shift. "
            f"{report['skipped_uneventful']} were routine (accepted, no pattern "
            f"relation, no surprise), {report['skipped_ranked_lower']} scored lower "
            f"or repeated a case type already covered. At most "
            f"{report['max_moments']} moments are shown to keep the reflection short."
        )
    st.markdown(timeline(moments), unsafe_allow_html=True)

    if st.button("Start reflection →", type="primary"):
        st.session_state.phase = "reflection"
        st.rerun()

    render_debug(session)


# --------------------------------------------------------------------------- #
# Phase: reflection dialogue
# --------------------------------------------------------------------------- #
def view_reflection() -> None:
    session: DirectorSession = st.session_state.session
    agent = st.session_state.agent
    moments = st.session_state.moments
    idx = st.session_state.reflection_index

    if idx >= len(moments):
        st.session_state.phase = "summary"
        st.rerun()
        return

    case = moments[idx]
    st.title(f"🪞 Reflection {idx + 1} / {len(moments)}")

    if st.session_state.reflection_stage == "question":
        _render_reflection_question(session, agent, case)
    else:
        _render_learning_candidate(session, case)

    render_debug(session)


def _render_reflection_case_card(session, case) -> None:
    """Show the initial situation and how it actually developed for this moment."""
    ep = case["episode"]
    step = ep.get("simulation_step", 0)
    dps = session.scenario.decision_points
    if step < 0 or step >= len(dps):
        return
    dp = dps[step]
    situation = dp.get("situation", {})
    selected = ep.get("user_decision", {}).get("selected_strategy")
    observed = ep.get("outcome", {}).get("observed", {})

    left, right = st.columns(2)
    with left:
        st.markdown("##### 🚦 Initial situation")
        st.caption(situation.get("description", ""))
        st.markdown(
            "".join([
                kpi_badge("Critical Conn.",
                          "Yes" if situation.get("critical_connection") else "No",
                          COLOR_CONFLICT if situation.get("critical_connection")
                          else COLOR_TRAIN),
                kpi_badge("Buffer", f"{situation.get('connection_buffer_min','-')} min"),
                kpi_badge("Delay", f"{situation.get('current_delay_min','-')} min"),
                kpi_badge("Ripple", str(situation.get("ripple_risk", "-")), COLOR_RISK),
            ]),
            unsafe_allow_html=True,
        )
        st.markdown(network_svg(dp.get("network", {}), display_height=170,
                                animate=False), unsafe_allow_html=True)
    with right:
        st.markdown(f"##### 📊 How it developed · *{strategy_name(selected)}*")
        render_outcome(ep)
        eff = dp.get("strategy_effects", {}).get(selected, {})
        proj = projected_network(dp.get("network", {}), eff, observed)
        st.markdown(network_svg(proj, display_height=170, animate=False),
                    unsafe_allow_html=True)


def _render_reflection_question(session, agent, case) -> None:
    q = st.session_state.current_question
    if q is None:
        q = agent.generate_reflection_question(case)
        st.session_state.current_question = q

    st.markdown(f"**Case type:** `{q['case_type']}`")
    st.info(q["summary"])

    # initial situation + how it actually developed
    _render_reflection_case_card(session, case)
    st.divider()

    ep = case["episode"]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Your decision pattern**")
        st.markdown(
            pattern_bars(case.get("pattern", {}),
                         ep.get("user_decision", {}).get("selected_strategy")),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"Expected: **{q['expected_pattern']}**  \n"
            f"You chose: **{q['actual_decision']}**"
        )
        if case["case_type"] == "pattern_deviation":
            st.markdown(
                f"<span style='color:{COLOR_RISK};font-weight:700;'>Pattern Deviation</span>",
                unsafe_allow_html=True,
            )

    st.markdown(f"#### 🤖 {q['question']}")
    selected_options = st.multiselect("Choose", q["options"], key=f"refopt_{case['decision_id']}")
    free_text = st.text_area("Or explain in your own words", key=f"reffree_{case['decision_id']}")

    if st.button("Submit answer →", type="primary"):
        answer = {"selected_options": selected_options, "free_text": free_text}
        session.logger.log(
            ev.EVENT_REFLECTION_ANSWER_SUBMITTED,
            ev.ACTOR_HUMAN,
            {"decision_id": case["decision_id"], **answer},
        )
        candidate = agent.propose_learning(case, answer)
        learning_id = session.learning_store.create_candidate(
            session.session_id, candidate
        )
        session.logger.log(
            ev.EVENT_LEARNING_PROPOSED,
            ev.ACTOR_REFLECTION_AGENT,
            {"learning_id": learning_id, "statement": candidate["statement"]},
        )
        st.session_state.current_candidate = candidate
        st.session_state.current_learning_id = learning_id
        st.session_state.reflection_stage = "learning"
        st.session_state.edit_mode = False
        st.rerun()


def _evidence_sentence(ev_data: dict) -> str:
    """Say what the evidence numbers actually refer to, and name the exceptions.

    The counts compare this learning's target strategy against what the operator
    deliberately chose in comparable situations earlier in the shift.
    """
    basis = ev_data.get("evidence_basis")
    target = strategy_name(ev_data.get("target_strategy"))
    if basis != "similar_decisions":
        return (
            "No comparable earlier decision this shift — this learning rests on "
            "your answer just now, not on a counted pattern."
        )
    supporting = ev_data.get("supporting_decisions", 0)
    contradictory = ev_data.get("contradictory_decisions", 0)
    total = supporting + contradictory
    txt = (
        f"Of {total} comparable decision(s) you made deliberately, "
        f"<b>{supporting}</b> point to <i>{target}</i>"
    )
    if contradictory:
        examples = ev_data.get("contradictory_examples") or []
        detail = ", ".join(
            f"{e.get('time_label') or e.get('decision_id')} → "
            f"{strategy_name(e.get('strategy'))}"
            for e in examples[:3]
        )
        txt += f" and <b>{contradictory}</b> go elsewhere"
        if detail:
            txt += f" ({detail})"
    else:
        txt += " and none go elsewhere"
    return txt + "."


def _render_learning_candidate(session, case) -> None:
    candidate = st.session_state.current_candidate
    learning_id = st.session_state.current_learning_id
    ev_data = candidate.get("evidence", {})

    st.markdown("### 🤝 SHARED LEARNING CANDIDATE")
    conditions = candidate.get("conditions", {})
    cond_lines = "".join(
        f"<div>✓ {k.replace('_', ' ')}: <b>{v}</b></div>" for k, v in conditions.items()
    )
    st.markdown(
        f"""
        <div style="border:1px solid #e0e3ea;border-left:5px solid {COLOR_TRAIN};
             border-radius:10px;padding:12px;background:#fff;">
          <div style="font-size:15px;font-weight:600;">{candidate['statement']}</div>
          <div style="margin-top:8px;font-size:13px;">{cond_lines}</div>
          <div style="margin-top:8px;font-size:13px;color:#555;">
            Confidence: <b>{candidate.get('confidence', 'Low')}</b>
          </div>
          <div style="margin-top:4px;font-size:12px;color:#666;">
            {_evidence_sentence(ev_data)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if candidate.get("boundaries"):
        st.caption("Boundaries: " + "; ".join(candidate["boundaries"]))

    if st.session_state.edit_mode:
        edited = st.text_area("Edit the learning statement",
                              value=candidate["statement"], key=f"edit_{learning_id}")
        cc1, cc2 = st.columns(2)
        if cc1.button("Save edit", type="primary"):
            session.learning_store.correct(learning_id, edited)
            session.logger.log(
                ev.EVENT_LEARNING_EDITED, ev.ACTOR_HUMAN,
                {"learning_id": learning_id, "statement": edited},
            )
            _advance_reflection()
        if cc2.button("Cancel"):
            st.session_state.edit_mode = False
            st.rerun()
        return

    b1, b2, b3 = st.columns(3)
    if b1.button("✅ Confirm", type="primary"):
        session.learning_store.confirm(learning_id)
        session.logger.log(ev.EVENT_LEARNING_CONFIRMED, ev.ACTOR_HUMAN,
                           {"learning_id": learning_id})
        _advance_reflection()
    if b2.button("✏️ Edit"):
        st.session_state.edit_mode = True
        st.rerun()
    if b3.button("🗑 Reject"):
        session.learning_store.reject(learning_id)
        session.logger.log(ev.EVENT_LEARNING_REJECTED, ev.ACTOR_HUMAN,
                           {"learning_id": learning_id})
        _advance_reflection()


def _advance_reflection() -> None:
    st.session_state.reflection_index += 1
    st.session_state.reflection_stage = "question"
    st.session_state.current_question = None
    st.session_state.current_candidate = None
    st.session_state.current_learning_id = None
    st.session_state.edit_mode = False
    st.rerun()


# --------------------------------------------------------------------------- #
# Phase: session learning summary
# --------------------------------------------------------------------------- #
def _render_vs_ai_baseline(session) -> None:
    """Your shift vs. the AI running unattended — did your judgement matter?"""
    controller = st.session_state.controller
    if controller is None:
        return
    mine = controller.kpis
    ai = ai_only_shift(session.scenario, session.seed)

    def _row(label, key, unit="", good_low=True, fmt=None):
        m, a = mine.get(key, 0), ai.get(key, 0)
        # colour the human column green when it beat the AI-only run
        better = (m < a) if good_low else (m > a)
        worse = (m > a) if good_low else (m < a)
        color = COLOR_PROTECTED if better else (COLOR_CONFLICT if worse else "#333")
        mv = fmt(m) if fmt else f"{m}{unit}"
        av = fmt(a) if fmt else f"{a}{unit}"
        return (
            f"<tr><td style='padding:5px 10px;color:#444;'>{label}</td>"
            f"<td style='padding:5px 10px;text-align:center;font-weight:800;"
            f"color:{color};'>{mv}</td>"
            f"<td style='padding:5px 10px;text-align:center;color:#888;'>{av}</td>"
            f"</tr>"
        )

    rows = (
        _row("Passengers affected (est.)", "passengers_affected", fmt=fmt_passengers)
        + _row("Connections lost", "connections_lost")
        + _row("Follow-up conflicts", "follow_up_conflicts")
        + _row("Added delay", "added_delay_min", " min")
    )
    st.markdown("### 🆚 Your shift vs. the AI unattended")
    st.markdown(
        "<table style='width:100%;border-collapse:collapse;background:#fff;"
        "border:1px solid #e0e3ea;border-radius:8px;'>"
        "<thead><tr>"
        "<th style='text-align:left;padding:6px 10px;'></th>"
        f"<th style='padding:6px 10px;color:{COLOR_TRAIN};'>With your interventions</th>"
        "<th style='padding:6px 10px;color:#888;'>AI unattended</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>",
        unsafe_allow_html=True,
    )

    # headline sentence on the most tangible metric
    dp_pax = ai.get("passengers_affected", 0) - mine.get("passengers_affected", 0)
    if dp_pax > 0:
        st.success(
            f"Your interventions spared an estimated **{fmt_passengers(dp_pax)} "
            f"passengers** and **{max(0, ai.get('connections_lost',0) - mine.get('connections_lost',0))} "
            f"connections** compared with letting the AI run unattended."
        )
    elif dp_pax < 0:
        st.warning(
            f"The AI unattended would have stranded ~{fmt_passengers(abs(dp_pax))[1:]} "
            f"fewer passengers — your interventions traded that for other goals "
            f"(e.g. lower delay)."
        )
    else:
        st.info("Your shift matched the AI-unattended baseline on passengers.")
    st.caption(
        "Passenger figures are estimates from typical train loads, not exact counts."
    )


def _render_ai_learned_about_you(session, confirmed) -> None:
    """The memorable closing panel: what the AI now knows about this operator."""
    episodes = session.episodes()
    deliberate = sum(
        1 for e in episodes
        if e.get("user_decision", {}).get("confirmation_mode")
        in ("reasoned_accept", "manual_override", "informed_accept")
    )
    passive = sum(
        1 for e in episodes
        if e.get("user_decision", {}).get("confirmation_mode")
        in ("quick_accept", "deferred_to_ai")
    )
    total = max(1, deliberate + passive)
    del_pct = deliberate / total * 100
    pas_pct = passive / total * 100

    profile = st.session_state.profile
    carried = [lg["statement"] for lg in (profile.confirmed_learnings if profile else [])]
    new = [lg["statement"] for lg in confirmed]
    prefs = {**dict.fromkeys(carried), **dict.fromkeys(new)}

    st.markdown("## 🧠 What the AI learned about you")

    # value profile: which goal the operator optimised, and its systemic cost
    vp = value_profile(episodes)
    if vp["dominant"]:
        kpis = st.session_state.controller.kpis if st.session_state.controller else {}
        st.markdown(
            f"<div style='background:{COLOR_TRAIN}12;border-radius:10px;padding:10px 14px;"
            f"margin-bottom:8px;'><span style='font-size:16px;'>You are a "
            f"<b>{vp['label']}</b> operator "
            f"<span style='color:#888;'>({vp['dominant_pct']}% of deliberate "
            f"decisions)</span></span><br>"
            f"<span style='font-size:13px;color:#555;'>Systemic cost this shift: "
            f"<b>{kpis.get('added_delay_min', 0)} min</b> added delay · "
            f"<b>{kpis.get('connections_lost', 0)}</b> connections lost · "
            f"<b>{fmt_passengers(kpis.get('passengers_affected', 0))}</b> "
            f"passengers affected (est.).</span></div>",
            unsafe_allow_html=True,
        )

    # deliberate vs. passive (over-reliance) bar
    st.markdown(
        f"<div style='font-size:13px;color:#555;margin-bottom:2px;'>"
        f"Decision engagement — deliberate vs. passive</div>"
        f"<div style='display:flex;height:26px;border-radius:8px;overflow:hidden;"
        f"border:1px solid #e0e3ea;'>"
        f"<div style='width:{del_pct:.0f}%;background:{COLOR_PROTECTED};color:#fff;"
        f"text-align:center;font-weight:700;line-height:26px;'>{del_pct:.0f}% deliberate</div>"
        f"<div style='width:{pas_pct:.0f}%;background:{COLOR_RISK};color:#fff;"
        f"text-align:center;font-weight:700;line-height:26px;'>{pas_pct:.0f}% passive</div>"
        f"</div>"
        f"<div style='font-size:12px;color:#888;margin-top:3px;'>"
        f"{deliberate} deliberate (reasoned / override) · {passive} passive "
        f"(quick-accept / deferred to AI)</div>",
        unsafe_allow_html=True,
    )

    # your interventions vs. the AI running unattended (credible what-if)
    _render_vs_ai_baseline(session)

    # trend: how well the AI predicts this operator, within and across sessions
    cumulative = []
    seen = hits = 0
    for e in sorted(episodes, key=lambda x: x.get("simulation_step", 0)):
        inter = e.get("user_decision", {}).get("interaction", {})
        if inter.get("predicted_strategy"):
            seen += 1
            hits += 1 if inter.get("prediction_correct") else 0
            cumulative.append(round(hits / seen * 100, 1))
    history = ProfileStore(session.db, session.profile_id).prediction_accuracy_history()
    if len(history) >= 2:
        st.markdown("#### 📈 How well I predict you — across sessions")
        st.line_chart(
            {"prediction accuracy %": [v for _, v in history]},
            height=180,
        )
    elif len(cumulative) >= 2:
        st.markdown("#### 📈 How well I predict you — during this shift")
        st.line_chart({"prediction accuracy %": cumulative}, height=180)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Your confirmed preferences")
        if prefs:
            for p in prefs:
                st.markdown(
                    f"<div style='background:{COLOR_TRAIN}14;border-radius:6px;"
                    f"padding:5px 9px;margin:4px 0;font-size:13px;'>✓ {p}</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No confirmed preferences yet.")
    with c2:
        st.markdown("#### How your profile changed a decision")
        applied = st.session_state.controller.applied_learnings if st.session_state.controller else []
        if applied:
            a = applied[0]
            verb = "you followed it" if a["followed"] else "you overrode it"
            st.markdown(
                f"<div style='border-left:4px solid {COLOR_PROTECTED};padding:8px 12px;"
                f"background:#fff;border-radius:6px;'>"
                f"At <b>{a['time_label']}</b> the AI recommended "
                f"<b>{strategy_name(a['recommended'])}</b> instead of "
                f"<b>{strategy_name(a['baseline'])}</b> — <i>{verb}</i>.<br>"
                f"<span style='font-size:12px;color:#666;'>Driven by: "
                f"\"{a['statement']}\"</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption(
                "No cross-session influence this shift. Confirm learnings to shape "
                "the next one."
            )


def view_summary() -> None:
    session: DirectorSession = st.session_state.session
    session.complete()

    st.title("📚 WHAT DID WE LEARN?")
    learnings = session.learning_store.learnings(session.session_id)
    confirmed = [l for l in learnings if l["status"] in (STATUS_CONFIRMED, STATUS_CORRECTED)]
    rejected = [l for l in learnings if l["status"] == STATUS_REJECTED]
    summary = session.decision_summary()

    _render_ai_learned_about_you(session, confirmed)
    st.divider()

    st.markdown("### Human Decision Patterns")
    st.write(
        f"- {summary['total']} decisions · {summary['overrides']} overrides · "
        f"{summary['quick_accepts']} quick accepts · {summary['deferrals']} deferred to AI"
    )

    # cross-session influence (how the carried-over profile shaped this shift)
    render_cross_session_influence()

    # profile evolution: what the AI knew before vs. what it will carry forward
    _render_profile_evolution(session, confirmed)

    st.markdown("### ✅ Confirmed Learnings (this session)")
    if not confirmed:
        st.write("No learnings were confirmed in this session.")
    for l in confirmed:
        ev_data = l.get("evidence", {})
        st.markdown(
            f"""
            <div style="border-left:4px solid {COLOR_PROTECTED};padding:8px 12px;
                 margin:6px 0;background:#fff;border-radius:6px;">
              <div style="font-weight:600;">{l['statement']}</div>
              <div style="font-size:12px;color:#555;">Status: {l['status']} ·
                Confidence: {l['confidence']} ·
                Evidence: {ev_data.get('supporting_decisions', 0)} supporting decisions</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### ⚠️ Where your own decisions disagree with a learning")
    st.caption(
        "A learning points at one strategy. These are the confirmed learnings "
        "where you deliberately chose something else in a comparable situation "
        "earlier in the shift — worth revisiting rather than an error."
    )
    contradictory = [
        l for l in confirmed if l.get("evidence", {}).get("contradictory_decisions", 0)
    ]
    if contradictory:
        for l in contradictory:
            st.markdown(f"- {l['statement']}  \n  {_evidence_sentence(l['evidence'])}",
                        unsafe_allow_html=True)
    else:
        st.write("None — your confirmed learnings match how you actually decided.")

    st.markdown("### ❓ Open Questions")
    if rejected:
        st.write("Rejected candidates that may need revisiting:")
        for l in rejected:
            st.write(f"- {l['statement']}")
    else:
        st.write("No open questions.")

    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("⬇️ Export event log (JSONL)"):
        path = session.logger.export_jsonl(
            session.db.db_path.parent / f"events_{session.session_id}.jsonl"
        )
        st.success(f"Exported to {path}")
    if c2.button("🔁 New session"):
        reset_session()
        st.rerun()

    render_debug(session)


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #
PHASES = {
    "select": view_select,
    "live": view_live,
    "reflection_intro": view_reflection_intro,
    "reflection": view_reflection,
    "summary": view_summary,
}

with st.sidebar:
    st.markdown("## Director Playground")
    st.caption("v0.1 · local · no LLM")
    if st.session_state.session is not None:
        s = st.session_state.session
        st.write(f"**Scenario:** {s.scenario.name}")
        st.write(f"**Session:** `{s.session_id}`")
        st.write(f"**Seed:** {s.seed}")
        if st.session_state.controller is not None:
            st.session_state.live_speed = st.select_slider(
                "⏩ Speed (sim-min / sec)", options=[1.0, 2.0, 3.0, 5.0, 8.0],
                value=st.session_state.live_speed,
            )
        st.markdown("---")
        st.markdown("### 👤 How I see you")
        prof = st.session_state.profile
        if prof is not None and prof.is_warm:
            st.caption(
                f"Profile: {prof.profile_id} · {prof.prior_sessions} prior "
                f"session(s) · {len(prof.confirmed_learnings)} learning(s)"
            )
        else:
            st.caption("The AI's live model of your preferences")
        _model = UserModel(
            s.episodes(),
            prior_preferences=(prof.preferences if prof else {}),
            confirmed_learnings=(prof.confirmed_learnings if prof else []),
        )
        st.markdown(
            preference_panel(_model.preferences(), _model.sample_size),
            unsafe_allow_html=True,
        )
        st.markdown(relationship_panel(s.episodes()), unsafe_allow_html=True)
    if st.button("Reset / new session"):
        reset_session()
        st.rerun()
    st.markdown("---")
    st.caption(
        "The reflection agent is a rule/template fake behind the ReflectionAgent "
        "interface, ready to be swapped for a local LLM."
    )

PHASES[st.session_state.phase]()
