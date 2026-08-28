"""Tests for the additive per-handle enrichment of GET /hmi/contentions.

Task 1 derives four quantities — baselineOrder, headway, entryDelay, slack —
all from the one forecast `result` the endpoint already produces (no second
run_branch). Task 2 carries them on the existing payload additively
(`handles` unchanged). These tests pin both:

  * the four quantities are derived on pf-ch-corridor-stops (the only preset
    where trains carry intermediate stops, against which slack is measurable);
  * a quantity not derivable in the horizon is null + unavailable_reason,
    never a silent zero;
  * `handles` is unchanged so the existing variant keeps working;
  * `location` is a station name where the window overlaps one, else the cell
    — never invented;
  * entryDelay matches the serializer.py formula (agent_outcomes is the
    source, not a re-derivation);
  * train names stay frontend — handles are returned as `agentHandle`.

The derivation helpers are also driven directly with synthetic inputs, so the
window/location/null-path contracts are pinned deterministically rather than
seed-waiting for a station to fall inside a contention window.
"""
import warnings
warnings.filterwarnings("ignore")

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _make_corridor_stops_session() -> str:
    r = client.post("/session", json={
        "scenario_preset_id": "pf-ch-corridor-stops",
        "seed": 42,
        "enabled_policy_ids": ["deadlock_avoidance"],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _drive(sid: str, steps: int, policy: str = "deadlock_avoidance"):
    r = client.post(f"/session/{sid}/step", json={"n_steps": steps, "policy": policy})
    assert r.status_code == 200, r.text


# ── additive payload (criterion 2.1: handles unchanged) ────────────


def test_handles_unchanged_additive_enrichment():
    """`handles` stays a plain list of ints; the enrichment rides alongside
    in `perHandle`. The existing Combined Actions variant reads `handles`
    alone, so it must keep working without noticing the new fields."""
    sid = _make_corridor_stops_session()
    _drive(sid, 15)
    r = client.get(f"/session/{sid}/hmi/contentions")
    assert r.status_code == 200, r.text
    groups = r.json()["groups"]
    assert groups, "corridor-stops produced no contentions — fixture regressed"
    for g in groups:
        assert isinstance(g["handles"], list)
        assert all(isinstance(h, int) for h in g["handles"])
        # The additive fields are present alongside, not replacing handles.
        assert "window" in g and "location" in g and "perHandle" in g
        assert set(g.keys()) >= {"step", "position", "kind", "handles", "window", "location", "perHandle"}


# ── the four quantities on corridor-stops (criterion 2.2) ───────────


def test_four_quantities_derived_on_corridor_stops():
    """The four quantities are derived for every handle in a contention group,
    all from the one forecast result — no second run_branch."""
    sid = _make_corridor_stops_session()
    _drive(sid, 15)
    groups = client.get(f"/session/{sid}/hmi/contentions").json()["groups"]
    assert groups
    g = groups[0]
    assert len(g["perHandle"]) == len(g["handles"])
    for p in g["perHandle"]:
        assert set(p.keys()) == {"agentHandle", "baselineOrder", "headway", "entryDelay", "slack"}
        # agentHandle, not a service name — train names stay frontend.
        assert isinstance(p["agentHandle"], int)
        for q in ("baselineOrder", "headway", "entryDelay", "slack"):
            assert set(p[q].keys()) == {"value", "unavailable_reason"}
    # At least one handle has a fully-derivable set (the contention's trains
    # do enter the window in the horizon — that's what makes them contenders).
    full = [p for p in g["perHandle"] if p["baselineOrder"]["value"] is not None]
    assert full, "no handle entered the window — window derivation regressed"
    p = full[0]
    assert isinstance(p["baselineOrder"]["value"], int)
    assert isinstance(p["headway"]["value"], int) and p["headway"]["value"] >= 0
    assert isinstance(p["entryDelay"]["value"], int) and p["entryDelay"]["value"] >= 0


def test_null_path_when_handle_never_enters_window():
    """A handle that never enters a window cell in the horizon gets null +
    unavailable_reason for baselineOrder AND headway — never a silent zero. A
    fabricated zero is worse than a missing field (criterion: no silent zeros)."""
    sid = _make_corridor_stops_session()
    _drive(sid, 15)
    groups = client.get(f"/session/{sid}/hmi/contentions").json()["groups"]
    g = groups[0]
    # corridor-stops contention is broad; at least one contending handle
    # does not reach the window cell set in 50 steps.
    never = [p for p in g["perHandle"] if p["baselineOrder"]["value"] is None]
    if never:
        for p in never:
            assert p["baselineOrder"] == {"value": None, "unavailable_reason": "never_enters_window"}
            assert p["headway"] == {"value": None, "unavailable_reason": "never_enters_window"}
    # And the reason is always carried when a value is null — no bare nulls.
    for p in g["perHandle"]:
        for q in ("baselineOrder", "headway", "entryDelay", "slack"):
            if p[q]["value"] is None:
                assert p[q]["unavailable_reason"] is not None, "null value without a reason"


def test_entry_delay_matches_serializer_formula():
    """entryDelay reuses the serializer.py formula via agent_outcomes — not a
    re-derivation. Cross-check a handle's value against the same formula
    computed from the live env."""
    from app.core.session_manager import session_manager

    sid = _make_corridor_stops_session()
    _drive(sid, 15)
    sess = session_manager.get(sid)
    env = sess.env
    elapsed = int(getattr(env, "_elapsed_steps", 0))
    groups = client.get(f"/session/{sid}/hmi/contentions").json()["groups"]
    g = groups[0]
    for p in g["perHandle"]:
        h = p["agentHandle"]
        a = env.agents[h]
        latest = getattr(a, "latest_arrival", None)
        latest = int(latest) if latest is not None else None
        expected = (elapsed - latest) if (latest is not None and elapsed > latest) else 0
        assert p["entryDelay"]["value"] == max(0, expected), (
            f"h{h} entryDelay {p['entryDelay']['value']} != serializer formula {max(0, expected)}"
        )


# ── location: station where known, else cell, never invented ────────


def test_location_kind_is_station_or_cell():
    """Every group's location is `station` or `cell` (or `none` for an empty
    window); never a fabricated name."""
    sid = _make_corridor_stops_session()
    _drive(sid, 15)
    for g in client.get(f"/session/{sid}/hmi/contentions").json()["groups"]:
        loc = g["location"]
        assert loc["kind"] in ("station", "cell", "none")
        if loc["kind"] == "station":
            assert isinstance(loc["name"], str) and loc["name"]
            assert isinstance(loc["cell"], list) and len(loc["cell"]) == 2
        elif loc["kind"] == "cell":
            assert loc["name"] is None
            assert isinstance(loc["cell"], list) and len(loc["cell"]) == 2
        else:
            assert loc["name"] is None and loc["cell"] is None


def test_location_for_helper_station_and_cell():
    """Drive the helper directly so the station-vs-cell contract is pinned
    deterministically, not seed-waiting for a station to fall in a window."""
    from app.api.hmi import _location_for

    # Window cell that is a named station → station location.
    labels = {(0, 17): "SIB 1", (2, 28): "SCBU 2"}
    loc = _location_for([(0, 17)], labels)
    assert loc == {"kind": "station", "name": "SIB 1", "cell": [0, 17]}

    # Window cell with no station → cell location, name None (never invented).
    loc = _location_for([(5, 99)], labels)
    assert loc == {"kind": "cell", "name": None, "cell": [5, 99]}

    # Empty window → none.
    assert _location_for([], labels) == {"kind": "none", "name": None, "cell": None}


# ── enrichment helpers, synthetic (deterministic null-path + slack) ──


def test_enrich_handles_null_path_and_slack_reasons():
    """The enrichment, driven directly with synthetic snapshots/outcomes, so
    the null-path and slack-reason contracts don't depend on a particular seed."""
    from app.api.hmi import _enrich_handles

    # Real BranchResult.snapshots are dicts ({step, agents: {h: {pos}}});
    # the fakes mirror that shape exactly.
    def _snap(step, positions):
        return {"step": step, "agents": {h: {"pos": p} for h, p in positions.items()}}

    class _Result:
        snapshots = [_snap(10, {0: (2, 5), 1: (9, 9)}),
                     _snap(12, {0: (2, 5), 1: (9, 9)}),
                     _snap(14, {0: (2, 6), 1: (9, 9)})]
        agent_outcomes = {0: {"delay": 4}, 1: {"delay": 0}}

    class _Wp:
        def __init__(self, pos):
            self.position = pos

    class _Ag:
        def __init__(self, wps, wlas):
            self.waypoints = wps
            self.waypoints_latest_arrival = wlas

    class _Env:
        agents = [_Ag([[_Wp((2, 5))]], [40]),     # h0: nearest wp has latest 40
                  _Ag([[_Wp((9, 9))]], [None])]   # h1: nearest wp has no latest

    window = [(2, 5)]
    env = _Env()
    out = _enrich_handles([0, 1], window, _Result(), env, elapsed=20)

    # h0 enters the window [(2,5)] at step 10 and is last present there at
    # step 12 (step 14 it has moved to (2,6), outside the window) → headway 2.
    assert out[0]["baselineOrder"] == {"value": 10, "unavailable_reason": None}
    assert out[0]["headway"] == {"value": 2, "unavailable_reason": None}
    assert out[0]["entryDelay"] == {"value": 4, "unavailable_reason": None}
    # slack = latest(40) - elapsed(20) = 20, at the waypoint nearest (2,5).
    assert out[0]["slack"] == {"value": 20, "unavailable_reason": None}

    # h1 never enters the window → null + reason on both, never a silent zero.
    assert out[1]["baselineOrder"] == {"value": None, "unavailable_reason": "never_enters_window"}
    assert out[1]["headway"] == {"value": None, "unavailable_reason": "never_enters_window"}
    # h1's nearest waypoint has no latest_arrival → slack null + reason.
    assert out[1]["slack"] == {"value": None, "unavailable_reason": "no_latest_arrival"}


def test_slack_no_waypoints_reason():
    """An agent without waypoints gets slack null with a named reason — the
    generated-env case (waypoints absent)."""
    from app.api.hmi import _enrich_handles

    class _Result:
        snapshots = [{"step": 10, "agents": {0: {"pos": (2, 5)}}}]
        agent_outcomes = {0: {"delay": 0}}

    class _Ag:
        waypoints = None
        waypoints_latest_arrival = None

    class _Env:
        agents = [_Ag()]

    out = _enrich_handles([0], [(2, 5)], _Result(), _Env(), elapsed=5)
    assert out[0]["slack"] == {"value": None, "unavailable_reason": "no_waypoints"}


def test_window_is_contended_cells_union():
    """The window is the union of each conflict's contended_cells — the same
    path-overlap that defined the contention. A group with two blocked events
    whose windows differ still carries the union."""
    from app.api.hmi import _group_contentions
    from app.core.conflict_detector import Conflict

    conflicts = [
        Conflict(kind="blocked", step=10, agents=[0, 1], position=(2, 5),
                 info={"emitter": 0, "contended_cells": [[2, 5], [2, 6]]}),
        Conflict(kind="blocked", step=10, agents=[1, 2], position=(2, 7),
                 info={"emitter": 1, "contended_cells": [[2, 7]]}),
    ]
    groups = _group_contentions(conflicts)
    # All three share handle 1 transitively → one group, window = union.
    assert len(groups) == 1
    g = groups[0]
    assert g["window"] == [[2, 5], [2, 6], [2, 7]]
    assert g["handles"] == [0, 1, 2]