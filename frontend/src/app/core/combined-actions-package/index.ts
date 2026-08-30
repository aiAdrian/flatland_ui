/**
 * Combined Actions — the public API, and the pipeline that wires it together.
 *
 *     conflict → candidates → simulate each → evaluate → rank → select
 *
 * Every stage is a separate module and none of them knows about Angular, so each
 * can be swapped independently: candidate generation for an optimiser or a MARL
 * policy, the simulation for Flatland, the scoring for real railway KPIs. The UI
 * reads {@link EvaluatedAction} and nothing else.
 */

import {
  CandidateStrategy,
  CombinedAction,
  ConflictWindow,
  DEFAULT_SCORING,
  EvaluatedAction,
  MAX_CANDIDATES,
  MAX_CONTROLLED_TRAINS,
  MIN_CONTROLLED_TRAINS,
  ScoringConfig,
  TrainId,
} from './model';
import { detectConflict, trainFacts } from './scenario';
import { simulateBaseline, simulateCombinedAction } from './simulation';
import {
  evaluateAction,
  rankCombinedActions,
  scoreAction,
  selectForUi,
} from './evaluation';

export * from './model';
export { CONFLICT_WINDOW, detectConflict, serviceOf, trainFacts } from './scenario';
export {
  applyCombinedAction,
  cloneState,
  planSteps,
  simulateBaseline,
  simulateCombinedAction,
  translateCombinedActionToPrimitives,
} from './simulation';
export type { PlanStep } from './simulation';
export {
  evaluateAction,
  rankCombinedActions,
  scoreAction,
  selectForUi,
} from './evaluation';

/** Subsets of the window's trains, in a fixed order, up to the size cap. */
function subsets(trains: readonly TrainId[], size: number): TrainId[][] {
  if (size === 0) return [[]];
  if (trains.length < size) return [];
  const [head, ...rest] = trains;
  return [
    ...subsets(rest, size - 1).map((s) => [head, ...s]),
    ...subsets(rest, size),
  ];
}

/**
 * Ordering rules used to turn a subset into a candidate.
 *
 * Four rules rather than all permutations: a six-train window has 1950 ordered
 * subsets of size two to four, and enumerating them would buy nothing — the
 * interesting orders are the ones a dispatcher would actually argue about.
 */
const ORDER_RULES: readonly {
  strategy: CandidateStrategy;
  order: (window: ConflictWindow, subset: readonly TrainId[]) => TrainId[];
}[] = [
  {
    strategy: 'ratio',
    order: (w, s) =>
      [...s].sort((a, b) => {
        const fa = trainFacts(w, a);
        const fb = trainFacts(w, b);
        return fb.weight / fb.headway - fa.weight / fa.headway;
      }),
  },
  {
    strategy: 'most-delayed',
    order: (w, s) =>
      [...s].sort((a, b) => trainFacts(w, b).entryDelay - trainFacts(w, a).entryDelay),
  },
  {
    strategy: 'heaviest',
    order: (w, s) =>
      [...s].sort((a, b) => trainFacts(w, b).weight - trainFacts(w, a).weight),
  },
  {
    strategy: 'timetable',
    order: (w, s) => w.baselineOrder.filter((t) => s.includes(t)),
  },
];

/**
 * Candidates for one conflict: for every subset of two to four trains, one
 * candidate per ordering rule, deduplicated and capped.
 *
 * Deterministic in order and content, so the same conflict always yields the same
 * candidate set — the ranking below would otherwise be unstable between runs.
 */
