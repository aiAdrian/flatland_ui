/**
 * Combined Actions — deterministic impact prediction (MOCK).
 *
 * Spec: docs/plans/widget-e1-combined-actions.md §8.
 *
 * This is a placeholder for a real re-solve of a human-supplied train priority
 * order. The consortium reuse target is the CBS/PP solver in
 * `AI4REALNET/flatland-blackbox` (the canonical source that `Tokener` and
 * `T3.4-with-HMI` both vendor): running PP with the operator's priority order is
 * exactly the computation this file fakes. Building it from scratch here is a
 * deliberate, spec'd decision — the first cut is about the *interaction* (human
 * edits a coordinated multi-train action → system re-evaluates the consequence),
 * not the optimiser.
 *
 * The only contract that matters for the swap: `predictImpact` is pure and
 * total — the same order ALWAYS yields the same numbers. A prediction that
 * jitters between identical inputs is not something an operator can calibrate
 * trust against (core question Q2).
 */

/** Confidence in a predicted impact. Mirrors the recommendations panel's vocabulary. */
export type ImpactConfidence = 'high' | 'medium' | 'low';

/** What a train order is predicted to achieve. */
export interface ImpactPrediction {
  /** Total delay reduction across the affected trains, in minutes (≥ 0). */
  delayReductionMin: number;
  /** Traction energy the order is predicted to cost, in kWh.
   *
   *  The second axis of the trade-off: the fastest order is rarely the cheapest
   *  one. A train held back has to brake and re-accelerate, and heavy
   *  long-distance stock pays far more for that than an S-Bahn — so an order
   *  that squeezes delay by making an ICE wait can cost more energy than the
   *  minutes are worth. Modelled, not measured (§8) — the backend folds energy
   *  into delay today and has no separate KPI (`scenario_builder.py`). */
  energyKwh: number;
  /** How many trains the package touches. */
  affectedTrains: number;
  /** Confidence in this prediction. */
  confidence: ImpactConfidence;
}

/**
 * The predictor seam. Swap the mock for an HTTP/solver-backed implementation by
 * providing a different `ImpactPredictor` — nothing in the UI depends on the
 * mock's internals.
 */
export interface ImpactPredictor {
  predict(trainOrder: readonly string[]): ImpactPrediction;
}

/**
 * Per-train dispatch weight — how much of the network's delay hangs off letting
 * this train go first. Long-distance services carry more onward connections than
 * regional ones, which is why an IC/ICE/TGV outranks an RE/RB/S-Bahn here.
 * Authored, not measured (§8).
 */
const TRAIN_WEIGHT: Record<string, number> = {
  ICE_42: 6,
  TGV_12: 6,
  IC_703: 5,
  EC_91: 5,
  IR_227: 4,
  RE_18: 3,
  S8_214: 2,
  RB_51: 2,
};

/** Fallback weight for a train the fixture table does not know. */
const DEFAULT_WEIGHT = 3;

/**
 * Orders whose outcome is fixed by the spec. Keyed by the order joined with '>'.
 * These are the numbers the brief names; the positional model below only governs
 * orders that are not listed here.
 */
const SEEDED: Record<string, { reduction: number; confidence: ImpactConfidence }> = {
  // Action A — the AI proposal and the two modifications named in the spec.
  'IC_703>ICE_42>RE_18>S8_214': { reduction: 14, confidence: 'high' },
  'ICE_42>IC_703>RE_18>S8_214': { reduction: 9, confidence: 'medium' },
  'IC_703>RE_18>ICE_42>S8_214': { reduction: 6, confidence: 'medium' },
  // Action B / Action C originals.
  'EC_91>IC_703>RB_51>ICE_42': { reduction: 11, confidence: 'medium' },
  'IR_227>RE_18>TGV_12>S8_214': { reduction: 8, confidence: 'medium' },
};

/**
 * Braking-and-restart energy penalty per train, in kWh per position of waiting.
 * Mass and top speed drive it, which is why an ICE/TGV costs multiples of an
 * S-Bahn to hold back. Authored, not measured (§8).
 */
const TRAIN_RESTART_KWH: Record<string, number> = {
  ICE_42: 34,
  TGV_12: 36,
  IC_703: 26,
  EC_91: 27,
  IR_227: 18,
  RE_18: 13,
  S8_214: 8,
  RB_51: 7,
};

/** Fallback restart cost for a train the fixture table does not know. */
const DEFAULT_RESTART_KWH = 15;

