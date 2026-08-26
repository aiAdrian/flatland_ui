"""The autonomous planner's activity feed.

Director mode's supervisory question is "what is the AI doing?". The answer
already existed in the plan info and was unreachable in the UI; this endpoint
exposes it cheaply and — crucially — without conflating the plan with a log.
"""
import warnings

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _make_session(malfunction_rate: float = 0.0) -> str:
    r = client.post("/session", json={
        "width": 25, "height": 25, "number_of_agents": 3,
        "seed": 42, "max_num_cities": 2,
        "malfunction_rate": malfunction_rate,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_unknown_session_is_404():
    assert client.get("/session/nope/director/activity").status_code == 404


def test_before_planning_the_feed_is_empty_but_well_formed():
    sid = _make_session()
    r = client.get(f"/session/{sid}/director/activity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recent"] == []
    assert body["upcoming"] == []
    assert body["replans"] == []
    assert body["totalDecisions"] == 0
    assert body["totalReplans"] == 0
    assert body["source"] is None


def test_committed_decisions_appear_and_carry_what_was_weighed():
    sid = _make_session()
    r = client.post(f"/session/{sid}/step", json={
        "n_steps": 6, "policy": "goal_directed"})
    assert r.status_code == 200, r.text

    body = client.get(f"/session/{sid}/director/activity").json()
    assert body["source"]
    entries = body["recent"] + body["upcoming"] + body["replans"]
    if body["totalDecisions"] == 0:
        # A model-free fallback plan carries no decision trace; the feed then
        # honestly has nothing to show rather than inventing entries.
        assert entries == []
        return

    assert entries
    for e in entries:
        assert e["kind"] in {"decision", "replan"}
        if e["kind"] == "decision" and not e["stuck"]:
            # The "it considered alternatives" evidence, not decoration.
            assert e["optionCount"] >= 1
            assert e["toNode"] is not None


def test_the_plan_ahead_is_kept_apart_from_what_already_happened():
    """The trace holds *planned* decision times. Merging them into one feed
    would announce a decision scheduled 30 steps out as having just happened."""
    sid = _make_session()
    client.post(f"/session/{sid}/step", json={
        "n_steps": 6, "policy": "goal_directed"})

    body = client.get(f"/session/{sid}/director/activity", params={"limit": 50}).json()
    step = body["step"]
    assert all(e["step"] <= step for e in body["recent"]), body["recent"]
    assert all(e["step"] > step for e in body["upcoming"]), body["upcoming"]
    # History reads newest first, the plan ahead soonest first.
    assert body["recent"] == sorted(body["recent"], key=lambda e: e["step"], reverse=True)
    assert body["upcoming"] == sorted(body["upcoming"], key=lambda e: e["step"])
    # Only committed decisions can lie ahead; a re-plan is always historic and
    # lives in its own channel so it cannot be crowded out by routine decisions.
    assert all(e["kind"] == "decision" for e in body["upcoming"])
    assert all(e["kind"] == "decision" for e in body["recent"])
    assert all(e["kind"] == "replan" for e in body["replans"])
    assert body["replans"] == sorted(body["replans"], key=lambda e: e["step"], reverse=True)


def test_the_response_stays_small_enough_to_poll():
    """Why this endpoint exists: `/director` carries the full trace with every
    weighed option per decision, which is far too large to poll for a feed of
    one-liners."""
    sid = _make_session()
    client.post(f"/session/{sid}/step", json={
        "n_steps": 8, "policy": "goal_directed"})

    activity = client.get(f"/session/{sid}/director/activity")
    full = client.get(f"/session/{sid}/director")
    assert activity.status_code == 200 and full.status_code == 200
    if (full.json().get("plan") or {}).get("trace"):
        assert len(activity.content) * 4 < len(full.content), (
            f"activity {len(activity.content)}B vs director {len(full.content)}B — "
            "the point of the endpoint is that it is much smaller"
        )


def test_limit_is_clamped_to_something_sane_activity():
    sid = _make_session()
    client.post(f"/session/{sid}/step", json={
        "n_steps": 6, "policy": "goal_directed"})
    for limit in (0, -5, 10_000):
        r = client.get(f"/session/{sid}/director/activity", params={"limit": limit})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["recent"]) <= 100
        assert len(body["upcoming"]) <= 100
        assert len(body["replans"]) <= 100
