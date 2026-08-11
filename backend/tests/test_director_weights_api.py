"""Director dials over the session API: round trip, gating, scorecard."""
import warnings

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _make_session() -> str:
    r = client.post("/session", json={
        "width": 25, "height": 25, "number_of_agents": 2,
        "seed": 42, "max_num_cities": 2,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_weights_round_trip_validation_and_unknown_session():
    sid = _make_session()
    r = client.get(f"/session/{sid}/director")
    assert r.status_code == 200
    body = r.json()
    assert body["weights"] == {
        "punctuality": 1.0, "connections": 1.0, "stability": 1.0}
    assert body["plan"] is None  # nothing planned yet

    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": 2, "connections": 0, "stability": 1})
    assert r.status_code == 200, r.text
    r = client.get(f"/session/{sid}/director")
    assert r.json()["weights"] == {
        "punctuality": 2.0, "connections": 0.0, "stability": 1.0}

    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": -1, "connections": 1, "stability": 1})
    assert r.status_code == 400
    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": 0, "connections": 0, "stability": 0})
    assert r.status_code == 400

    assert client.get("/session/nope/director").status_code == 404
    assert client.post("/session/nope/director/weights", json={
        "punctuality": 1, "connections": 1, "stability": 1,
    }).status_code == 404


def test_stepping_with_the_planner_fills_the_scorecard_and_sliders_replan():
    """The full Director flow: step under `goal_directed` → the plan's
    provenance appears; moving a dial mid-episode keeps the committed
    plan driving (a from-scratch re-plan would restart trains at their
    origins) and the next step re-plans *from the current state* under
    the new dials."""
    sid = _make_session()
    r = client.post(f"/session/{sid}/step", json={
        "n_steps": 2, "policy": "goal_directed"})
    assert r.status_code == 200, r.text

    body = client.get(f"/session/{sid}/director").json()
    plan = body["plan"]
    assert plan is not None
    assert isinstance(plan["source"], str)
    assert plan["weights"] == [1.0, 1.0, 1.0]

    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": 0, "connections": 0, "stability": 1})
    assert r.status_code == 200
    # Mid-episode the committed plan keeps driving until the re-plan.
    assert client.get(f"/session/{sid}/director").json()["plan"] is not None

    # The dirty flag starts a *background* re-plan on the next step; keep
    # stepping until its result lands (applied re-anchored to the live
    # state — the plan keeps driving meanwhile).
    import time

    deadline = time.time() + 15
    replans: list = []
    while time.time() < deadline and not replans:
        r = client.post(f"/session/{sid}/step", json={
            "n_steps": 1, "policy": "goal_directed"})
        assert r.status_code == 200, r.text
        plan = client.get(f"/session/{sid}/director").json()["plan"]
        replans = (plan or {}).get("replans") or []
        time.sleep(0.02)
    assert plan is not None
    assert plan["weights"] == [0.0, 0.0, 1.0]
    assert replans and replans[-1]["reason"] == "weights change"


def test_pushing_weights_with_plan_returns_the_fresh_plan_and_paths():
    """The map-overlay contract: `plan: true` makes the weights push plan
    (or mid-episode re-plan) immediately and hand back the plan plus
    drawable per-train paths — and the satisfied re-plan must not fire
    again on the next step."""
    sid = _make_session()
    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": 0, "connections": 0, "stability": 1, "plan": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["replanned"] is True
    assert body["plan"]["weights"] == [0.0, 0.0, 1.0]
    paths = body["paths"]
    assert paths and all(
        {"step", "row", "col"} <= set(point)
        for points in paths.values() for point in points
    )

    # Paths ride along on the scorecard poll as well.
    state = client.get(f"/session/{sid}/director").json()
    assert state["paths"] is not None

    # Mid-episode: the push re-plans from the current state, once.
    client.post(f"/session/{sid}/step", json={
        "n_steps": 2, "policy": "goal_directed"})
    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": 1, "connections": 1, "stability": 1, "plan": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["replanned"] is True
    replans = body["plan"].get("replans") or []
    assert len(replans) == 1 and replans[-1]["reason"] == "weights change"

    client.post(f"/session/{sid}/step", json={
        "n_steps": 1, "policy": "goal_directed"})
    plan = client.get(f"/session/{sid}/director").json()["plan"]
    assert len(plan.get("replans") or []) == 1


def test_pushing_weights_with_plan_drops_the_cached_scenario_forecasts():
    """A committed re-plan changes the future the trains will drive, so
    the scenario forecasts cached before it describe a stale course and
    must be invalidated by the push."""
    from app.core.scenario_cache import scenario_cache

    sid = _make_session()
    r = client.get(f"/session/{sid}/hmi/scenarios")
    assert r.status_code == 200, r.text
    assert any(key[0] == sid for key in scenario_cache._cache), (
        "the scenario fetch did not populate the cache"
    )

    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": 0, "connections": 1, "stability": 0, "plan": True})
    assert r.status_code == 200, r.text
    assert r.json()["replanned"] is True
    assert not any(key[0] == sid for key in scenario_cache._cache), (
        "the committed re-plan left stale scenario forecasts in the cache"
    )


def test_verification_replays_the_plan_without_touching_the_session():
    """Verify = ground truth from a pristine fork; the live session's
    step counter must not move, and without a plan it refuses."""
    sid = _make_session()
    assert client.post(f"/session/{sid}/director/verify").status_code == 400

    client.post(f"/session/{sid}/step", json={
        "n_steps": 2, "policy": "goal_directed"})
    before = client.get(f"/session/{sid}/state").json()

    r = client.post(f"/session/{sid}/director/verify")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["verified"]) >= {
        "total_delay", "all_arrived", "kept_ratio", "safety"}
    assert body["predicted"]["source"] is not None

    after = client.get(f"/session/{sid}/state").json()
    assert after["elapsed_steps"] == before["elapsed_steps"]
