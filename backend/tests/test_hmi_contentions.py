"""End-to-end tests for GET /{session_id}/hmi/contentions.

The endpoint is the backend half of widget E1's "packages from live
conflicts": it runs a no-override forecast branch and returns the
multi-agent contentions ahead, grouped, most-urgent first, plus the
forecast budget (`horizonSteps`) the panel states on screen. These tests
pin the contract the Combined Actions panel depends on:

  * a session with a real contention returns one group whose handles are all
    real session handles (the defect fix — no phantoms);
  * a conflict-free session returns empty groups (never an error, never a
    synthesised package to fill the panel) — and still states its horizon;
  * single-train kinds are filtered out;
  * multiple events for the same contention collapse into one group;
  * a forecast failure stays empty and never raises;
  * the horizon budget is always present, so the panel can state its lookahead
    regardless of whether this step found a contention;
  * 404 for an unknown session.
"""
import warnings
warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# The forecast budget the endpoint runs with — what it returns as
# `horizonSteps`. Pinned here so a change to the constant surfaces as a test
# failure, not silently on the panel.
from app.api.hmi import _CONTENTION_MAX_STEPS


def _make_pfch_session() -> str:
    r = client.post("/session", json={
        "scenario_preset_id": "pf-ch-wn-wal-conflict",
        "seed": 42,
        "enabled_policy_ids": ["deadlock_avoidance"],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _make_simple_session(num_agents: int = 2) -> str:
    r = client.post("/session", json={
        "width": 25, "height": 25, "number_of_agents": num_agents,
        "seed": 42, "max_num_cities": 2,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _drive(sid: str, steps: int, policy: str = "deadlock_avoidance"):
    r = client.post(f"/session/{sid}/step", json={"n_steps": steps, "policy": policy})
    assert r.status_code == 200, r.text
    return r.json()


def _groups(resp) -> list:
    """Extract the groups list from the wrapper response and pin its shape."""
    body = resp.json()
    assert isinstance(body, dict), f"expected wrapper object, got {type(body)}"
    assert set(body.keys()) == {"horizonSteps", "groups"}, f"unexpected keys: {body.keys()}"
    return body["groups"]


def _horizon(resp) -> int:
    return resp.json()["horizonSteps"]


def test_contentions_returns_real_handles_for_pf_ch_conflict():
    """The PF–CH single-track conflict: three trains contend for the Wal
    line. The endpoint must return a group naming all three real handles —
    that is what makes every chip on every Combined Actions card resolve to
    a train actually in the session."""
    sid = _make_pfch_session()
    _drive(sid, 8)

    r = client.get(f"/session/{sid}/hmi/contentions")
    assert r.status_code == 200, r.text
    groups = _groups(r)
    assert groups, "PF–CH conflict produced no contentions — fixture or detector regressed"

    # Exactly one contention group: the three blocked events (one per stopped
    # train) collapse into a single group by shared handles.
    assert len(groups) == 1, f"expected 1 contention group, got {len(groups)}: {groups}"
    g = groups[0]
    assert set(g["handles"]) == {0, 1, 2}
    assert g["kind"] in ("blocked", "swap_attempt", "deadlock_cycle")
    # Every handle is a real session handle (0..2) — no phantoms.
    assert all(0 <= h <= 2 for h in g["handles"])
    # Most-urgent first is trivially satisfied with one group; pin the shape.
    assert isinstance(g["step"], int) and g["step"] >= 0
    assert g["position"] is None or (isinstance(g["position"], list) and len(g["position"]) == 2)


def test_contentions_empty_for_conflict_free_session():
    """A session that cannot contend returns empty groups — the panel keeps its
    empty state and never synthesises a package to fill. The horizon budget is
    still present, so the panel can state its lookahead even with nothing ahead.

    One agent, deliberately: a contention needs two handles by definition, so
    this premise holds by construction. With two agents it did not — the
    forecast looks `_CONTENTION_MAX_STEPS` into the *future*, and two trains on
    a small generated map often do meet in it, which made this test fail about
    one run in five while asserting nothing the endpoint controls."""
    sid = _make_simple_session(num_agents=1)
    r = client.get(f"/session/{sid}/hmi/contentions")
    assert r.status_code == 200, r.text
    assert _groups(r) == []
    assert _horizon(r) == _CONTENTION_MAX_STEPS


def test_contentions_single_train_kinds_filtered_out():
    """malfunction / agent_done / overdue_arrival are single-train events
    and must never appear as contentions. The PF–CH run above only emits
    `blocked`, so assert directly that no group carries a single-train kind
    and that every group has >= 2 handles."""
    sid = _make_pfch_session()
    _drive(sid, 8)
    r = client.get(f"/session/{sid}/hmi/contentions")
    assert r.status_code == 200, r.text
    for g in _groups(r):
        assert g["kind"] in ("blocked", "swap_attempt", "deadlock_cycle")
        assert len(g["handles"]) >= 2


def test_contentions_memoised_within_step():
    """Two calls within the same step return the same payload without
    re-running the forecast (the cheap-poll guarantee). Drive to a step with
    a contention, call twice, assert equal."""
    sid = _make_pfch_session()
    _drive(sid, 8)
    a = client.get(f"/session/{sid}/hmi/contentions").json()
    b = client.get(f"/session/{sid}/hmi/contentions").json()
    assert a == b
    assert a["groups"]  # non-empty


def test_contentions_404_for_unknown_session():
    r = client.get("/session/does-not-exist/hmi/contentions")
    assert r.status_code == 404


def test_contentions_groups_sorted_most_urgent_first():
    """When several distinct contentions exist, the lowest-step group comes
    first. Two unrelated contentions are hard to stage deterministically on
    the sparse generator, so this asserts the sort contract on the step
    field directly: groups are non-decreasing in step."""
    sid = _make_pfch_session()
    _drive(sid, 8)
    groups = _groups(client.get(f"/session/{sid}/hmi/contentions"))
    steps = [g["step"] for g in groups]
    assert steps == sorted(steps)


def test_contentions_always_states_its_horizon():
    """The forecast budget (`horizonSteps`) is returned whether or not a
    contention was found, so the panel can state its lookahead in minutes
    via the shared `MINUTES_PER_STEP` convention regardless of the result.
    This is the Q2 fix: the lookahead is visible, not an invisible parameter
    that changes the figure on screen."""
    # Conflict-free: horizon still present.
    sid_free = _make_simple_session(num_agents=2)
    assert _horizon(client.get(f"/session/{sid_free}/hmi/contentions")) == _CONTENTION_MAX_STEPS

    # Contention found: same horizon.
    sid_pfch = _make_pfch_session()
    _drive(sid_pfch, 8)
    assert _horizon(client.get(f"/session/{sid_pfch}/hmi/contentions")) == _CONTENTION_MAX_STEPS


def test_group_contentions_merges_transitive_chain():
    """Conflicts that only share a handle *transitively* are one contention.

    A stalled queue emits one event per stopped train, and two of them can name
    disjoint pairs that a third one joins. Grouping while the unions are still
    being made keyed the first two by roots that went stale, so the contention
    split across several groups — with the shared train in each of them, which
    is what the grouping exists to prevent.
    """
    from app.api.hmi import _group_contentions
    from app.core.conflict_detector import Conflict

    groups = _group_contentions([
        Conflict(kind="blocked", step=10, agents=[0, 1], position=(2, 50)),
        Conflict(kind="blocked", step=11, agents=[2, 3], position=(2, 60)),
        Conflict(kind="blocked", step=12, agents=[1, 2], position=(2, 55)),
    ])

    assert len(groups) == 1
    assert groups[0]["handles"] == [0, 1, 2, 3]
    assert groups[0]["step"] == 10, "the group carries its earliest conflict"


def test_group_contentions_keeps_unrelated_contentions_apart():
    """Merging must not go the other way: two contentions sharing no train
    stay two groups, most-urgent first."""
    from app.api.hmi import _group_contentions
    from app.core.conflict_detector import Conflict

    groups = _group_contentions([
        Conflict(kind="blocked", step=20, agents=[7, 8], position=(2, 90)),
        Conflict(kind="blocked", step=10, agents=[0, 1], position=(2, 50)),
    ])

    assert [g["handles"] for g in groups] == [[0, 1], [7, 8]]


def test_contention_cache_released_when_the_session_goes():
    """A deleted session leaves nothing behind.

    The cache's own `put()` only drops stale *steps* of the same session, so
    without an explicit release a session's last forecast stayed for the life
    of the process — small per session, unbounded across a long-running server.
    """
    from app.core.contention_cache import contention_cache

    sid = _make_simple_session(num_agents=1)
    client.get(f"/session/{sid}/hmi/contentions")
    assert any(k[0] == sid for k in contention_cache._cache), "nothing was cached to release"

    client.delete(f"/session/{sid}")
    assert not any(k[0] == sid for k in contention_cache._cache)


def test_contention_cache_dropped_when_the_driving_policy_changes():
    """A policy switch invalidates the forecast, even within the same step.

    The cache keys on (session_id, step) alone, and the forecast's baseline is
    whatever drives the session (`_rollout_baseline`). Switching policy without
    stepping would otherwise serve a prediction made under the old one — the
    same reason `_invalidate_scenario_forecasts` exists for the scenario cache.
    Override changes deliberately do *not* invalidate it: the predicted course
    ignores operator overrides by design.
    """
    from app.core.contention_cache import contention_cache

    sid = _make_simple_session(num_agents=1)
    client.get(f"/session/{sid}/hmi/contentions")
    assert any(k[0] == sid for k in contention_cache._cache)

    r = client.post(f"/session/{sid}/policy", json={"policy": "deadlock_avoidance"})
    assert r.status_code == 200, r.text
    assert not any(k[0] == sid for k in contention_cache._cache)
