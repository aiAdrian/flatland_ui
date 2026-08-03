"""Passenger connections, as the planned order of trains at a station.

A connection is passengers changing from one train to another at a station.
Rather than authoring transfer data that Flatland has no notion of, we read
it off the timetable that already exists: if the plan has train A at a city
before train B, passengers can change from A to B there, and the connection
is *kept* when the actual run still has A before B.

That makes the whole objective derivable from the premade plan:

- which trains call at which city comes from `agent.waypoints` — the UI's
  `env_factory` builds 4-stop lines (Flatland's own default is 2), and
  `stations.resolve_stations` is what groups a city's platform cells so two
  trains stopping on different platforms count as meeting;
- when they are planned to be there comes from
  `agent.waypoints_earliest_departure`.

Every pair of trains meeting at a city is a connection, not just
consecutive ones: with the trains at a city ordered t1 < t2 < t3, a
passenger can change t1->t2, t1->t3 and t2->t3, and a plan that reorders
t1 and t3 has broken a real transfer even though they are not adjacent.

Nothing here looks at a run. `planned_connections` describes what the plan
promises; comparing that against what a rollout delivered is separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from flatland.envs.rail_env import RailEnv

from app.policies.goal_based_policies.schedule import line_stops
from app.policies.goal_based_policies.stations import Station


@dataclass(frozen=True)
class StationCall:
    """One train's scheduled call at one station."""
    handle: int
    station_id: str
    cell: Tuple[int, int]
    stop_index: int      # position in the train's line, 0 = origin
    time: int            # planned time at the station, in steps
    from_departure: bool  # True: earliest departure. False: arrival fallback.


@dataclass(frozen=True)
class PlannedConnection:
    """Passengers changing from `feeder` to `connector` at a station.

    `feeder` is planned to be at the station before `connector`, so keeping
    the connection means keeping that order.
    """
    station_id: str
    feeder: int
    connector: int
    planned_gap: int     # steps between them in the plan, always > 0

    @property
    def pair(self) -> Tuple[int, int]:
        return (self.feeder, self.connector)


def _call_time(
    agent, stop_index: int, include_terminal: bool
) -> Optional[Tuple[int, bool]]:
    """Planned time at a stop, from `waypoints_earliest_departure`.

    Earliest departure is the quantity of interest — it is when the train is
    ready to leave, so it bounds when a passenger must have boarded. It is
    `None` at the final stop, where the train terminates rather than
    departing.

    `include_terminal` decides what happens there. The only other planned
    time at a terminus is `waypoints_latest_arrival`, which is a *deadline*,
    not an expected arrival: measured over generated lines it sits about
    3.3x later than departure-based times (median 289 vs 88), so mixing the
    two sorts every terminating train to the end of its terminus regardless
    of when it really gets there. Default is therefore to skip terminal
    calls rather than order them on an incomparable quantity; pass True to
    include them and accept that bias.
    """
    departures = getattr(agent, "waypoints_earliest_departure", None) or []
    if stop_index < len(departures) and departures[stop_index] is not None:
        return int(departures[stop_index]), True
    if not include_terminal:
        return None
    arrivals = getattr(agent, "waypoints_latest_arrival", None) or []
    if stop_index < len(arrivals) and arrivals[stop_index] is not None:
        return int(arrivals[stop_index]), False
    return None


def station_calls(
    env: RailEnv,
    stations: Sequence[Station],
    include_terminal: bool = False,
) -> List[StationCall]:
    """Every scheduled call at a station, across all trains.

    A call needs the stop to belong to a known station: the platform
    grouping is what makes two trains on different platforms of one city
    count as meeting. See `_call_time` for `include_terminal`.
    """
    cell_to_station: Dict[Tuple[int, int], str] = {
        cell: station.id for station in stations for cell in station.stop_cells
    }
    calls: List[StationCall] = []
    for handle in range(len(env.agents)):
        agent = env.agents[handle]
        for stop_index, cell in enumerate(line_stops(env, handle)):
            station_id = cell_to_station.get(cell)
            if station_id is None:
                continue
            timed = _call_time(agent, stop_index, include_terminal)
            if timed is None:
                continue
            time, from_departure = timed
            calls.append(StationCall(
                handle=handle,
                station_id=station_id,
                cell=cell,
                stop_index=stop_index,
                time=time,
                from_departure=from_departure,
            ))
    return calls


def planned_order(
    env: RailEnv,
    stations: Sequence[Station],
    include_terminal: bool = False,
) -> Dict[str, List[StationCall]]:
    """Per station, its calls ordered by planned time.

    Ties break on handle so the order is total and reproducible — two trains
    planned for the same step would otherwise order arbitrarily and make the
    connection set depend on iteration order.
    """
    order: Dict[str, List[StationCall]] = {}
    for call in station_calls(env, stations, include_terminal):
        order.setdefault(call.station_id, []).append(call)
    for calls in order.values():
        calls.sort(key=lambda c: (c.time, c.handle))
    return order


