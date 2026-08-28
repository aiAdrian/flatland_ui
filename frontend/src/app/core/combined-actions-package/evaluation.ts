/**
 * Evaluation, ranking and selection.
 *
 * Evaluation turns one simulation run into the numbers a card shows, and — the
 * part that matters conceptually — sorts the trains into controlled, affected and
 * unchanged by comparing the run against the baseline. A train nobody dispatched
 * whose delay moved anyway lands in `affected`, which is the whole claim the
 * feature makes about network-wide effects.
 *
 * Ranking is benefit minus a penalty per controlled train, so a solution that
 * touches half the network has to earn it. On top of that sits the explicit rule
 * the brief asks for: within a small benefit difference, the smaller intervention
 * wins outright. Both are configurable, because how much intervention a minute of
 * delay is worth is a policy question.
 */

import {
  ActionMetrics,
  CombinedAction,
  ConflictWindow,
  DEFAULT_SCORING,
  EvaluatedAction,
  ImpactConfidence,
  ScoringConfig,
  SimulationResult,
  TrainId,
} from './model';

/** Below this the delay change is noise rather than an effect. */
const IMPACT_EPSILON = 0.05;

export function evaluateAction(
  baseline: SimulationResult,
  result: SimulationResult,
  action: CombinedAction,
  window: ConflictWindow,
): ActionMetrics {
  const controlled = [...action.sequence];
  const controlledSet = new Set(controlled);

  const trainImpacts: Record<TrainId, number> = {};
  const affected: TrainId[] = [];
  const unchanged: TrainId[] = [];

  for (const train of window.trains) {
    const before = baseline.outcomes[train.id]?.delay ?? 0;
    const after = result.outcomes[train.id]?.delay ?? 0;
    const impact = round1(after - before);
    trainImpacts[train.id] = impact;
    if (Math.abs(impact) > IMPACT_EPSILON) {
      affected.push(train.id);
    } else if (!controlledSet.has(train.id)) {
      // A controlled train whose delay did not move is still dispatched, so it is
      // not "unchanged" — the operator gave it an instruction.
      unchanged.push(train.id);
    }
  }

  const totalDelayReduction = round1(baseline.totalDelay - result.totalDelay);
  return {
    totalDelay: result.totalDelay,
    totalDelayReduction,
    controlledTrains: controlled.length,
    affectedTrains: affected.length,
    trainImpacts,
    controlled,
    affected,
    unchanged,
    confidence: confidenceFor(totalDelayReduction, controlled.length),
  };
}

/**
 * How firmly the number is offered.
 *
 * Falls with the size of the intervention: the more trains an action re-slots, the
 * more of the outcome rests on the mock's assumptions rather than on the one
 * contended section it actually models.
 */
function confidenceFor(reduction: number, controlled: number): ImpactConfidence {
  if (reduction <= 0) return 'low';
  if (controlled <= 2 && reduction >= 6) return 'high';
  if (controlled <= 3 && reduction >= 8) return 'high';
  if (reduction >= 4) return 'medium';
  return 'low';
}

export function scoreAction(
  metrics: ActionMetrics,
  config: ScoringConfig = DEFAULT_SCORING,
): number {
  return round1(
    metrics.totalDelayReduction - config.interventionPenalty * metrics.controlledTrains,
  );
}

/**
 * Best first.
 *
 * Primary key is the score. The similar-benefit rule then overrides it: when two
 * candidates are within `similarBenefitMinutes` of each other in raw benefit, the
 * one controlling fewer trains wins regardless of score. Without this the penalty
 * alone would let a four-train action edge out a two-train action of practically
 * equal value.
 */
export function rankCombinedActions(
  actions: readonly EvaluatedAction[],
  config: ScoringConfig = DEFAULT_SCORING,
): EvaluatedAction[] {
  return [...actions].sort((a, b) => {
    const benefitGap = Math.abs(
      a.metrics.totalDelayReduction - b.metrics.totalDelayReduction,
    );
    if (benefitGap < config.similarBenefitMinutes) {
      const byIntervention = a.metrics.controlledTrains - b.metrics.controlledTrains;
      if (byIntervention !== 0) return byIntervention;
    }
    if (b.score !== a.score) return b.score - a.score;
    // Stable and readable: more benefit, then fewer trains, then by id.
    if (b.metrics.totalDelayReduction !== a.metrics.totalDelayReduction) {
      return b.metrics.totalDelayReduction - a.metrics.totalDelayReduction;
    }
    if (a.metrics.controlledTrains !== b.metrics.controlledTrains) {
      return a.metrics.controlledTrains - b.metrics.controlledTrains;
    }
    return a.action.id.localeCompare(b.action.id);
  });
}

/**
 * The three best actions, in rank order.
 *
 * Straight off the ranking rather than one per level of intervention. The ranking
 * already carries the preference for the smaller intervention — a bigger one has
 * to earn its extra trains — so taking the top of it yields the best answers
 * without also insisting that every level be represented. Distinct sequences are
 * guaranteed upstream: candidate generation deduplicates them.
 */
export function selectForUi(
  ranked: readonly EvaluatedAction[],
  limit = 3,
): EvaluatedAction[] {
  return [...ranked].slice(0, limit);
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}
