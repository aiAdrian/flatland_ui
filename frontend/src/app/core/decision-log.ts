import { InteractionMode } from './events/event-types';

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

export interface DecisionLogEntry {
  /** Monotonic sequence number within the session (1-based). */
  seq: number;
  /** Wall-clock timestamp (ms). */
  t: number;
  /** Simulation step at which the decision was made. */
  simStep: number;
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
}

/** Rolling cap on the in-memory log (newest kept). */
export const DECISION_LOG_CAP = 500;

/** Flatland RailEnvActions: LEFT=1, FORWARD=2, RIGHT=3, STOP_MOVING=4.
 *  4 → hold; 1/2/3 → reroute (the alternative-branch override). */
export function actionLabelFor(actionCode: number): 'hold' | 'reroute' {
  return actionCode === 4 ? 'hold' : 'reroute';
}
