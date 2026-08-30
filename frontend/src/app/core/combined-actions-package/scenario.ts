/**
 * The mocked network state and the conflict detected in it.
 *
 * Replacing this file with a reader over the live Flatland session is the first
 * step towards a real version: nothing downstream knows where a
 * {@link ConflictWindow} came from.
 */

import { ConflictWindow, TrainFacts, TrainId } from './model';

/**
 * The six trains contending for one single-track section.
 *
 * The numbers are chosen so the situation has a genuine trade-off rather than one
 * obvious answer: ICE_42 is the heaviest but also the slowest through the section,
 * EC_91 arrives latest, and the two regional services are cheap to hold but block
 * the section for almost as long as an ICE.
 */
const TRAINS: readonly TrainFacts[] = [
  // Generous recovery time: it absorbs a few minutes of waiting without arriving
  // late at all, which is what lets an action leave it genuinely unchanged.
  { id: 'ICE_42', service: 'ICE', weight: 1.0, entryDelay: 4, headway: 4, slack: 9, agentHandle: 0 },
  { id: 'IC_703', service: 'InterCity', weight: 0.85, entryDelay: 6, headway: 3, slack: 2, agentHandle: 1 },
  { id: 'EC_91', service: 'EuroCity', weight: 0.85, entryDelay: 8, headway: 3, slack: 2, agentHandle: 2 },
  { id: 'RE_18', service: 'RegionalExpress', weight: 0.5, entryDelay: 3, headway: 3, slack: 7, agentHandle: 3 },
  // The two that suffer most under first-come-first-served: short trains stuck
  // behind long ones, with almost no slack to absorb it.
  { id: 'RB_51', service: 'RegionalBahn', weight: 0.35, entryDelay: 5, headway: 3, slack: 1, agentHandle: 4 },
  { id: 'S8_214', service: 'S-Bahn', weight: 0.3, entryDelay: 6, headway: 2, slack: 1, agentHandle: 5 },
];

/**
 * The order the timetable sends them in — first come, first served, which is a
 * measurably poor order.
 *
 * It leads with the two trains that occupy the section longest, so everything
 * behind them piles up: the S-Bahn, which needs the section for two minutes,
 * waits behind sixteen minutes of long-distance traffic. Doing nothing is a real
 * option here and a bad one, which is what makes the conflict worth dispatching.
 *
 * An earlier fixture had the short services first. That is close to
 * shortest-occupancy-first, which is optimal for total delay at a single-server
 * queue — so no action could improve on it by more than a minute or two, and the
 * whole demo had nothing to show.
 */
const BASELINE_ORDER: readonly TrainId[] = [
  'ICE_42',
  'EC_91',
  'RE_18',
  'IC_703',
  'RB_51',
  'S8_214',
];

export const CONFLICT_WINDOW: ConflictWindow = {
  id: 'conflict_nord',
  location: 'Einfahrt Nord, eingleisiger Abschnitt',
  reason: 'Sechs Züge beanspruchen denselben Abschnitt innerhalb von 30 Minuten.',
  horizonMinutes: 30,
  trains: TRAINS,
  baselineOrder: BASELINE_ORDER,
};

/**
 * The conflict the demo starts from.
 *
 * A single fixture today. The signature is the one a detector would have, so the
 * caller does not have to change when conflicts start being found rather than
 * declared: only trains inside the spatial and temporal window are candidates,
 * and here the window *is* the fixture.
 */
export function detectConflict(): ConflictWindow {
  return CONFLICT_WINDOW;
}

export function trainFacts(window: ConflictWindow, train: TrainId): TrainFacts {
  const found = window.trains.find((t) => t.id === train);
  if (!found) {
    throw new Error(`Train ${train} is not part of conflict ${window.id}`);
  }
  return found;
}

export function serviceOf(window: ConflictWindow, train: TrainId): string {
  return window.trains.find((t) => t.id === train)?.service ?? 'Zug';
}
