"""Director re-planning over the session API: manual re-plan and what-if forks."""
import warnings

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

WEIGHTS = {"punctuality": 1, "connections": 1, "stability": 1}


def _make_session() -> str:
    r = client.post("/session", json={
        "width": 25, "height": 25, "number_of_agents": 2,
        "seed": 42, "max_num_cities": 2,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _step(sid: str, n: int) -> None:
    r = client.post(f"/session/{sid}/step", json={
        "n_steps": n, "policy": "goal_directed"})
    assert r.status_code == 200, r.text


def test_replan_and_whatif_refuse_without_a_committed_plan():
    sid = _make_session()
    assert client.post(f"/session/{sid}/director/replan").status_code == 400
    assert client.post(
        f"/session/{sid}/director/whatif", json=WEIGHTS).status_code == 400
    assert client.post("/session/nope/director/replan").status_code == 404
    assert client.post(
        "/session/nope/director/whatif", json=WEIGHTS).status_code == 404


def test_manual_replan_records_an_event_and_leaves_the_episode_alone():
    sid = _make_session()
    _step(sid, 2)
    before = client.get(f"/session/{sid}/state").json()

    r = client.post(f"/session/{sid}/director/replan")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event"]["reason"] == "manual"
    assert body["event"]["source"] in ("research", "continue")
    replans = body["plan"].get("replans") or []
    assert replans and replans[-1] == body["event"]

    after = client.get(f"/session/{sid}/state").json()
    assert after["elapsed_steps"] == before["elapsed_steps"]


def test_play_drives_director_mode_with_the_director_policy():
    """/play gates on the control-policy set (like /step and /policy), not
    the scenario set. goal_directed is control-enabled but not
    scenario-capable — gating on the scenario set rejected it, and the
    frontend's recovery then silently switched a running Director session
    back to deadlock avoidance."""
    sid = _make_session()
    r = client.post(f"/session/{sid}/policy", json={"policy": "goal_directed"})
    assert r.status_code == 200, r.text

    r = client.post(f"/session/{sid}/play",
                    json={"policy": "goal_directed", "speed": 20})
    assert r.status_code == 200, r.text
    assert r.json()["policy"] == "goal_directed"
    r = client.post(f"/session/{sid}/pause")
    assert r.status_code == 200, r.text

    # The gate itself must survive: hidden policies stay unplayable.
    r = client.post(f"/session/{sid}/play", json={"policy": "do_nothing"})
    assert r.status_code == 400


def test_scenario_rollouts_use_the_director_plan_as_baseline():
    """In Director mode the trains follow the committed Director plan —
    so the scenario baseline must roll out *that plan*, never a proxy
    policy. The alternatives stay what-ifs about switching away."""
    sid = _make_session()
    _step(sid, 3)
    r = client.post(f"/session/{sid}/policy", json={"policy": "goal_directed"})
    assert r.status_code == 200, r.text

    r = client.get(f"/session/{sid}/hmi/scenarios")
    assert r.status_code == 200, r.text
    scenarios = r.json()
    baseline = [s for s in scenarios if s.get("isBaseline")]
    assert len(baseline) == 1
    assert baseline[0]["id"] == "scn_goal_directed"
    # The old bug: goal_directed is not scenario-capable, so the baseline
    # silently fell back to deadlock avoidance.
    assert all(
        s["id"] != "scn_deadlock_avoidance" or not s.get("isBaseline")
        for s in scenarios
    )
    assert client.get(
        f"/session/{sid}/hmi/recommendations").status_code == 200


def test_whatif_compares_both_branches_without_touching_the_session():
    sid = _make_session()
    _step(sid, 3)
    before = client.get(f"/session/{sid}/state").json()

    r = client.post(f"/session/{sid}/director/whatif", json={
        "punctuality": 0, "connections": 0, "stability": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["step"] == before["elapsed_steps"]
    for branch in ("continue", "replan"):
        outcome = body[branch]
        assert set(outcome) >= {
            "total_delay", "arrived", "trains", "all_arrived", "steps",
            "connections_total", "connections_kept", "kept_ratio",
        }
        assert outcome["steps"] >= before["elapsed_steps"]
    assert body["replan"]["source"] in ("research", "continue")
    assert set(body["replan"]["predicted"]["considered"]) == {
        "research", "continue"}

    # Both forks ran to the episode's end; the live session must not move.
    after = client.get(f"/session/{sid}/state").json()
    assert after["elapsed_steps"] == before["elapsed_steps"]

    r = client.post(f"/session/{sid}/director/whatif", json={
        "punctuality": 0, "connections": 0, "stability": 0})
    assert r.status_code == 400


def test_override_whatif_under_director_follows_the_committed_plan(monkeypatch):
    """The override what-if's branches must roll out the committed Director
    plan, not a proxy policy — so the endpoint has to consult the Director
    replay factory and get a real factory back."""
    import app.policies.goal_directed_policy as goal_directed_policy

    sid = _make_session()
    _step(sid, 3)
    r = client.post(f"/session/{sid}/policy", json={"policy": "goal_directed"})
    assert r.status_code == 200, r.text

    real = goal_directed_policy.director_replay_factory
    factories: list = []

    def recording(env):
        factory = real(env)
        factories.append(factory)
        return factory

    monkeypatch.setattr(
        goal_directed_policy, "director_replay_factory", recording)

    r = client.post(f"/session/{sid}/what-if-override",
                    json={"overrides": {0: 4}})
    assert r.status_code == 200, r.text
    assert factories, (
        "the override what-if never consulted the Director replay factory"
    )
    assert factories[-1] is not None, (
        "no committed plan to replay — the what-if fell back to a proxy policy"
    )
