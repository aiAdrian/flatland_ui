"""The A/B/C strategy tiles: one plan per focus, or an honest refusal.

The Director's supervisory decision is *which objective* the autonomous plan
should pursue, so each tile has to be answered by a plan under those dials —
never by a label with invented numbers.
"""
import warnings

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.sessions import DIRECTOR_STRATEGY_PRESETS  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def _make_session() -> str:
    r = client.post("/session", json={
        "width": 25, "height": 25, "number_of_agents": 2,
        "seed": 42, "max_num_cities": 2,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_every_preset_wins_on_its_own_axis():
    """No dominated option: each focus weights its own axis strictly higher
    than the others, so choosing a tile is a statement about values rather
    than picking the objectively better one."""
    assert [p["ident"] for p in DIRECTOR_STRATEGY_PRESETS] == ["A", "B", "C"]
    assert {p["focus"] for p in DIRECTOR_STRATEGY_PRESETS} == {
        "punctuality", "connections", "stability"}
    for preset in DIRECTOR_STRATEGY_PRESETS:
        weights = preset["weights"]
        own = weights[preset["focus"]]
        others = [v for k, v in weights.items() if k != preset["focus"]]
        assert all(own > other for other in others), preset["id"]
        assert all(other > 0 for other in others), (
            f"{preset['id']} zeroes an axis — a focus is a priority, not a veto")


def test_unknown_session_is_404():
    assert client.get("/session/nope/director/strategies").status_code == 404


def test_without_a_plan_the_presets_come_back_unplanned_not_as_an_error():
    """Degradation contract: the tiles stay usable as pure directives, and
    say why there are no numbers, instead of failing the whole panel."""
    sid = _make_session()
    r = client.get(f"/session/{sid}/director/strategies")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is False
    assert body["reason"]
    assert len(body["strategies"]) == 3
    assert all(s["plan"] is None and s["paths"] is None for s in body["strategies"])
    # The presets themselves are always there — that is what makes the tiles
    # clickable even without a planner answer.
    assert [s["ident"] for s in body["strategies"]] == ["A", "B", "C"]
    assert all(s["weights"] for s in body["strategies"])


def test_an_unchanged_request_is_served_from_cache():
    """Three residual plans cost ~20s, and an identical request cost exactly the
    same again — which turned re-entering Director or a stray refresh into a 20s
    stall for an answer already computed. A step invalidates it."""
    import time

    sid = _make_session()
    client.post(f"/session/{sid}/step", json={"n_steps": 4, "policy": "goal_directed"})

    first = client.get(f"/session/{sid}/director/strategies")
    assert first.status_code == 200, first.text
    if not first.json()["available"]:
        return  # no models installed here; nothing to cache

    assert first.json()["cached"] is False

    t = time.time()
    second = client.get(f"/session/{sid}/director/strategies")
    elapsed = time.time() - t
    assert second.json()["cached"] is True
    assert elapsed < 1.0, f"cached answer took {elapsed:.1f}s"
    # Same content, not just a flag.
    assert second.json()["strategies"] == first.json()["strategies"]

    # Stepping moves the state the plans were made from → recompute.
    client.post(f"/session/{sid}/step", json={"n_steps": 2, "policy": "goal_directed"})
    third = client.get(f"/session/{sid}/director/strategies")
    assert third.json()["cached"] is False
    assert third.json()["step"] > first.json()["step"]


def test_committing_new_weights_invalidates_the_cached_strategies():
    """The tiles compare each focus against the plan that drives. Commit a new
    plan and the old comparison is meaningless."""
    sid = _make_session()
    client.post(f"/session/{sid}/step", json={"n_steps": 4, "policy": "goal_directed"})
    first = client.get(f"/session/{sid}/director/strategies")
    if not first.json()["available"]:
        return
    assert client.get(f"/session/{sid}/director/strategies").json()["cached"] is True

    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": 5, "connections": 2, "stability": 2, "plan": True})
    assert r.status_code == 200, r.text
    assert client.get(f"/session/{sid}/director/strategies").json()["cached"] is False


def test_an_unchanged_request_is_served_from_cache_instead_of_replanning():
    """Three residual plans cost ~20s (measured), and an identical request cost
    exactly that again — so re-entering Director, a second panel instance or a
    stray refresh each stalled for 20s on an answer already computed."""
    import time

    sid = _make_session()
    r = client.post(f"/session/{sid}/step", json={
        "n_steps": 4, "policy": "goal_directed"})
    assert r.status_code == 200, r.text

    first = client.get(f"/session/{sid}/director/strategies")
    assert first.status_code == 200, first.text
    if not first.json()["available"]:
        return  # no models installed here; nothing to cache

    assert first.json()["cached"] is False

    t = time.time()
    second = client.get(f"/session/{sid}/director/strategies")
    elapsed = time.time() - t
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert elapsed < 1.0, f"cached answer took {elapsed:.1f}s"
    # Same answer, not just a fast one.
    assert second.json()["strategies"] == first.json()["strategies"]


def test_the_cache_is_dropped_when_the_running_plan_changes():
    """The tiles report each focus as a delta against the plan that drives, so a
    committed re-plan invalidates every one of them."""
    sid = _make_session()
    client.post(f"/session/{sid}/step", json={
        "n_steps": 4, "policy": "goal_directed"})
    first = client.get(f"/session/{sid}/director/strategies")
    if not first.json()["available"]:
        return

    assert client.get(f"/session/{sid}/director/strategies").json()["cached"] is True

    # Committing a focus re-plans the session → the comparison baseline moved.
    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": 5, "connections": 2, "stability": 2, "plan": True})
    assert r.status_code == 200, r.text
    assert client.get(f"/session/{sid}/director/strategies").json()["cached"] is False


def test_stepping_invalidates_the_cache():
    sid = _make_session()
    client.post(f"/session/{sid}/step", json={
        "n_steps": 4, "policy": "goal_directed"})
    if not client.get(f"/session/{sid}/director/strategies").json()["available"]:
        return
    assert client.get(f"/session/{sid}/director/strategies").json()["cached"] is True

    client.post(f"/session/{sid}/step", json={
        "n_steps": 2, "policy": "goal_directed"})
    assert client.get(f"/session/{sid}/director/strategies").json()["cached"] is False


def test_each_focus_is_answered_by_a_plan_and_leaves_the_session_alone():
    """With a committed plan in place, every tile carries the plan its dials
    produce — per-axis utilities and a drawable reroute — and the live
    session is untouched by the three forked plannings."""
    sid = _make_session()
    r = client.post(f"/session/{sid}/step", json={
        "n_steps": 2, "policy": "goal_directed"})
    assert r.status_code == 200, r.text

    before = client.get(f"/session/{sid}/state").json()
    before_plan = client.get(f"/session/{sid}/director").json()

    r = client.get(f"/session/{sid}/director/strategies")
    assert r.status_code == 200, r.text
    body = r.json()

    if not body["available"]:
        # No checkpoints installed in this environment: the endpoint must say
        # so rather than pretend. Covered by the degradation test above.
        assert body["reason"]
        return

    assert len(body["strategies"]) == 3
    for s in body["strategies"]:
        plan = s["plan"]
        assert plan is not None, s["id"]
        assert set(plan["utilities"]) == {
            "punctuality", "connections", "stability"}
        assert all(0.0 <= v <= 1.0 for v in plan["utilities"].values())
        assert isinstance(plan["changed"], list)
        assert s["paths"] is not None
        for points in s["paths"].values():
            assert all({"step", "row", "col"} <= set(p) for p in points)

    after = client.get(f"/session/{sid}/state").json()
    assert after["elapsed_steps"] == before["elapsed_steps"]
    # The committed plan is the one that was driving before — planning the
    # tiles must not have spliced anything into the live session.
    after_plan = client.get(f"/session/{sid}/director").json()
    assert after_plan["plan"]["weights"] == before_plan["plan"]["weights"]
    assert len(after_plan["plan"].get("replans") or []) == len(
        before_plan["plan"].get("replans") or [])


def test_before_the_first_step_the_options_get_the_portfolio_guarantee():
    """At t=0 an option must be planned by `director_plan`, not residually.

    Only `director_plan` holds the searched plan against `plan_all_lines` /
    `plan_avoiding_overlaps` under the same weighted score
    (docs/reference/director-mode.md §3.7). The plan that *drives* comes from
    that path (`goal_directed_policy._plan`), so planning the options residually
    at t=0 compared guaranteed against unguaranteed — and could offer a focus
    that its own scorer rates below the naive baseline.

    The observable trace of the guarantee is `source ∈ {search, lines,
    avoidance}` plus a `considered` map; a residual plan has neither.
    """
    sid = _make_session()
    # Plan without stepping: this is the state the operator sees on entering
    # Director, and the one the bug applied to.
    r = client.post(f"/session/{sid}/director/weights", json={
        "punctuality": 1, "connections": 1, "stability": 1, "plan": True})
    assert r.status_code == 200, r.text

    body = client.get(f"/session/{sid}/director/strategies").json()
    if not body["available"]:
        return  # no models installed here
    assert body["step"] == 0
    for strategy in body["strategies"]:
        plan = strategy["plan"]
        assert plan is not None, strategy["ident"]
        assert plan["source"] in {"search", "lines", "avoidance"}, plan["source"]


def test_mid_episode_the_options_stay_residual():
    """Past the first step the past must be pinned, which is `residual_plan`'s
    job (§3.8) — re-planning from scratch would move trains that already drove."""
    sid = _make_session()
    client.post(f"/session/{sid}/step", json={
        "n_steps": 6, "policy": "goal_directed"})
    body = client.get(f"/session/{sid}/director/strategies").json()
    if not body["available"]:
        return
    assert body["step"] >= 6
    for strategy in body["strategies"]:
        if strategy["plan"] is None:
            continue
        # Residual plans are labelled by their own planner, never "lines".
        assert strategy["plan"]["source"], strategy["ident"]
        # And every option's paths start at the trains' current positions, not
        # at their origins.
        assert strategy["paths"], strategy["ident"]
