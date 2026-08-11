import { ScenarioOption } from './events/event-types';

/**
 * Strategy Impact Forecast — "what will this option do over the next half hour?"
 *
 * Ported from the Director-Mode Reflection Playground prototype: three rows
 * (the conflict itself, the primary goal, the side effect) across four columns
 * (Now / +10 / +20 / +30 min), each cell a coloured state chip.
 *
 * Two honest limits, deliberately visible in the UI:
 *  - It is a **rule-based projection** from the option's KPI deltas, not a
 *    re-simulation of the next 30 minutes.
 *  - Its **reliable horizon shrinks with system load**: with several problems
 *    open at once the far columns turn 'unknown' instead of pretending to know.
 *    Stabilising decisions widen the horizon again — the coupling that makes
 *    "the future gets murkier the more I let pile up" visible.
 */

export type ForecastLevel = 'good' | 'fair' | 'bad' | 'unknown';
export type ForecastConfidence = 'high' | 'medium' | 'lower' | 'unknown';

export interface ForecastCell {
  label: string;
  level: ForecastLevel;
}

export interface ForecastColumn {
  label: string;
  confidence: ForecastConfidence;
}

export interface ForecastRow {
  icon: string;
  label: string;
  cells: ForecastCell[];
}

export interface StrategyForecast {
  columns: ForecastColumn[];
  rows: ForecastRow[];
  /** How many of the four columns are trustworthy (1..4). */
  reliableColumns: number;
  /** Minutes the forecast is reliable for (0, 10, 20 or 30). */
  horizonMinutes: number;
  /** Concurrently open problems the horizon was derived from. */
  openProblems: number;
}

/**
 * The three yes/no facts the table actually needs. Extracted so the same
 * visual can describe different subjects honestly: a scenario option (its KPI
 * deltas) or a Director strategy focus (its per-axis deltas against the plan
 * currently driving). Without this split the Director centre showed a forecast
 * headed with a *policy* name while the tiles above it offered *objectives* —
 * two mental models in one glance, and the policy was not even the one driving.
 */
export interface ForecastSignals {
  addsDelay: boolean;
  keepsConnections: boolean;
  addsRipple: boolean;
}

/** Reliable columns by number of concurrently open problems. */
const RELIABLE_BY_LOAD: Record<number, number> = { 0: 4, 1: 4, 2: 3, 3: 2 };

export function reliableColumns(openProblems: number): number {
  return RELIABLE_BY_LOAD[openProblems] ?? 1;
}

const cell = (label: string, level: ForecastLevel): ForecastCell => ({ label, level });

/**
 * Count what is currently open and unresolved: deadlocks the option leaves
 * behind plus trains that are late. This is the "system load" that governs how
 * far ahead the forecast can be trusted.
 */
export function openProblemsFrom(option: ScenarioOption | undefined, delayedTrains = 0): number {
  const deadlocks = Math.max(0, option?.kpis?.deadlocks ?? 0);
  return deadlocks + Math.max(0, delayedTrains);
}

/**
 * Build the forecast for one option.
 *
 * @param option        the scenario option being previewed / recommended
 * @param openProblems  concurrently open problems (see `openProblemsFrom`)
 */
export function buildStrategyForecast(
  option: ScenarioOption | undefined,
  openProblems = 0,
): StrategyForecast {
  const meanDelay = option?.kpiDeltas?.meanDelay ?? null;
  const done = option?.kpiDeltas?.done ?? null;
  const deadlocks = option?.kpiDeltas?.deadlocks ?? null;

  return buildForecastFromSignals(
    {
      addsDelay: meanDelay != null && meanDelay > 0,
      keepsConnections: done != null && done >= 0,
      addsRipple: deadlocks != null && deadlocks > 0,
    },
    openProblems,
  );
}

/**
 * Signals for a Director strategy focus, read off its per-axis change against
 * the plan currently driving. The mapping needs no invention: the axes *are*
 * punctuality, connections and stability.
 *
 * - scores worse on punctuality → this focus buys its goal with delay
 * - keeps or improves connections → transfers hold
 * - gives up stability → less headroom, so knock-on conflicts are likelier
 */
export function signalsFromFocusDelta(delta: {
  punctuality: number;
  connections: number;
  stability: number;
}): ForecastSignals {
  return {
    addsDelay: delta.punctuality < 0,
    keepsConnections: delta.connections >= 0,
    addsRipple: delta.stability < 0,
  };
}

export function buildForecastFromSignals(
  signals: ForecastSignals,
  openProblems = 0,
): StrategyForecast {
  const { addsDelay, keepsConnections, addsRipple } = signals;

  const columns: ForecastColumn[] = [
    { label: 'Jetzt', confidence: 'high' },
    { label: '+10 min', confidence: 'high' },
    { label: '+20 min', confidence: 'medium' },
    { label: '+30 min', confidence: 'lower' },
  ];

  // Row 1 — the conflict this option resolves.
  const conflictRow: ForecastRow = {
    icon: '⚠️',
    label: 'Konflikt',
    cells: addsRipple
      ? [cell('aktiv', 'bad'), cell('aktiv', 'bad'), cell('offen', 'fair'), cell('unklar', 'fair')]
      : [cell('aktiv', 'bad'), cell('löst sich', 'fair'), cell('gelöst', 'good'), cell('stabil', 'good')],
  };

  // Row 2 — the primary goal: are the connections kept?
  const goalRow: ForecastRow = {
    icon: '🔗',
    label: 'Anschlüsse',
    cells: keepsConnections
      ? [cell('gefährdet', 'bad'), cell('gehalten', 'good'), cell('gehalten', 'good'), cell('gehalten', 'good')]
      : [cell('gefährdet', 'bad'), cell('gefährdet', 'bad'), cell('verloren', 'bad'), cell('verloren', 'bad')],
  };

  // Row 3 — the side effect: delay / network load.
  const sideRow: ForecastRow = {
    icon: '🌊',
    // Short on purpose: this table has to survive in a 333px column.
    label: 'Netzlast',
    cells: addsDelay
      ? [cell('steigt', 'fair'), cell('steigt', 'fair'), cell('hoch', 'bad'), cell('hoch', 'bad')]
      : [cell('niedrig', 'good'), cell('niedrig', 'good'), cell('niedrig', 'good'), cell('stabil', 'good')],
  };

  const rows = [conflictRow, goalRow, sideRow];

  // Beyond the reliable horizon the future is unknown — say so.
  const reliable = reliableColumns(openProblems);
  for (let i = reliable; i < columns.length; i++) {
    columns[i].confidence = 'unknown';
    for (const row of rows) row.cells[i] = cell('unklar', 'unknown');
  }

  return {
    columns,
    rows,
    reliableColumns: reliable,
    horizonMinutes: Math.max(0, (reliable - 1) * 10),
    openProblems,
  };
}
