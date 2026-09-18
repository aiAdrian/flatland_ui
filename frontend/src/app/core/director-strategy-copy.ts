import { DirectorFocus } from './api.service';
import { DecisionValueAxis } from './decision-log';

/** Copy for the three strategy focuses the Director offers as A/B/C tiles,
 *  as translation keys. Kept out of the component so the wording can be
 *  reviewed on its own and reused by the reflection surfaces (a chosen focus is
 *  preference evidence, and the operator model speaks the same three axes).
 *  The text lives in public/i18n/*.json (i18n plan, phase 3).
 *
 *  `gives` / `costs` name the trade-off explicitly: every focus wins on its own
 *  axis and pays somewhere else. No focus is dominated — otherwise the choice
 *  would be a quality ranking, not a decision about values. */
export interface StrategyCopy {
  /** Translation keys, resolved where the tile is rendered. */
  title: string;
  /** One line: what this focus optimises for. */
  goal: string;
  gives: string;
  costs: string;
}

export const FOCUS_LABEL: Record<DirectorFocus, string> = {
  punctuality: 'strategy.focus.punctuality',
  connections: 'strategy.focus.connections',
  stability: 'strategy.focus.stability',
};

export const STRATEGY_COPY: Record<DirectorFocus, StrategyCopy> = {
  punctuality: {
    title: 'strategy.copy.punctuality.title',
    goal: 'strategy.copy.punctuality.goal',
    gives: 'strategy.copy.punctuality.gives',
    costs: 'strategy.copy.punctuality.costs',
  },
  connections: {
    title: 'strategy.copy.connections.title',
    goal: 'strategy.copy.connections.goal',
    // Deliberately an intent, not a promise. The acceptance sweep (12 scenarios,
    // every row verified by a full episode — director-mode.md §8) shows the
    // connections dial is the weakest lever: 0.736 kept vs 0.753 for the
    // conflict-blind baseline, at 15 more delay. Punctuality and stability do win
    // on their own axis; this one does not yet, so the tile says what it
    // prioritises and lets the measured delta and "Nachspielen" speak.
    gives: 'strategy.copy.connections.gives',
    costs: 'strategy.copy.connections.costs',
  },
  stability: {
    title: 'strategy.copy.stability.title',
    goal: 'strategy.copy.stability.goal',
    gives: 'strategy.copy.stability.gives',
    costs: 'strategy.copy.stability.costs',
  },
};

/** Focus order for the axis rows, so every tile reads the same way. */
export const FOCUS_ORDER: DirectorFocus[] = ['punctuality', 'connections', 'stability'];

/** The operator model speaks 'connection' (singular) where a dial says
 *  'connections'. One place for that translation. */
export const VALUE_AXIS_BY_FOCUS: Record<DirectorFocus, DecisionValueAxis> = {
  punctuality: 'punctuality',
  connections: 'connection',
  stability: 'stability',
};

/** The reverse direction, for marking the tile a learned preference points at.
 *  'throughput' is deliberately absent: the Director offers no throughput
 *  preset, so a throughput-first profile marks nothing rather than being
 *  rounded onto the nearest tile. */
export const FOCUS_BY_VALUE_AXIS: Partial<Record<DecisionValueAxis, DirectorFocus>> = {
  punctuality: 'punctuality',
  connection: 'connections',
  stability: 'stability',
};

/**
 * The preference hypothesis a strategy choice suggests — a template, not an
 * LLM, and phrased as a hypothesis because one choice is not a rule yet.
 *
 * Naming the price is the point: "you prefer connections" is cheap, "you prefer
 * connections even at −31 punctuality" is a statement the operator can actually
 * agree or object to.
 */
export function strategyHypothesis(
  focus: DirectorFocus,
  tradedAway: string | null,
  t: (key: string, params?: Record<string, unknown>) => string,
): string {
  const goal = t(FOCUS_LABEL[focus]);
  return tradedAway
    ? t('strategy.hypothesisCost', { goal, cost: tradedAway })
    : t('strategy.hypothesis', { goal });
}