def planned_connections(
    env: RailEnv,
    stations: Sequence[Station],
    include_terminal: bool = False,
) -> List[PlannedConnection]:
    """Every train pair meeting at a station, feeder first.

    Pairs are all-to-all within a station rather than consecutive only (see
    the module docstring). Trains planned for the same step are not a
    connection in either direction: their order carries no information, so
    demanding one would label noise.
    """
    connections: List[PlannedConnection] = []
    for station_id, calls in planned_order(env, stations, include_terminal).items():
        for position, feeder in enumerate(calls):
            for connector in calls[position + 1:]:
                if connector.time == feeder.time:
                    continue
                connections.append(PlannedConnection(
                    station_id=station_id,
                    feeder=feeder.handle,
                    connector=connector.handle,
                    planned_gap=connector.time - feeder.time,
                ))
    return connections


@dataclass(frozen=True)
class ConnectionOutcome:
    """What became of one planned connection in an actual run."""
    connection: PlannedConnection
    kept: bool
    reason: str          # "kept" | "reordered" | "feeder_absent" | "connector_absent"
    feeder_time: Optional[int]
    connector_time: Optional[int]

    @property
    def observed_gap(self) -> Optional[int]:
        if self.feeder_time is None or self.connector_time is None:
            return None
        return self.connector_time - self.feeder_time


@dataclass(frozen=True)
class ConnectionReport:
    """Connections kept across a whole run."""
    outcomes: List[ConnectionOutcome]

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def kept(self) -> int:
        return sum(1 for o in self.outcomes if o.kept)

    @property
    def kept_ratio(self) -> float:
        """How likely a passenger is to get their connection.

        This is the label: kept connections over all planned ones. A train
        that never reaches the station counts against it exactly like a
        reordered one, because the passenger waiting to change there does
        not care *why* the train is missing — either way the connection is
        gone. Conditioning on "both trains showed up" would measure how
        tidily the dispatcher orders the trains that made it, which is not
        the passenger's experience.

        1.0 when nothing was planned: a scenario with no connections has
        broken none, and scoring it 0 would read as total failure.
        """
        return 1.0 if not self.outcomes else self.kept / len(self.outcomes)

    @property
    def served(self) -> int:
        """Connections where both trains actually called at the station.

        Diagnostic only — `kept_ratio` is the label. Useful for telling
        "the order was wrong" apart from "a train never came", which the
        `reasons()` breakdown spells out.
        """
        return sum(
            1 for o in self.outcomes
            if o.feeder_time is not None and o.connector_time is not None
        )

    def reasons(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for outcome in self.outcomes:
            counts[outcome.reason] = counts.get(outcome.reason, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, object]:
        return {
            "total": self.total,
            "kept": self.kept,
            "served": self.served,
            "kept_ratio": self.kept_ratio,
            "reasons": self.reasons(),
        }


def observed_times(
    stations: Sequence[Station],
    occupancy: Dict[int, Dict[Tuple[int, int], Tuple[int, int]]],
) -> Dict[Tuple[int, str], int]:
    """`(handle, station_id) -> the step the train last stood at that station`.

    The *last* step, because the planned side is an earliest departure: the
    comparable moment in a run is when the train is finished there and ready
    to leave, not when it rolled in. A train that used several of a
    station's platforms counts as one call spanning all of them.

    Trains that never reached a station are simply absent, which is what
    distinguishes a reordered connection from an unserved one.
    """
    cell_to_station: Dict[Tuple[int, int], str] = {
        cell: station.id for station in stations for cell in station.stop_cells
    }
    times: Dict[Tuple[int, str], int] = {}
    for handle, cells in occupancy.items():
        for cell, (_first, last) in cells.items():
            station_id = cell_to_station.get(cell)
            if station_id is None:
                continue
            key = (handle, station_id)
            times[key] = max(last, times.get(key, last))
    return times


def evaluate_connections(
    connections: Sequence[PlannedConnection],
    times: Dict[Tuple[int, str], int],
) -> ConnectionReport:
    """Judge each planned connection against what the run actually did.

    Kept means the feeder was still at the station before the connector, so
    a passenger changing between them still had somewhere to change to. A
    train that never called at all breaks the connection just as surely as
    a reordered one — the passenger is left standing either way — so it
    counts as broken. The reason is recorded to tell the two apart when
    diagnosing, not to excuse one of them.

    Equal times count as kept: the two trains are both standing there, so
    the transfer is possible; only an actual reversal breaks it.
    """
    outcomes: List[ConnectionOutcome] = []
    for connection in connections:
        feeder_time = times.get((connection.feeder, connection.station_id))
        connector_time = times.get((connection.connector, connection.station_id))
        if feeder_time is None:
            reason, kept = "feeder_absent", False
        elif connector_time is None:
            reason, kept = "connector_absent", False
        elif feeder_time <= connector_time:
            reason, kept = "kept", True
        else:
            reason, kept = "reordered", False
        outcomes.append(ConnectionOutcome(
            connection=connection,
            kept=kept,
            reason=reason,
            feeder_time=feeder_time,
            connector_time=connector_time,
        ))
    return ConnectionReport(outcomes=outcomes)


def station_watch_cells(stations: Sequence[Station]) -> List[Tuple[int, int]]:
    """Every platform cell, for `run_schedules(watch_cells=...)`."""
    return [cell for station in stations for cell in station.stop_cells]


__all__ = [
    "ConnectionOutcome",
    "ConnectionReport",
    "PlannedConnection",
    "StationCall",
    "evaluate_connections",
    "observed_times",
    "planned_connections",
    "planned_order",
    "station_calls",
    "station_watch_cells",
]
