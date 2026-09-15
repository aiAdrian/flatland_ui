import { DecisionLogEntry } from './decision-log';
import { interventionsFrom } from './shift-review';

function entry(partial: Partial<DecisionLogEntry>): DecisionLogEntry {
  return {
    seq: 1,
    t: 0,
    simStep: 0,
    mode: 'co-learning',
    handle: 0,
    accountableOwner: 'human',
    action: 'hold',
    ...partial,
  } as DecisionLogEntry;
}

describe('interventionsFrom', () => {
  it('lists human per-train decisions in order, with the stated reason', () => {
    const result = interventionsFrom([
      entry({ seq: 2, simStep: 40, handle: 1, action: 'proceed' }),
      entry({ seq: 1, simStep: 28, handle: 1, action: 'hold', rationale: 'Vermeide Deadlock', hypothesisResponse: 'once' }),
    ]);

    expect(result.map((i) => i.seq)).toEqual([1, 2]);
    expect(result[0]).toEqual(
      jasmine.objectContaining({ step: 28, handle: 1, action: 'hold', reason: 'Vermeide Deadlock', response: 'once' }),
    );
    expect(result[1].reason).toBeNull();
  });

  it('leaves out system holds, strategy choices and coordinated packages', () => {
    const result = interventionsFrom([
      entry({ seq: 1, accountableOwner: 'system' }),
      entry({ seq: 2, action: 'strategy', handle: -1 }),
      entry({ seq: 3, action: 'accept', handle: -1 }),
      entry({ seq: 4, accountableOwner: 'ai' }),
    ]);

    expect(result).toEqual([]);
  });

  it('strips the strategy bookkeeping prefix from a reason', () => {
    const [only] = interventionsFrom([entry({ rationale: 'Strategie: Anschlüsse halten; Schützt Anschluss' })]);

    expect(only.reason).toBe('Schützt Anschluss');
  });
});
