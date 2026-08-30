import { deltaSteps, perTrainDeltaMin } from './combined-actions-preview';

/**
 * The per-train split is what the map badges and the Marey ghost lines are drawn
 * from, so its two invariants matter: it must not invent network-level gain, and
 * a train that is dispatched earlier must come out ahead of one pushed back.
 */
describe('perTrainDeltaMin', () => {
  const A = ['IC_703', 'ICE_42', 'RE_18', 'S8_214'];

  it('shares the net gain equally when nothing moved', () => {
    const deltas = perTrainDeltaMin(A, A, 14);
    expect(new Set(Object.values(deltas)).size).toBe(1);
  });

  it('sums to the package net gain, up to rounding', () => {
    const order = ['S8_214', 'IC_703', 'ICE_42', 'RE_18'];
    const sum = Object.values(perTrainDeltaMin(order, A, 10)).reduce((a, b) => a + b, 0);
    expect(Math.abs(sum + 10)).toBeLessThanOrEqual(order.length / 2);
  });

  it('gives a train moved earlier more than one moved later', () => {
    const deltas = perTrainDeltaMin(['S8_214', 'IC_703', 'ICE_42', 'RE_18'], A, 10);
    expect(deltas['S8_214']).toBeLessThan(deltas['RE_18']);
  });

  it('is empty for an empty order', () => {
    expect(perTrainDeltaMin([], [], 10)).toEqual({});
  });
});

describe('deltaSteps', () => {
  it('maps minutes onto simulation steps', () => {
    expect(deltaSteps(-3)).toBe(-3);
    expect(deltaSteps(0)).toBe(0);
  });
});
