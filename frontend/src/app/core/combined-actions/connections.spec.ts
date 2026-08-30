import { AgentDTO } from '../models';
import { plannedTransfers, transferOutcome } from './connections';

/** Just enough agent to carry a timetable. */
function train(handle: number, stops: [number, number, number][]): AgentDTO {
  return {
    handle,
    position: null,
    direction: null,
    initial_position: null,
    initial_direction: null,
    target: [0, 0],
    stops: stops.map(([r, c, t]) => ({
      cell: [r, c] as [number, number],
      earliest_departure: t,
      latest_arrival: null,
    })),
    state: 'READY_TO_DEPART',
    speed: 1,
  } as AgentDTO;
}

describe('plannedTransfers', () => {
  it('pairs trains that call at the same place, feeder first', () => {
    const transfers = plannedTransfers([
      train(0, [[2, 10, 5]]),
      train(1, [[2, 10, 9]]),
    ]);

    expect(transfers.length).toBe(1);
    expect(transfers[0].feeder).toBe(0);
    expect(transfers[0].connector).toBe(1);
    expect(transfers[0].plannedGap).toBe(4);
  });

  it('ignores trains that never meet', () => {
    expect(plannedTransfers([train(0, [[2, 10, 5]]), train(1, [[4, 80, 9]])])).toEqual([]);
  });

  it('skips calls planned for the same step — their order carries no information', () => {
    expect(plannedTransfers([train(0, [[2, 10, 5]]), train(1, [[2, 10, 5]])])).toEqual([]);
  });

  it('pairs all-to-all at a place, not only neighbours', () => {
    const transfers = plannedTransfers([
      train(0, [[2, 10, 1]]),
      train(1, [[2, 10, 2]]),
      train(2, [[2, 10, 3]]),
    ]);
    // 0>1, 0>2, 1>2 — a passenger can change between any two that meet there.
    expect(transfers.length).toBe(3);
  });
});

describe('transferOutcome', () => {
  const transfers = plannedTransfers([
    train(0, [[2, 10, 1]]),
    train(1, [[2, 10, 2]]),
  ]);

  it('keeps the transfer when the order preserves the planned sequence', () => {
    expect(transferOutcome([0, 1], transfers)).toEqual(
      jasmine.objectContaining({ kept: 1, total: 1 }),
    );
  });

  it('breaks it when the order reverses the pair — the trade-off against delay', () => {
    const outcome = transferOutcome([1, 0], transfers);
    expect(outcome.kept).toBe(0);
    expect(outcome.total).toBe(1);
    expect(outcome.broken[0].feeder).toBe(0);
  });

  it('judges only transfers whose both ends the order dispatches', () => {
    // The action says nothing about train 1, so this is not its doing and must
    // not be counted as kept either — it drops out of the total.
    expect(transferOutcome([0], transfers)).toEqual(
      jasmine.objectContaining({ kept: 0, total: 0 }),
    );
  });
});
