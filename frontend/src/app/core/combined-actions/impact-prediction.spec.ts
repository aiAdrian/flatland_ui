import { orderDistance, predictImpact } from './impact-prediction';
import { ACTION_PACKAGES } from './action-packages';

/**
 * The predictor's contract is determinism (spec §6, core question Q2: a
 * prediction that jitters between identical inputs cannot be calibrated
 * against) plus the seeded values the widget brief names.
 */
describe('predictImpact', () => {
  const A = ['IC_703', 'ICE_42', 'RE_18', 'S8_214'];

  it('returns the seeded value for each order named in the spec', () => {
    expect(predictImpact(A).delayReductionMin).toBe(14);
    expect(predictImpact(['ICE_42', 'IC_703', 'RE_18', 'S8_214']).delayReductionMin).toBe(9);
    expect(predictImpact(['IC_703', 'RE_18', 'ICE_42', 'S8_214']).delayReductionMin).toBe(6);
    expect(predictImpact(['EC_91', 'IC_703', 'RB_51', 'ICE_42']).delayReductionMin).toBe(11);
    expect(predictImpact(['IR_227', 'RE_18', 'TGV_12', 'S8_214']).delayReductionMin).toBe(8);
  });

  it('gives every action package the impact its card advertises', () => {
    const advertised = [14, 11, 8];
    ACTION_PACKAGES.forEach((pkg, i) => {
      expect(predictImpact(pkg.aiOrder).delayReductionMin).toBe(advertised[i]);
    });
  });

  it('is stable — the same order always returns the same prediction', () => {
    const unseeded = ['S8_214', 'RE_18', 'ICE_42', 'IC_703'];
    const first = predictImpact(unseeded);
    for (let i = 0; i < 20; i++) {
      expect(predictImpact(unseeded)).toEqual(first);
    }
  });

  it('never claims high confidence for an order it was not seeded on', () => {
    expect(predictImpact(['S8_214', 'RE_18', 'ICE_42', 'IC_703']).confidence).not.toBe('high');
    expect(predictImpact(['RE_18', 'S8_214', 'IC_703', 'ICE_42']).confidence).not.toBe('high');
  });

  it('reports the number of trains the order touches', () => {
    expect(predictImpact(A).affectedTrains).toBe(4);
    expect(predictImpact(['IC_703', 'ICE_42']).affectedTrains).toBe(2);
  });

  it('prices holding a heavy train back', () => {
    // The energy axis only earns its place if it pulls against delay: moving
    // the ICE to the back of the queue has to cost more than letting it go.
    const iceFirst = predictImpact(['ICE_42', 'IC_703', 'RE_18', 'S8_214']).energyKwh;
    const iceLast = predictImpact(['IC_703', 'RE_18', 'S8_214', 'ICE_42']).energyKwh;
    expect(iceLast).toBeGreaterThan(iceFirst);
  });

  it('returns a stable, positive energy figure', () => {
    const order = ['IR_227', 'RE_18', 'TGV_12', 'S8_214'];
    const first = predictImpact(order).energyKwh;
    expect(first).toBeGreaterThan(0);
    expect(predictImpact(order).energyKwh).toBe(first);
  });

  it('never returns a negative reduction', () => {
    // Worst possible arrangement of the heaviest/lightest mix.
    expect(predictImpact(['S8_214', 'RB_51', 'IC_703', 'ICE_42']).delayReductionMin)
      .toBeGreaterThanOrEqual(0);
  });
});

describe('orderDistance', () => {
  const A = ['IC_703', 'ICE_42', 'RE_18', 'S8_214'];

  it('is zero for the unchanged order', () => {
    expect(orderDistance(A, A)).toBe(0);
  });

  it('counts one inversion for a single adjacent swap', () => {
    expect(orderDistance(['ICE_42', 'IC_703', 'RE_18', 'S8_214'], A)).toBe(1);
  });

  it('grows with the number of swapped pairs', () => {
    expect(orderDistance([...A].reverse(), A)).toBe(6);
  });
});
