import { InteractionMode } from './events/event-types';
import type { ActionOrigin } from './dispatch/train-action.service';

/**
 * Decision Log (Tile A2) — the session's owned, timestamped decision record.
 *
 * Spec: docs/plans/tile-a2-decision-log.md. `kind` = Capitalization. This is
 * the first visible slice of [interaction-logging-plan.md](../plans/interaction-logging-plan.md)
 * — it reuses existing capture choke-points (setOverride / clearOverride /
 * systemHold) rather than introducing a parallel logging mechanism.
 *
 * Every entry has an `accountableOwner`:
 *   - 'human'  — the operator clicked (accept or override; either way a human
 *                decision, per the spec's §6 acceptance scenario)
 *   - 'ai'     — the AI auto-applied (countdown expiry / autonomous Director)
 *   - 'system' — a safe-default hold (`SessionStore.systemHold`), deliberately
 *                NOT attributed to either party (the code's own comment at
 *                session.store.ts:981)
 *
 * The schema field names map cleanly onto the WP4 Railway KPI catalog
 * (override rate → KPI-HS-003; decisionTimeMs → KPI-HS-023; accept/override
 * ratio → KPI-AS-005) — see the spec's §5b. No FAB/orchestrator integration is
 * done here; this is purely a naming precaution.
 */

export type DecisionOwner = 'human' | 'ai' | 'system';

export type DecisionAction =
  | 'hold'
  | 'reroute'
  | 'proceed'
  | 'accept'
  | 'override'
  | 'dismiss'
  /** Director: the operator committed the autonomous plan to a strategy focus.
   *  Not about one train — it is the objective the whole plan pursues. */
  | 'strategy';

/** Value axes, duplicated from `operator-model.service` to keep this leaf module
 *  import-free. */
export type DecisionValueAxis = 'punctuality' | 'throughput' | 'stability' | 'connection';

/**
 * A coordinated multi-train action, as the log records it.
 *
 * The entry schema is per-train (`handle`), and a combined action is not: it is
 * an *order* over several trains. Rather than emit one entry per train — which
 * would record the parts and lose the coordination, the one thing the operator
 * actually decided — a coordinated action is one entry with `handle: -1`, the
 * convention `action: 'strategy'` already uses for decisions that are not about
 * a single train.
 *
 * Both orders are kept, never just the applied one. The whole point of the
 * Combined Actions surfaces is the distinction between what the AI proposed and
 * what the operator made of it; a log that stores only the outcome cannot
 * answer "did they take the AI's answer or their own?", which is the question
 * (Q3, accountability) the log exists for. `action` says which: `'accept'` when
 * the applied order is the AI's, `'override'` when it is not — the two values
 * the schema reserved for exactly this and never wired.
 */
export type CoordinatedVariant =
  /** Widget E1: three packages to compare, one editable in place. */
  | 'packages'
  /** Widget E1b: one package to reorder and confirm. */
  | 'package';

/**
 * Predicted figures for one order.
 *
 * A shared core plus what each variant actually measures. Forcing both into one
 * vocabulary would mean inventing a number for whichever surface does not have
 * it — so the fields a variant does not compute are simply absent, and a reader
 * can tell "not measured here" from "measured as zero".
 */
export interface CoordinatedImpact {
  /** Minutes of delay the order is predicted to save. */
  delayReductionMin: number | null;
  /** E1: planned transfers this order keeps, of the ones it can affect. */
  transfersKept?: number | null;
  transfersTotal?: number | null;
  /** E1b: trains the re-slotting moves that the order never dispatched — the
   *  indirect cost its queue model exists to make visible. */
  affectedTrains?: number | null;
}

