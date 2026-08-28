/**
 * Combined Actions — the data model.
 *
 * A Combined Action actively redispatches a *subset* of the trains at a conflict
 * and lets everything else run on baseline behaviour. The distinction that the
 * whole feature rests on:
 *
 * - **controlled** — trains the action gives an explicit priority to
 * - **affected**   — every train whose delay changes as a result, controlled or not
 * - **unchanged**  — trains the action leaves untouched *and* without side effect
 *
 * `not controlled` is not `not affected`: holding an ICE at a junction delays the
 * regional service behind it even though nobody dispatched that regional service.
 * The model keeps the three sets apart so the UI can say which is which, and so a
 * later real simulator can fill them in without the shape changing.
 */

export type TrainId = string;

export type ImpactConfidence = 'high' | 'medium' | 'low';

/** What a train brings into the conflict. The simulator reads only these. */
export interface TrainFacts {
  id: TrainId;
  /** Service class, for display. */
  service: string;
  /**
   * The Flatland agent this train stands for, so an action can be highlighted on
   * the map.
   *
   * The conflict is a fixture while the map shows a real session, so the two have
   * to be tied together somewhere; doing it here keeps the guess in one place. It
   * is a stand-in: once conflicts are detected from the live session the handle
   * will be the real one and nothing downstream changes.
   */
  agentHandle: number;
  /** Minutes it counts for — passengers and onward connections. */
  weight: number;
  /** Minutes late when it reaches the conflict area. */
  entryDelay: number;
  /** Minutes it occupies the contended section. */
  headway: number;
  /** Minutes of recovery its timetable still holds before the delay bites. */
  slack: number;
}

/**
 * The situation a Combined Action is generated for: which trains contend for one
 * section, and the order the timetable would send them in.
 *
 * `baselineOrder` is the do-nothing behaviour — it is what the non-controlled
 * trains keep following, and the reference every candidate is measured against.
 */
export interface ConflictWindow {
  id: string;
  /** Where the trains contend. */
  location: string;
  /** Why this is a conflict, in one line. */
  reason: string;
  /** Simulated minutes the evaluation looks ahead. */
  horizonMinutes: number;
  trains: readonly TrainFacts[];
  /** Timetable order through the section, by train id. */
  baselineOrder: readonly TrainId[];
}

/** A primitive the sequence is translated into — the seam to real control. */
export interface ControlPrimitive {
  train: TrainId;
  command: 'proceed' | 'hold';
  /** Which train must clear the section first. Null for the leader. */
  after: TrainId | null;
  /** Position in the intended passing order, 1-based. */
  position: number;
}

/** A candidate, before it has been simulated. */
export interface CombinedAction {
  id: string;
  /** The trains this action actively dispatches, in the intended priority order. */
  sequence: readonly TrainId[];
  /** How the candidate was constructed — kept for the explanation. */
  strategy: CandidateStrategy;
}

export type CandidateStrategy =
  | 'ratio'        // highest weight per occupancy first
  | 'most-delayed' // the latest train first
  | 'heaviest'     // the most important train first
  | 'timetable'    // keep the timetable order among the controlled trains
  | 'human';       // the dispatcher reordered it

/** Per-train outcome of one simulation run. */
export interface TrainOutcome {
  train: TrainId;
  /** Minutes of delay at the end of the horizon. */
  delay: number;
  /** Position in the passing order this run produced. */
  position: number;
}

export interface SimulationResult {
  /** The passing order that was actually simulated, all trains included. */
  passingOrder: readonly TrainId[];
  outcomes: Readonly<Record<TrainId, TrainOutcome>>;
  /** Sum of all delays in minutes — the KPI the cards report against. */
  totalDelay: number;
  /** Delay weighted by train importance, used for scoring only. */
  weightedDelay: number;
  horizonMinutes: number;
}

/** What one candidate is worth, measured against the baseline run. */
export interface ActionMetrics {
  totalDelay: number;
  /** Baseline total minus this candidate's total. Positive = an improvement. */
  totalDelayReduction: number;
  controlledTrains: number;
  affectedTrains: number;
  /** Per train: minutes gained (negative) or lost (positive) against baseline. */
  trainImpacts: Readonly<Record<TrainId, number>>;
  controlled: readonly TrainId[];
  /** Every train whose delay moved, including the controlled ones. */
  affected: readonly TrainId[];
  /** Neither dispatched nor affected. */
  unchanged: readonly TrainId[];
  confidence: ImpactConfidence;
}

/** A candidate with its metrics and its rank. */
export interface EvaluatedAction {
  action: CombinedAction;
  metrics: ActionMetrics;
  /** Ranking score — see `scoreAction`. */
  score: number;
  /** Set on the single best candidate overall. */
  recommended: boolean;
  result: SimulationResult;
}

/**
 * Ranking knobs, configurable because the trade-off between benefit and how much
 * of the network gets touched is a policy decision, not a fact.
 */
export interface ScoringConfig {
  /** Minutes of benefit each controlled train has to justify. */
  interventionPenalty: number;
  /**
   * Benefit difference under which the smaller intervention wins outright —
   * "minimum intervention for similar benefit". Applied as an explicit rule on
   * top of the penalty so the principle is visible rather than emergent.
   */
  similarBenefitMinutes: number;
}

export const DEFAULT_SCORING: ScoringConfig = {
  interventionPenalty: 0.6,
  similarBenefitMinutes: 2,
};

/** No candidate may dispatch more trains than this. */
export const MAX_CONTROLLED_TRAINS = 4;
/** Fewer than two trains is not a *combined* action. */
export const MIN_CONTROLLED_TRAINS = 2;
/** Upper bound on the internal candidate set before selection. */
export const MAX_CANDIDATES = 30;
