import { ImpactPrediction, predictImpact } from './impact-prediction';

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

/**
 * Every distinct train across the packages, in a fixed order.
 *
 * The order is the binding order onto the session's live Flatland handles (see
 * the panel's `handleByTrain`): first train ↔ lowest handle. Fixed here rather
 * than derived, so the same session always binds the same way and a study can
 * be replayed.
 */
export const ALL_TRAINS: readonly string[] = [
  'IC_703',
  'ICE_42',
  'RE_18',
  'S8_214',
  'EC_91',
  'RB_51',
  'IR_227',
  'TGV_12',
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