/** Baseline traction energy every train in the package spends regardless. */
const BASE_KWH_PER_TRAIN = 40;

/** Stable 32-bit FNV-1a hash — the deterministic source of the per-order jitter. */
function hash(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

function weightOf(train: string): number {
  return TRAIN_WEIGHT[train] ?? DEFAULT_WEIGHT;
}

/**
 * Positional score: a train's weight counts for more the earlier it is dispatched.
 * Highest for weight-descending order, lowest for weight-ascending order — so a
 * modification that pushes a heavy train back reads as a loss, which is the whole
 * point of the widget.
 */
function positionalScore(order: readonly string[]): number {
  return order.reduce((sum, train, i) => sum + weightOf(train) * (order.length - i), 0);
}

/** The best and worst positional scores reachable by permuting this exact set. */
function scoreBounds(order: readonly string[]): { min: number; max: number } {
  const weights = order.map(weightOf);
  const n = weights.length;
  const best = [...weights].sort((a, b) => b - a);
  const worst = [...weights].sort((a, b) => a - b);
  const score = (w: number[]) => w.reduce((sum, x, i) => sum + x * (n - i), 0);
  return { min: score(worst), max: score(best) };
}

/**
 * Where this order sits between the worst (0) and the best (1) possible
 * arrangement of the same trains.
 */
function qualityOf(order: readonly string[]): number {
  const { min, max } = scoreBounds(order);
  const span = max - min;
  return span === 0 ? 1 : (positionalScore(order) - min) / span;
}

/**
 * Deterministic pseudo-prediction for an order the seed table does not cover.
 *
 * `qualityOf` (0..1) maps onto a delay-reduction band, and a hash-derived ±1 min
 * offset keeps the surface from looking like a straight line.
 */
function pseudoReduction(order: readonly string[]): number {
  // Band chosen so a plausible order lands in the same 3..15 min range as the
  // seeded ones — a modification must be comparable to the AI proposal it replaces.
  const base = 3 + qualityOf(order) * 11;
  const jitter = (hash(order.join('>')) % 3) - 1; // -1 | 0 | +1, stable per order
  return Math.max(0, Math.round(base + jitter));
}

/**
 * Kendall-tau-like distance: how many pairs of trains this order swaps relative
 * to the AI's proposal. 0 = identical.
 */
export function orderDistance(order: readonly string[], reference: readonly string[]): number {
  const rank = new Map(reference.map((t, i) => [t, i]));
  let inversions = 0;
  for (let i = 0; i < order.length; i++) {
    for (let j = i + 1; j < order.length; j++) {
      const a = rank.get(order[i]);
      const b = rank.get(order[j]);
      if (a !== undefined && b !== undefined && a > b) inversions++;
    }
  }
  return inversions;
}

/**
 * Confidence for an order the seed table does not cover. Never 'high': the mock
 * model has not "seen" this arrangement, and claiming high confidence in a
 * number it extrapolated is exactly the miscalibration the trust widgets exist
 * to prevent (core question Q2).
 */
function derivedConfidence(order: readonly string[]): ImpactConfidence {
  return qualityOf(order) >= 0.8 ? 'medium' : 'low';
}

/**
 * Predict the operational impact of dispatching `trainOrder` in that sequence.
 * Pure and total: identical input ⇒ identical output, always.
 */
/**
 * Traction energy for an order: every train pays a base cost, plus a restart
 * penalty for each position it waits. Purely positional, so it is stable per
 * order like the delay figure — and it deliberately pulls the *opposite* way
 * from delay when a heavy train is held back, which is what makes the two axes
 * worth plotting against each other.
 */
function energyFor(order: readonly string[]): number {
  const total = order.reduce(
    (sum, train, i) => sum + BASE_KWH_PER_TRAIN + i * (TRAIN_RESTART_KWH[train] ?? DEFAULT_RESTART_KWH),
    0,
  );
  return Math.round(total);
}

export function predictImpact(trainOrder: readonly string[]): ImpactPrediction {
  const seeded = SEEDED[trainOrder.join('>')];
  return {
    delayReductionMin: seeded ? seeded.reduction : pseudoReduction(trainOrder),
    energyKwh: energyFor(trainOrder),
    affectedTrains: trainOrder.length,
    confidence: seeded ? seeded.confidence : derivedConfidence(trainOrder),
  };
}

/** The mock predictor, as an `ImpactPredictor`. */
export const MOCK_IMPACT_PREDICTOR: ImpactPredictor = { predict: predictImpact };
