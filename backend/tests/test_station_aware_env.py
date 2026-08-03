"""Retaining Flatland's city/platform grouping, which RailEnv discards."""
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from flatland.envs.persistence import RailEnvPersister  # noqa: E402
from flatland.envs.rail_env import RailEnv  # noqa: E402

from app.core.env_factory import create_env  # noqa: E402
from app.core.station_aware_env import (  # noqa: E402
    StationAwareRailEnv,
    fingerprint_grid,
    forget_station_hints,
    station_hints_for,
)
from app.policies.goal_based_policies.stations import (  # noqa: E402
    resolve_stations,
    stations_from_generator_hints,
)
from app.policies.goal_based_policies.visualization import build_demo_env  # noqa: E402


def _plain_env(seed=7, cities=3):
    """The same scenario built on stock RailEnv, for comparison."""
    import flatland.envs.line_generators as line_gen
    import flatland.envs.rail_generators as rail_gen
    import flatland.envs.timetable_generators as ttg

    env = RailEnv(
        width=40, height=40, number_of_agents=3, random_seed=seed,
        rail_generator=rail_gen.sparse_rail_generator(
            max_num_cities=cities, seed=seed, grid_mode=False,
            max_rails_between_cities=1, max_rail_pairs_in_city=1),
        line_generator=line_gen.sparse_line_generator(seed=seed),
        timetable_generator=ttg.timetable_generator,
    )
    env.reset()
    return env


# ── the grouping itself ──────────────────────────────────────────────

def test_stock_railenv_loses_the_grouping():
    """The premise: without the subclass there is nothing to read, which is
    why stations otherwise have to be guessed from train missions."""
    forget_station_hints()
    env = _plain_env()
    assert getattr(env, "station_hints", None) is None
    assert station_hints_for(env) is None


def test_subclass_keeps_the_generators_city_platform_grouping():
    env = build_demo_env(seed=7, width=40, height=40,
                         number_of_agents=3, max_num_cities=3)
    hints = station_hints_for(env)
    assert hints is not None
    assert set(hints) >= {"city_positions", "train_stations", "city_orientations"}

    train_stations = hints["train_stations"]
    assert len(train_stations) == len(hints["city_positions"])
    # Each city holds several platform cells, each with a track number.
    for city in train_stations:
        assert len(city) >= 2, "a city should have more than one platform"
        for cell, track in city:
            assert len(cell) == 2
            assert isinstance(int(track), int)


def test_subclass_does_not_change_the_environment_it_builds():
    """It only retains hints — the rail, agents and timetable must be
    identical to stock RailEnv for the same seed, or every earlier
    measurement would be invalidated."""
    forget_station_hints()
    plain = _plain_env(seed=7)
    aware = build_demo_env(seed=7, width=40, height=40,
                           number_of_agents=3, max_num_cities=3)

    assert np.array_equal(
        np.asarray(plain.rail.grid).astype(np.int64),
        np.asarray(aware.rail.grid).astype(np.int64),
    )
    assert len(plain.agents) == len(aware.agents)
    for a, b in zip(plain.agents, aware.agents):
        assert tuple(a.initial_position) == tuple(b.initial_position)
        assert tuple(a.target) == tuple(b.target)
        assert a.earliest_departure == b.earliest_departure
        assert a.latest_arrival == b.latest_arrival


# ── surviving the what-if fork ───────────────────────────────────────

def test_hints_survive_the_what_if_fork(tmp_path):
    """`scenario_runner` forks envs via RailEnvPersister.save -> load_new,
    which returns a *plain* RailEnv and drops the attribute. The grid is
    value-identical, so the registry must still resolve it."""
    env = build_demo_env(seed=11, width=40, height=40,
                         number_of_agents=3, max_num_cities=3)
    path = str(tmp_path / "forked.pkl")
    RailEnvPersister.save(env, path)
    forked, _ = RailEnvPersister.load_new(path)

    # The attribute really is gone — this is what the registry works around.
    assert type(forked) is RailEnv
    assert getattr(forked, "station_hints", None) is None

    assert station_hints_for(forked) == station_hints_for(env)


def test_fingerprint_ignores_dtype_but_not_content():
    """load_new rebuilds the grid as int64 from uint16, so the key must be
    taken on values; different networks must still not collide."""
    grid = np.arange(12, dtype=np.uint16).reshape(3, 4)
    assert fingerprint_grid(grid) == fingerprint_grid(grid.astype(np.int64))

    changed = grid.copy()
    changed[1, 1] += 1
    assert fingerprint_grid(changed) != fingerprint_grid(grid)
    # Same values, different shape is a different network.
    assert fingerprint_grid(grid.reshape(4, 3)) != fingerprint_grid(grid)
    assert fingerprint_grid(None) is None


def test_unknown_env_resolves_to_nothing_rather_than_guessing():
    forget_station_hints()
    assert station_hints_for(_plain_env(seed=21)) is None
    assert stations_from_generator_hints(_plain_env(seed=21)) == []


# ── what this buys the station list ──────────────────────────────────

def test_generated_stations_group_platforms_instead_of_splitting_them():
    """The point of the change: platforms of one city become one station,
    where the mission fallback produced one single-cell station each."""
    env = build_demo_env(seed=7, width=40, height=40,
                         number_of_agents=4, max_num_cities=3)
    stations = resolve_stations(env)

    assert all(s.source == "generator_hints" for s in stations), (
        f"expected generator hints to win, got "
        f"{sorted({s.source for s in stations})}"
    )
    assert any(len(s.stop_cells) > 1 for s in stations), (
        "no station has multiple platforms — the grouping was lost"
    )
    # Every station's cells are real rail, and no cell is claimed twice.
    seen = set()
    for station in stations:
        assert station.center is not None
        for cell in station.stop_cells:
            assert cell not in seen, f"{cell} claimed by two stations"
            seen.add(cell)

    # Every train's origin and target is covered by some station, which the
    # mission fallback guaranteed and this must not regress.
    for agent in env.agents:
        for cell in (tuple(agent.initial_position), tuple(agent.target)):
            assert cell in seen, f"{cell} is not served by any station"


def test_station_count_drops_because_platforms_merge():
    """Same env, so fewer stations with more cells each is exactly the
    intended change rather than lost information."""
    forget_station_hints()
    plain = _plain_env(seed=7)
    plain_stations = resolve_stations(plain)

    aware = build_demo_env(seed=7, width=40, height=40,
                           number_of_agents=3, max_num_cities=3)
    aware_stations = resolve_stations(aware)

    assert all(s.source == "missions" for s in plain_stations)
    assert len(aware_stations) < len(plain_stations)
    # No stop cell is lost in the merge.
    assert {c for s in plain_stations for c in s.stop_cells} <= {
        c for s in aware_stations for c in s.stop_cells
    }


# ── the live UI path ─────────────────────────────────────────────────

@pytest.mark.integration
def test_sessions_created_through_env_factory_are_station_aware():
    """The UI builds envs via create_env, so the grouping has to be there
    for session surfaces to use it."""
    env = create_env(
        width=40, height=40, number_of_agents=3, max_num_cities=3, seed=7
    )
    assert isinstance(env, StationAwareRailEnv)
    assert isinstance(env, RailEnv), "must stay usable everywhere RailEnv is"
    assert station_hints_for(env) is not None

    stations = resolve_stations(env)
    assert stations and any(len(s.stop_cells) > 1 for s in stations)
