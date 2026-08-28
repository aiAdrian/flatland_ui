import { ImpactPrediction, predictImpact, trainWeight } from './impact-prediction';
export { SERVICE_ROSTER as ALL_TRAINS } from '../train-identity.service';

/**
 * Combined Actions — the authored action packages.
 *
 * Each package is a *coordinated multi-train action*: an ordered priority list
 * over the trains contending for the same resource, plus the impact that order is
 * predicted to have. This is the Tokener (T3.4) unit of interaction — the
 * operator negotiates one order, not four separate train commands.
 *
 * Fixtures, not simulation output (spec §4, `dataSource: 'mock'`). Replacing them
 * with packages derived from live conflicts is a flagged extension.
 */

/** Train category, used only to type the chip visually (no per-train colours). */
export type TrainCategory = 'long-distance' | 'regional' | 'suburban';

/** An AI-generated action package in its original, unmodified form. */
export interface ActionPackage {
  /** Stable id — 'A' | 'B' | 'C'. */
  id: string;
  /** Card label, e.g. 'Action A'. */
  label: string;
  /** The AI's proposed dispatch order. Never mutated; the human edit lives
   *  beside it so the AI ↔ human distinction stays visible (spec §3). */
  aiOrder: readonly string[];
  /** True for the package the AI ranks best. Survives human modification —
   *  the card keeps "Recommended by AI", it just adds "Human modified". */
  recommended: boolean;
  /** One short line on what this order does, for the card's second row. */
  rationale: string;
}

export const ACTION_PACKAGES: readonly ActionPackage[] = [
  {
    id: 'A',
    label: 'Action A',
    aiOrder: ['IC_703', 'ICE_42', 'RE_18', 'S8_214'],
    recommended: true,
    rationale: 'Clears the through-running services first, regional traffic follows.',
  },
  {
    id: 'B',
    label: 'Action B',
    aiOrder: ['EC_91', 'IC_703', 'RB_51', 'ICE_42'],
    recommended: false,
    rationale: 'Protects the cross-border connection at the cost of ICE_42.',
  },
  {
    id: 'C',
    label: 'Action C',
    aiOrder: ['IR_227', 'RE_18', 'TGV_12', 'S8_214'],
    recommended: false,
    rationale: 'Keeps the regional cadence intact, delays the long-distance pair.',
  },
];

/** Category per train, for chip styling. Authored alongside the fixtures. */
const TRAIN_CATEGORY: Record<string, TrainCategory> = {
  ICE_42: 'long-distance',
  TGV_12: 'long-distance',
  IC_703: 'long-distance',
  EC_91: 'long-distance',
  IR_227: 'regional',
  RE_18: 'regional',
  RB_51: 'regional',
  S8_214: 'suburban',
};

export function trainCategory(train: string): TrainCategory {
  return TRAIN_CATEGORY[train] ?? 'regional';
}

/** The impact of a package's untouched AI order — the baseline every card
 *  compares its current (possibly human-modified) order against. */
export function aiBaseline(pkg: ActionPackage): ImpactPrediction {
  return predictImpact(pkg.aiOrder);
}

// ── Packages derived from live conflicts (Stufe 1) ─────────────────
//
// The fixture `ACTION_PACKAGES` above is what the spec's acceptance
// walkthrough (§6) and `impact-prediction.spec.ts` still consume; it stays.
// The panel, however, now builds its packages from the session's real
// contentions so every chip resolves to a train actually in the Fahrplan
// (the defect the PF–CH 3-train scenario exposed). Impact figures keep
// coming from the deterministic model — the real PP/CBS re-solve remains a
// flagged extension (spec §4).

/** Per-handle context the package builder ranks on. */
export interface PackageContext {
  /** Scheduled arrival deadline per handle (`AgentDTO.latest_arrival`) — the
   *  "earliest scheduled arrival first" package ranks on this. */
  arrivalByHandle: Record<number, number>;
  /** Current delay per handle (`AgentDTO.delay`) — the "most-delayed first"
   *  package ranks on this. */
  delayByHandle: Record<number, number>;
}

/** Sort comparator that never returns 0 for equal keys — a stable tiebreak by
 *  handle keeps two trains with the same rank in a deterministic order, so
 *  the same group always yields the same package (Q2 · calibrated trust). */
function byValueThenHandle(
  valueOf: (h: number) => number,
  direction: 1 | -1,
): (a: number, b: number) => number {
  return (a, b) => {
    const va = valueOf(a);
    const vb = valueOf(b);
    if (va !== vb) return direction * (va - vb);
    return a - b;
  };
}

/**
 * Turn one contention group (the handles the backend reports as contending
 * for the same resource) into three coordinated-action packages, each with a
 * different, stateable dispatch rationale — the operator has to be able to
 * say why B differs from A.
 *
 *   A — by service weight, long-distance first (the TRAIN_WEIGHT ranking the
 *       seeded Action A uses). `recommended: true`.
 *   B — by earliest scheduled arrival first.
 *   C — by current delay, most-delayed first.
 *
 * Train names come from `nameOf` (TrainIdentityService.nameByHandle) — never
 * from SERVICE_ROSTER directly. That is what makes the chips real: a name the
 * map, the ZWL and the timetable also resolve to the same handle.
 *
 * If two orderings come out identical for a group, both cards are kept and
 * show the same figures — a card is never silently dropped, and a difference
 * is never fabricated. The three cards stay three because the widget's whole
 * interaction is "compare coordinated orders and edit one".
 */
export function buildPackages(
  handles: readonly number[],
  nameOf: (h: number) => string,
  ctx: PackageContext,
): ActionPackage[] {
  const hs = [...handles];
  const names = (order: readonly number[]) => order.map((h) => nameOf(h));

  // Missing arrival/delay values sort last (Infinity / -Infinity) rather than
  // NaN, so a train whose ETA the payload omitted doesn't poison the order.
  const arrival = (h: number) => ctx.arrivalByHandle[h] ?? Number.POSITIVE_INFINITY;
  const delay = (h: number) => ctx.delayByHandle[h] ?? Number.NEGATIVE_INFINITY;

  const byWeight = [...hs].sort(byValueThenHandle((h) => trainWeight(nameOf(h)), -1));
  const byArrival = [...hs].sort(byValueThenHandle(arrival, 1));
  const byDelay = [...hs].sort(byValueThenHandle(delay, -1));

  return [
    {
      id: 'A',
      label: 'Action A',
      aiOrder: names(byWeight),
      recommended: true,
      rationale: 'Clears the through-running services first, regional traffic follows.',
    },
    {
      id: 'B',
      label: 'Action B',
      aiOrder: names(byArrival),
      recommended: false,
      rationale: 'Dispatches in scheduled-arrival order — the earliest ETA clears the bottleneck first.',
    },
    {
      id: 'C',
      label: 'Action C',
      aiOrder: names(byDelay),
      recommended: false,
      rationale: 'Most-delayed trains first — limits the worst overdue.',
    },
  ];
}