export interface CoordinatedDecision {
  /** Which surface produced this. The two variants are never on screen at once
   *  (they are separate layout presets), so entries cannot interleave within a
   *  session — but a study comparing the surfaces has to be able to tell the
   *  records apart afterwards. */
  variant: CoordinatedVariant;
  /** The package as the operator saw it named ('Action A'). */
  label: string;
  /** The AI's proposed order, in service names. */
  aiOrder: readonly string[];
  /** The order that was applied. Equal to `aiOrder` on an accept. */
  appliedOrder: readonly string[];
  /** The same order in train handles. The service names are an authored alias
   *  (`SERVICE_ROSTER`); the handles are what the session actually contains, so
   *  a record that outlives the alias still points at real trains. */
  handles: readonly number[];
  aiImpact: CoordinatedImpact;
  appliedImpact: CoordinatedImpact;
  /**
   * Whether the order reached the planner.
   *
   * `false` for both variants today: Apply sets a confirmation and controls no
   * train (spec §4, "`Apply` actually committing the order to the planner" is
   * still flagged). Recorded explicitly rather than left to be assumed, because
   * a decision record that reads as executed when nothing moved is worse than
   * no record — it is the one failure mode an audit trail cannot survive.
   */
  committed: boolean;
}

export interface DecisionLogEntry {
  /** Monotonic sequence number within the session (1-based). */
  seq: number;
  /** Wall-clock timestamp (ms). */
  t: number;
  /** Simulation step at which the decision was made. */
  simStep: number;
  /** Which surface the operator acted from (map, roster, table, …). The same
   *  action is deliberately offered in several places; recording the affordance
   *  turns "which one do dispatchers actually use?" into a measurement instead
   *  of an assertion (HMI review §3). Absent on entries written before the
   *  dispatch seam existed, and on system-owned holds. */
  origin?: ActionOrigin;
  /** Active interaction mode when the decision was made. */
  mode: InteractionMode;
  /** Agent (train handle) the decision concerned. */
  handle: number;
  /** Who owns the outcome of this decision. */
  accountableOwner: DecisionOwner;
  /** What was done (movement semantic for overrides; accept/override/dismiss
   *  reserved for the recommendations-panel context, not wired in the first cut). */
  action: DecisionAction;
  /** Top AI recommendation title at the moment of decision, if any. */
  aiSuggestion: string | null;
  /** Dwell time from decision-moment-open to decision, in ms. null for system
   *  / autonomous entries (no human dwell). */
  decisionTimeMs: number | null;
  /** Chosen "why" behind a human override (Workstream B Tier 1, deck slide 7).
   *  Absent on entries the operator never annotated, and on all non-human
   *  entries. Mirrored from the rationale-capture prompt. */
  rationale?: string;
  /** Generated preference hypothesis the operator was shown. */
  preferenceHypothesis?: string;
  /** Operator's confirmation of that hypothesis. 'once' is the explicit
   *  overfitting guard — a one-off decision that must not become a rule. */
  hypothesisResponse?: 'yes' | 'once' | 'no';
  /**
   * The value axis this decision is evidence for, when the decision *states* it
   * rather than implying it. A Director strategy choice does: picking
   * "Anschlüsse halten" over two named alternatives with quantified costs is a
   * direct statement of priority, so there is nothing to infer from KPI deltas
   * or to guess from a reason chip.
   */
  valueAxis?: DecisionValueAxis;
  /** Human-readable summary of what the choice gave up, for the reflection card
   *  and the learning record ("−31 Pünktlichkeit"). */
  tradedAway?: string;
  /** Present on coordinated multi-train actions; see `CoordinatedDecision`.
   *  Absent on every per-train entry, so existing readers are untouched. */
  coordinated?: CoordinatedDecision;
}

/** Rolling cap on the in-memory log (newest kept). */
export const DECISION_LOG_CAP = 500;

/** Flatland RailEnvActions: LEFT=1, FORWARD=2, RIGHT=3, STOP_MOVING=4.
 *  4 → hold; 1/2/3 → reroute (the alternative-branch override). */
export function actionLabelFor(actionCode: number): 'hold' | 'reroute' {
  return actionCode === 4 ? 'hold' : 'reroute';
}
