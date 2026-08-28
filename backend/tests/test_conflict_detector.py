"""Tests for ConflictDetectionCallbacks (R5).

These tests drive the callback directly (on_episode_start / on_episode_step /
on_episode_end) so the detection logic can be exercised deterministically
without depending on PolicyRunner's I/O.

Scope: only the three multi-agent kinds the contentions endpoint filters on
are wired — `blocked`, `swap_attempt`, `deadlock_cycle`. The single-train
kinds (`malfunction`, `agent_done`, `overdue_arrival`) are deliberate no-ops
here (served by `/hmi/impact` and the notifications feed instead); a test
below pins that scope so a future regression cannot silently turn them on.
"""
import warnings
warnings.filterwarnings("ignore")

from types import SimpleNamespace

import pytest
from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_env_action import RailEnvActions
from flatland.envs.rail_generators import sparse_rail_generator
from flatland.envs.step_utils.states import TrainState

from app.core.conflict_detector import Conflict, ConflictDetectionCallbacks


def _make_env(num_agents: int = 2, seed: int = 42) -> RailEnv:
    e = RailEnv(
        width=25, height=25, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


def _drive(env, detector, actions_per_step, steps: int):
    """Helper: emit on_episode_start, then steps × on_episode_step,
    then on_episode_end. Mirrors how PolicyRunner would invoke it."""
    detector.on_episode_start(env=env)
    for _ in range(steps):
        try:
            env.step(actions_per_step(env))
        except Exception as e:
            if "Episode is done" in str(e):
                break
            raise
        detector.on_episode_step(env=env)
    detector.on_episode_end(env=env)


# ── construction ────────────────────────────────────────────────────


def test_constructor_defaults():
    d = ConflictDetectionCallbacks()
    assert d.blocked_threshold == 3
    assert d.detect_deadlocks is True
    kpis = d.get_kpis()
    assert kpis["total_conflicts"] == 0
    assert kpis["num_snapshots"] == 0


def test_episode_start_takes_initial_snapshot():
    env = _make_env()
    d = ConflictDetectionCallbacks()
    d.on_episode_start(env=env)
    snaps = d.get_snapshots()
    assert len(snaps) == 1
    assert snaps[0]["step"] == 0
    assert set(snaps[0]["agents"].keys()) == set(range(len(env.agents)))


# ── snapshot consistency ────────────────────────────────────────────


def test_snapshots_grow_with_steps():
    env = _make_env()
    d = ConflictDetectionCallbacks()
    _drive(env, d,
           lambda e: {h: RailEnvActions.MOVE_FORWARD for h in e.get_agent_handles()},
           steps=5)
    assert len(d.get_snapshots()) >= 2
    steps = [s["step"] for s in d.get_snapshots()]
    assert steps == sorted(steps)


# ── scope: the single-train kinds stay off ──────────────────────────


def test_single_train_kinds_are_not_wired():
    """`malfunction`, `agent_done`, `overdue_arrival` are deliberately not
    detected here — they are single-train events served by /hmi/impact and
    the notifications feed. Pin that scope so a regression shows up as a
    real failure rather than as new events the endpoint would then drop."""
    env = _make_env(num_agents=2)
    d = ConflictDetectionCallbacks()
    _drive(env, d,
           lambda e: {h: RailEnvActions.MOVE_FORWARD for h in e.get_agent_handles()},
           steps=200)
    kinds = {c.kind for c in d.get_conflicts()}
    assert kinds.isdisjoint({"malfunction", "agent_done", "overdue_arrival"}), (
        f"single-train kinds unexpectedly emitted: {kinds & {'malfunction','agent_done','overdue_arrival'}}"
    )


# ── blocked detection ───────────────────────────────────────────────


def test_blocked_threshold_emits_event():
    """STOP_MOVING an on-map agent → it is STOPPED for >= threshold steps →
    one blocked event with consecutive_stops == threshold and a real
    position. Unlike the earlier skip-only version, this asserts the event
    actually fires: the detector is wired now."""
    env = _make_env(num_agents=2)
    # Drive forward until an agent is on the map.
    for _ in range(15):
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
        if any(a.position is not None for a in env.agents):
            break

    on_map = [h for h, a in enumerate(env.agents) if a.position is not None]
    assert on_map, "no agent reached the map within 15 steps — fixture regressed"

    d = ConflictDetectionCallbacks(blocked_threshold=3)
    d.on_episode_start(env=env)
    for _ in range(5):
        env.step({h: RailEnvActions.STOP_MOVING for h in env.get_agent_handles()})
        d.on_episode_step(env=env)
    d.on_episode_end(env=env)

    blocked = [c for c in d.get_conflicts() if c.kind == "blocked"]
    assert blocked, "STOP_MOVING an on-map agent produced no blocked event"
    for ev in blocked:
        assert ev.info["consecutive_stops"] == 3
        assert ev.position is not None
        assert ev.info["emitter"] in on_map


def test_blocked_emitted_once_per_emitter_per_streak():
    """An 8-step STOP_MOVING stall emits at most one blocked event per
    *emitting* train (the train whose streak crossed the threshold). Counts
    by `info.emitter`, not by handle-membership: with path-overlap
    contenders, a handle legitimately appears in its own event and in a
    contender's, so membership-counting would double-count a single stall."""
    env = _make_env(num_agents=2)
    for _ in range(15):
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
        if any(a.position is not None for a in env.agents):
            break
    assert [h for h, a in enumerate(env.agents) if a.position is not None], "no agent on map"

    d = ConflictDetectionCallbacks(blocked_threshold=3)
    d.on_episode_start(env=env)
    for _ in range(8):
        env.step({h: RailEnvActions.STOP_MOVING for h in env.get_agent_handles()})
        d.on_episode_step(env=env)
    d.on_episode_end(env=env)

    blocked = [c for c in d.get_conflicts() if c.kind == "blocked"]
    emissions: dict[int, int] = {}
    for ev in blocked:
        emissions[ev.info["emitter"]] = emissions.get(ev.info["emitter"], 0) + 1
    for handle, n in emissions.items():
        assert n == 1, f"emitter {handle} emitted {n} blocked events (expected 1)"


def test_blocked_resets_when_train_moves():
    """A stall, then movement, then a second stall emits two events — the
    reset-on-position-change is what lets a fresh stall re-fire. (State
    flicker without movement must NOT re-fire; that is covered implicitly
    by the once-per-streak test above, where STOPPED holds throughout.)"""
    env = _make_env(num_agents=2)
    for _ in range(15):
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
        if any(a.position is not None for a in env.agents):
            break
    on_map = [h for h, a in enumerate(env.agents) if a.position is not None]
    assert on_map

    d = ConflictDetectionCallbacks(blocked_threshold=3)
    d.on_episode_start(env=env)
    # First stall: 4 STOP_MOVING steps → 1 blocked event for the on-map agent.
    for _ in range(4):
        env.step({h: RailEnvActions.STOP_MOVING for h in env.get_agent_handles()})
        d.on_episode_step(env=env)
    # Move again so the stall genuinely ends (position changes).
    moved = False
    for _ in range(6):
        before = [tuple(a.position) if a.position else None for a in env.agents]
        env.step({h: RailEnvActions.MOVE_FORWARD for h in env.get_agent_handles()})
        d.on_episode_step(env=env)
        if [tuple(a.position) if a.position else None for a in env.agents] != before:
            moved = True
            break
    if not moved:
        pytest.skip("agent did not move on MOVE_FORWARD in this seed")
    # Second stall.
    for _ in range(4):
        env.step({h: RailEnvActions.STOP_MOVING for h in env.get_agent_handles()})
        d.on_episode_step(env=env)
    d.on_episode_end(env=env)

    blocked = [c for c in d.get_conflicts() if c.kind == "blocked"]
    # At least one event from each stall — i.e. >= 2 emissions total across
    # the on-map handles.
    assert len(blocked) >= 2, f"expected >=2 blocked events across two stalls, got {len(blocked)}"


# ── blocked contention: path-overlap contenders (the PF–CH fix) ─────


def test_blocked_contention_includes_path_overlap_contenders():
    """The defect this whole task fixes: on the PF–CH single-track conflict
    the three trains are NOT adjacent — they freeze 25 cells apart on a
    shared track segment. A blocked event whose `agents` only held the
    stopped train would be dropped by the endpoint's 2+-handles rule, and
    the widget would never show packages. Assert the contender set is found
    via remaining-path overlap so every blocked event carries all three."""
    from app.core.session_manager import session_manager
    from app.core.scenario_runner import TrajectoryBranchRunner
    from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy

    sess = session_manager.create(scenario_preset_id="pf-ch-wn-wal-conflict", seed=42)
    env = sess.env
    dla = DeadLockAvoidancePolicy()
    dla.reset(env)
    for _ in range(8):
        try:
            env.step(dla.act_many(env.get_agent_handles(), {h: env for h in env.get_agent_handles()}))
        except Exception as e:
            if "Episode is done" in str(e):
                break
            raise
        dla.end_step()

    runner = TrajectoryBranchRunner(env, DeadLockAvoidancePolicy)
    result = runner.run_branch(overrides={}, max_steps=50)

    blocked = [c for c in result.conflicts if c.kind == "blocked"]
    assert blocked, "PF–CH forecast produced no blocked events — fixture or detector regressed"
    # Every blocked event names all three session handles: the contention is
    # the whole Wal single-track queue, not a single stopped train.
    handles = {0, 1, 2}
    for ev in blocked:
        assert set(ev.agents) == handles, (
            f"blocked event agents {ev.agents} != all three contending handles {sorted(handles)}"
        )


# ── swap + deadlock helpers (deterministic, fake env) ───────────────


def _fake_agent(position, direction, state="MOVING"):
    """Minimal stand-in for a Flatland agent — `_wait_graph` / `_detect_swap`
    read only `.position`, `.direction` and `.state`."""
    state_obj = SimpleNamespace(name=state) if isinstance(state, str) else state
    return SimpleNamespace(position=position, direction=direction, state=state_obj)


def _fake_env(agents):
    return SimpleNamespace(agents=agents)


def test_swap_attempt_detects_mutual_face_to_face():
    """Two agents facing each other on adjacent cells (each in the other's
    front cell) → one swap_attempt event listing both. Built from fakes so
    the geometry is exact, not seed-dependent."""
    # Agent 0 at (5,5) facing EAST → front (5,6); agent 1 at (5,6) facing
    # WEST → front (5,5). Mutual face-to-face.
    env = _fake_env([
        _fake_agent((5, 5), 1),  # 0: EAST
        _fake_agent((5, 6), 3),  # 1: WEST
    ])
    d = ConflictDetectionCallbacks()
    # _detect_swap needs >=2 snapshots present; seed two identical ones.
    d.on_episode_start(env=env)
    d.on_episode_step(env=env)

    swaps = [c for c in d.get_conflicts() if c.kind == "swap_attempt"]
    assert len(swaps) == 1
    assert sorted(swaps[0].agents) == [0, 1]
    assert swaps[0].position is not None


def test_no_swap_when_only_one_side_blocked():
    """A faces B's cell but B faces away → not a swap, just a one-sided
    block. No swap_attempt event."""
    env = _fake_env([
        _fake_agent((5, 5), 1),  # 0: EAST, front (5,6)
        _fake_agent((5, 6), 1),  # 1: also EAST, front (5,7) — facing away
    ])
    d = ConflictDetectionCallbacks()
    d.on_episode_start(env=env)
    d.on_episode_step(env=env)
    swaps = [c for c in d.get_conflicts() if c.kind == "swap_attempt"]
    assert swaps == []


def test_scc_finder_finds_three_cycle_and_drops_pair():
    """`_sccs_of_size_ge(min_size=3)` finds a 3-cycle A→B→C→A and ignores
    a separate mutual pair (which swap_attempt owns). Also verify
    min_size=2 returns the pair too."""
    # 0→1→2→0 (3-cycle), 3↔4 (mutual pair).
    graph = {0: {1}, 1: {2}, 2: {0}, 3: {4}, 4: {3}}
    big = ConflictDetectionCallbacks._sccs_of_size_ge(graph, 3)
    assert big == [[0, 1, 2]]
    all_cycles = ConflictDetectionCallbacks._sccs_of_size_ge(graph, 2)
    assert sorted(map(tuple, all_cycles)) == [(0, 1, 2), (3, 4)]


def test_wait_graph_excludes_done_and_off_map():
    """Done / waiting / ready-to-depart agents and agents without a
    position take no part in the wait-graph — they hold no cell."""
    env = _fake_env([
        _fake_agent((5, 5), 1),                    # 0: on map, MOVING
        _fake_agent(None, 1),                      # 1: no position
        _fake_agent((5, 6), 3, state="DONE"),      # 2: DONE → excluded
    ])
    d = ConflictDetectionCallbacks()
    g = d._wait_graph(env)
    assert set(g.keys()) == {0}  # only the on-map, active agent
    assert g[0] == set()         # 2 is DONE so not counted as a blocker


# ── KPI shape ───────────────────────────────────────────────────────


def test_kpis_shape_matches_spec():
    env = _make_env()
    d = ConflictDetectionCallbacks()
    _drive(env, d,
           lambda e: {h: RailEnvActions.MOVE_FORWARD for h in e.get_agent_handles()},
           steps=10)
    kpis = d.get_kpis()
    for key in (
        "total_conflicts", "by_kind", "num_snapshots",
        "num_done", "num_overdue", "num_blocked_events",
        "num_swap_attempts", "num_deadlock_cycles", "num_malfunctions",
        "total_delay", "agents_with_conflicts",
    ):
        assert key in kpis, f"missing kpi: {key}"
    assert isinstance(kpis["by_kind"], dict)
    assert isinstance(kpis["agents_with_conflicts"], list)
    assert kpis["total_conflicts"] == sum(kpis["by_kind"].values())


# ── re-use the same instance ────────────────────────────────────────


def test_episode_start_resets_state():
    env = _make_env()
    d = ConflictDetectionCallbacks()
    _drive(env, d,
           lambda e: {h: RailEnvActions.MOVE_FORWARD for h in e.get_agent_handles()},
           steps=10)
    snaps_before = len(d.get_snapshots())
    assert snaps_before > 0

    env2 = _make_env(seed=7)
    d.on_episode_start(env=env2)
    assert len(d.get_snapshots()) == 1
    assert len(d.get_conflicts()) == 0
    _ = snaps_before  # unused, kept for clarity


# ── Conflict dataclass ──────────────────────────────────────────────


def test_conflict_to_dict_jsonable():
    c = Conflict(
        kind="blocked", step=5, agents=[0, 1],
        position=(3, 7), info={"consecutive_stops": 3, "emitter": 0},
    )
    d = c.to_dict()
    assert d["kind"] == "blocked"
    assert d["agents"] == [0, 1]
    assert d["position"] == [3, 7]
    assert d["info"]["consecutive_stops"] == 3
