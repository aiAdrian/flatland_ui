import { AgentDTO } from '../models';

/**
 * Planned transfers, and what a dispatch order does to them.
 *
 * The second axis of the Combined Actions trade-off used to be traction energy.
 * Flatland has no traction model, so that number could only ever be authored —
 * it was the one axis with no path from mock to simulation. Kept transfers is
 * the axis the project actually measures: `connections` is one of the three
 * Director dials (`DirectorWeights`), and the backend scores it for real in
 * `goal_based_policies/connections.py`.
 *
 * **The semantics are the backend's, deliberately.** There, a transfer is kept
 * iff the feeder is at the station no later than the connector
 * (`feeder_time <= connector_time`); the break reason is literally `reordered`.
 * So the thing that breaks a transfer is exactly the thing this widget lets the
 * operator do — change a passing order. That is what makes it a trade-off with
 * delay rather than a second delay axis: letting the heaviest service go first
 * saves minutes and can overtake a feeder; holding it behind preserves the
 * transfer and costs minutes.
 *
 * Planned transfers are derived here from the session's own timetable — the
 * per-agent `stops` the payload already carries — rather than fetched, so no
 * backend change is needed. This mirrors the backend's `planned_connections`:
 * every pair of trains calling at the same place, feeder first, pairs planned
 * for the same step skipped because their order carries no information.
 *
 * Still a model, not a simulation: it asks whether the proposed order reverses
 * a planned pair, not whether the trains physically make it. The figure is
 * therefore honest about *which* transfers an order puts at risk, and silent
 * about whether the network would have delivered them anyway.
 */

/** One planned transfer: `feeder` is scheduled at `cellKey` before `connector`. */
export interface PlannedTransfer {
  cellKey: string;
  feeder: number;
  connector: number;
  /** Planned steps between the two calls — the buffer the transfer has. */
  plannedGap: number;
}

/** What an order does to the transfers among its own trains. */
export interface TransferOutcome {
  kept: number;
  total: number;
  /** The transfers this order reverses, for naming them on the card. */
  broken: readonly PlannedTransfer[];
}

function cellKey(cell: readonly [number, number] | null): string | null {
  return cell ? `${cell[0]}:${cell[1]}` : null;
}

/**
 * When each train is planned to call at each place.
 *
 * `earliest_departure` is the call's time; the destination carries none (a
 * train does not depart its target), so `latest_arrival` stands in there.
 */
function callTimes(agent: AgentDTO): Map<string, number> {
  const out = new Map<string, number>();
  for (const stop of agent.stops ?? []) {
    const key = cellKey(stop.cell);
    const time = stop.earliest_departure ?? stop.latest_arrival;
    if (key === null || time === null || out.has(key)) continue;
    out.set(key, time);
  }
  return out;
}

/**
 * Every planned transfer among `agents`, feeder first.
 *
 * All-to-all within a place rather than consecutive-only, matching the
 * backend: a passenger can change between any two trains that meet there, not
 * only between neighbours in the timetable.
 */
export function plannedTransfers(agents: readonly AgentDTO[]): PlannedTransfer[] {
  const times = new Map<number, Map<string, number>>();
  for (const agent of agents) times.set(agent.handle, callTimes(agent));

  const byPlace = new Map<string, { handle: number; time: number }[]>();
  for (const [handle, calls] of times) {
    for (const [key, time] of calls) {
      const list = byPlace.get(key);
      if (list) list.push({ handle, time });
      else byPlace.set(key, [{ handle, time }]);
    }
  }

  const out: PlannedTransfer[] = [];
  for (const [key, calls] of byPlace) {
    const ordered = [...calls].sort((a, b) => a.time - b.time || a.handle - b.handle);
    for (let i = 0; i < ordered.length; i++) {
      for (let j = i + 1; j < ordered.length; j++) {
        // Same step is not a transfer in either direction: the order carries
        // no information, so demanding one would label noise.
        if (ordered[j].time === ordered[i].time) continue;
        out.push({
          cellKey: key,
          feeder: ordered[i].handle,
          connector: ordered[j].handle,
          plannedGap: ordered[j].time - ordered[i].time,
        });
      }
    }
  }
  return out;
}

/**
 * How the proposed order treats the transfers among the trains it names.
 *
 * Only transfers whose *both* ends are in the order can be judged — the action
 * says nothing about trains it does not dispatch, so their transfers are not
 * this order's doing and are left out of the total rather than counted as kept.
 */
export function transferOutcome(
  handleOrder: readonly number[],
  transfers: readonly PlannedTransfer[],
): TransferOutcome {
  const rank = new Map(handleOrder.map((handle, index) => [handle, index]));
  const relevant = transfers.filter(
    (t) => rank.has(t.feeder) && rank.has(t.connector),
  );
  const broken = relevant.filter(
    (t) => rank.get(t.connector)! < rank.get(t.feeder)!,
  );
  return { kept: relevant.length - broken.length, total: relevant.length, broken };
}
