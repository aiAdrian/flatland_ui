/**
 * Primitive translation and the deterministic mock simulation.
 *
 * Two steps, kept apart because only the first one is about railway control and
 * only the second one is a stand-in for Flatland.
 *
 * ## How a sequence becomes an outcome
 *
 * A Combined Action states a priority order for its controlled trains. It does
 * *not* state anything about the others: they keep the slots the timetable gave
 * them. So the passing order is built by re-slotting — the positions the
 * controlled trains occupy in the baseline order are collected, and the action's
 * sequence is written back into exactly those positions. Everything else stays
 * where it was.
 *
 * That is what produces indirect effects without pretending to dispatch anyone
 * else. If a regional service sits between two controlled slots in the timetable,
 * swapping a 4-minute ICE for a 3-minute IC ahead of it changes how long it
 * waits, although no one gave it an instruction.
 *
 * The queue itself is a single-server model: a train at position k waits for the
 * occupancy of everything ahead of it and burns its own slack first.
 *
 *     delay_k = max(0, entryDelay_k + Σ headway_before_k − slack_k)
 *
 * Deterministic by construction — no clocks, no randomness, no state outside the
 * arguments. The same action on the same window always produces the same numbers,
 * which a demo depends on.
 */

import {
  CombinedAction,
  ConflictWindow,
  ControlPrimitive,
  SimulationResult,
  TrainId,
  TrainOutcome,
} from './model';
import { trainFacts } from './scenario';

/**
 * The sequence as control commands: the leader proceeds, everyone else holds
 * until the train ahead of it has cleared.
 *
 * Mocked, and the shape is the point: replacing the two literal commands with
 * real interlocking primitives should not touch anything else.
 */
export function translateCombinedActionToPrimitives(
  action: CombinedAction,
  window: ConflictWindow,
): ControlPrimitive[] {
  return action.sequence.map((train, index) => {
    // Fail loudly on a train that is not in the window — a sequence referring to
    // a train outside the conflict is a bug, not a degraded case.
    trainFacts(window, train);
    return {
      train,
      command: index === 0 ? 'proceed' : 'hold',
      after: index === 0 ? null : action.sequence[index - 1],
      position: index + 1,
    };
  });
}

/** A working copy of the window, so applying an action cannot mutate the state. */
export function cloneState(window: ConflictWindow): ConflictWindow {
  return {
    ...window,
    trains: window.trains.map((t) => ({ ...t })),
    baselineOrder: [...window.baselineOrder],
  };
}

/**
 * The passing order an action produces: the controlled trains take the section
 * first, in the order the action states, and everyone else follows in unchanged
 * timetable order.
 *
 * That is what "priority sequence through the conflict area" means operationally,
 * and it is exactly what the hold/proceed primitives express — whoever is not in
 * the block waits for the block to clear. Nothing has passed the section yet in
 * this window, so there is no one to leave ahead of it.
 *
 * The consequence is deliberate and is the point of the feature: a train nobody
 * dispatched can end up worse off because the block went ahead of it. The
 * evaluation reports that as an indirect effect rather than hiding it.
 */
export function applyCombinedAction(
  window: ConflictWindow,
  action: CombinedAction,
): TrainId[] {
  const controlled = new Set(action.sequence);
  const behind = window.baselineOrder.filter((t) => !controlled.has(t));
  return [...action.sequence, ...behind];
}

/** Run the single-server queue over a passing order. */
function runQueue(
  window: ConflictWindow,
  passingOrder: readonly TrainId[],
): SimulationResult {
  const outcomes: Record<TrainId, TrainOutcome> = {};
  let occupied = 0;
  let totalDelay = 0;
  let weightedDelay = 0;

  passingOrder.forEach((train, index) => {
    const facts = trainFacts(window, train);
    const delay = Math.max(0, facts.entryDelay + occupied - facts.slack);
    outcomes[train] = { train, delay, position: index + 1 };
    totalDelay += delay;
    weightedDelay += facts.weight * delay;
    occupied += facts.headway;
  });

  return {
    passingOrder: [...passingOrder],
    outcomes,
    totalDelay: round1(totalDelay),
    weightedDelay: round1(weightedDelay),
    horizonMinutes: window.horizonMinutes,
  };
}

/** Do nothing: the timetable order, which is what the non-controlled trains follow. */
export function simulateBaseline(window: ConflictWindow): SimulationResult {
  return runQueue(window, window.baselineOrder);
}

/** Apply one Combined Action to a copy of the state and run the horizon. */
export function simulateCombinedAction(
  window: ConflictWindow,
  action: CombinedAction,
): SimulationResult {
  const state = cloneState(window);
  // Translated for its own sake: the primitives are what a real controller would
  // receive, and generating them here keeps the two paths from diverging.
  translateCombinedActionToPrimitives(action, state);
  return runQueue(state, applyCombinedAction(state, action));
}

/** One line of the operational plan: what happens to one train, and why. */
export interface PlanStep {
  train: TrainId;
  /** Position in the resulting passing order, 1-based. */
  position: number;
  /** Whether the action dispatches this train or leaves it to the timetable. */
  role: 'controlled' | 'baseline';
  command: 'proceed' | 'hold';
  /** The train it waits for. Null for whoever goes first. */
  after: TrainId | null;
  /** Minutes it stands at the section before entering. */
  waitMinutes: number;
  /** Delay under the timetable, and under this action. */
  delayBefore: number;
  delayAfter: number;
}

/**
 * The plan behind an action, train by train — the "how" the numbers summarise.
 *
 * The dispatcher confirming an action is accountable for what it does to trains
 * they did not touch, so the steps cover the whole passing order, not only the
 * controlled block. `waitMinutes` is the occupancy accumulated ahead of the train,
 * which is what it physically stands still for.
 */
export function planSteps(
  window: ConflictWindow,
  action: CombinedAction,
  result: SimulationResult,
  baseline: SimulationResult,
): PlanStep[] {
  const controlled = new Set(action.sequence);
  let occupied = 0;
  return result.passingOrder.map((train, index) => {
    const facts = trainFacts(window, train);
    const wait = occupied;
    occupied += facts.headway;
    return {
      train,
      position: index + 1,
      role: controlled.has(train) ? 'controlled' : 'baseline',
      command: index === 0 ? 'proceed' : 'hold',
      after: index === 0 ? null : result.passingOrder[index - 1],
      waitMinutes: round1(wait),
      delayBefore: baseline.outcomes[train]?.delay ?? 0,
      delayAfter: result.outcomes[train]?.delay ?? 0,
    };
  });
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}