export function generateCombinedActions(
  window: ConflictWindow,
): CombinedAction[] {
  // Worst-off first. With a budget per level, the order subsets are enumerated in
  // decides which ones are reachable at all, so it should start with the trains
  // that are actually suffering under the timetable — a candidate that ignores
  // them cannot help much.
  const baseline = simulateBaseline(window);
  const ids = window.trains
    .map((t) => t.id)
    .sort(
      (a, b) =>
        (baseline.outcomes[b]?.delay ?? 0) - (baseline.outcomes[a]?.delay ?? 0),
    );
  const sizes: number[] = [];
  for (let s = MIN_CONTROLLED_TRAINS; s <= MAX_CONTROLLED_TRAINS; s++) sizes.push(s);

  // A budget per level, not one shared cap. A shared cap is spent entirely on the
  // smallest subsets — six trains already give fifteen pairs — and the three- and
  // four-train levels would never be generated at all, which is precisely what
  // the dispatcher is supposed to be able to compare.
  const perSize = Math.max(1, Math.floor(MAX_CANDIDATES / sizes.length));
  const seen = new Set<string>();
  const out: CombinedAction[] = [];

  for (const size of sizes) {
    let taken = 0;
    for (const subset of subsets(ids, size)) {
      if (taken >= perSize) break;
      for (const rule of ORDER_RULES) {
        if (taken >= perSize) break;
        const sequence = rule.order(window, subset);
        const key = sequence.join('>');
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({
          id: `cand_${size}_${out.length + 1}`,
          sequence,
          strategy: rule.strategy,
        });
        taken++;
      }
    }
  }
  return out;
}

/** One candidate, simulated and evaluated against a baseline run. */
export function evaluateCandidate(
  window: ConflictWindow,
  action: CombinedAction,
  baseline = simulateBaseline(window),
  config: ScoringConfig = DEFAULT_SCORING,
): EvaluatedAction {
  const result = simulateCombinedAction(window, action);
  const metrics = evaluateAction(baseline, result, action, window);
  return {
    action,
    metrics,
    result,
    score: scoreAction(metrics, config),
    recommended: false,
  };
}

export interface CombinedActionProposal {
  window: ConflictWindow;
  baseline: ReturnType<typeof simulateBaseline>;
  /** What the dispatcher is offered, one per level of intervention. */
  offered: EvaluatedAction[];
  /** How many candidates were generated and evaluated to get there. */
  consideredCount: number;
}

/**
 * The whole pipeline: detect, generate, simulate, evaluate, rank, select.
 *
 * The single best candidate overall is marked `recommended` — which is not
 * necessarily the first card, because the cards are ordered by how much they
 * intervene so the levels can be compared.
 */
export function proposeCombinedActions(
  window: ConflictWindow = detectConflict(),
  config: ScoringConfig = DEFAULT_SCORING,
): CombinedActionProposal {
  const baseline = simulateBaseline(window);
  const candidates = generateCombinedActions(window);
  const evaluated = candidates.map((c) =>
    evaluateCandidate(window, c, baseline, config),
  );
  const ranked = rankCombinedActions(evaluated, config);
  const offered = selectForUi(ranked);

  const best = ranked[0];
  for (const candidate of offered) {
    candidate.recommended = best !== undefined && candidate.action.id === best.action.id;
  }
  // The best overall must be on screen, or the badge would point at nothing.
  if (best && !offered.some((c) => c.action.id === best.action.id)) {
    best.recommended = true;
    offered.push(best);
  }

  return {
    window,
    baseline,
    offered,
    consideredCount: candidates.length,
  };
}

/**
 * Re-evaluate a sequence the dispatcher reordered.
 *
 * Deliberately not a re-run of candidate generation: the dispatcher edited *this*
 * action, and regenerating would replace it with something else. Same state, same
 * baseline, same simulator — only the sequence differs.
 */
export function evaluateModifiedAction(
  window: ConflictWindow,
  original: CombinedAction,
  sequence: readonly TrainId[],
  config: ScoringConfig = DEFAULT_SCORING,
): EvaluatedAction {
  return evaluateCandidate(
    window,
    { id: `${original.id}_human`, sequence: [...sequence], strategy: 'human' },
    simulateBaseline(window),
    config,
  );
}

/** How long a recalculation is shown as pending, so the causal chain reads. */
export const PREDICTION_LATENCY_MS = 420;
