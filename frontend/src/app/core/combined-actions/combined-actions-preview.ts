/**
 * Combined Actions — the consequence an action package is predicted to have,
 * in the form the *other* views can draw.
 *
 * Spec: docs/plans/widget-e1-combined-actions.md §4.
 *
 * Reordering a dispatch priority list does not reroute anybody — it changes
 * **who is released first** at a contended resource, i.e. timing, not topology.
 * That is why the two views show different halves of the same consequence:
 *
 *  - the **Marey / ZWL** is the time-distance view, so the consequence there is
 *    the affected trains' future lines *shifted along the time axis* by the
 *    minutes they gain or lose;
 *  - the **track map** is the topology view, so the consequence there is *which*
 *    trains the package moves and *in what order* they are released — a reroute
 *    overlay would be a lie, because a priority order does not produce one.
 */

/**
 * Demo convention: one simulation step ≈ one minute.
 *
 * The simulation's native delay unit is **steps** (see `scenario_runner.py`);
 * the widget speaks minutes because the brief does. This is the single place
 * the two meet, so a real timetable scale later changes one number.
 */
export const MINUTES_PER_STEP = 1;

/** Minutes a train gains or loses per position it moves in the order. */
const MINUTES_PER_POSITION = 2;

/** What the other views need to draw an action package's consequence. */
export interface CombinedActionPreview {
  /** Package id ('A' | 'B' | 'C'), so a pinned card can render as pinned. */
  packageId: string;
  /** Card label, for the map/Marey legend. */
  label: string;
  /** The human has changed this package's AI order. */
  modified: boolean;
  /** Train handle → 1-based dispatch rank in the previewed order. */
  rankByHandle: Record<number, number>;
  /** Train handle → predicted delay change in minutes. Negative = runs
   *  earlier than it would without this action. */
  deltaMinByHandle: Record<number, number>;
  /** Train handle → the service name the card shows for it. */
  trainByHandle: Record<number, string>;
}

/**
 * Per-train delay change, in minutes, for one dispatch order.
 *
 * Two effects are added, and the split is the point — a dispatcher asks both
 * "is the network better off?" and "who pays for it?":
 *
 *  1. **The package's net gain**, shared equally: `-netReductionMin / n`.
 *  2. **The train's own move**, relative to `baselineOrder` — the order the
 *     trains would take with no coordinated action at all. Moving one position
 *     later costs `MINUTES_PER_POSITION`, one position earlier saves it.
 *
 * Because both are permutations of the same set, the position terms cancel and
 * the deltas sum to `-netReductionMin` before rounding — the redistribution
 * never invents or destroys network-level gain.
 *
 * Deterministic and pure, like `predictImpact`: same inputs, same numbers.
 */
export function perTrainDeltaMin(
  order: readonly string[],
  baselineOrder: readonly string[],
  netReductionMin: number,
): Record<string, number> {
  const n = order.length;
  if (n === 0) return {};

  const baselineRank = new Map(baselineOrder.map((train, i) => [train, i]));
  const share = -netReductionMin / n;

  const out: Record<string, number> = {};
  order.forEach((train, i) => {
    const from = baselineRank.get(train);
    const moved = from === undefined ? 0 : i - from;
    out[train] = Math.round(share + moved * MINUTES_PER_POSITION);
  });
  return out;
}

/** The delay change as a shift along the Marey's time axis, in steps. */
export function deltaSteps(deltaMin: number): number {
  return Math.round(deltaMin / MINUTES_PER_STEP);
}
