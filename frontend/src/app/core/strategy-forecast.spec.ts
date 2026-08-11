import { ScenarioOption } from './events/event-types';
import {
  buildForecastFromSignals,
  buildStrategyForecast,
  openProblemsFrom,
  reliableColumns,
  signalsFromFocusDelta,
} from './strategy-forecast';

function option(overrides: Partial<ScenarioOption> = {}): ScenarioOption {
  return {
    id: 'opt-a',
    title: 'Anschluss halten',
    description: '',
    kpiDelta: {},
    kpiDeltas: { totalDelay: 0, deadlocks: 0, done: 0, meanDelay: 0, episodeSteps: 0, episodeFinished: false },
    ...overrides,
  } as ScenarioOption;
}

describe('reliableColumns', () => {
  it('sees the full 30 minutes while at most one problem is open', () => {
    expect(reliableColumns(0)).toBe(4);
    expect(reliableColumns(1)).toBe(4);
  });

  it('shrinks the horizon as problems pile up', () => {
    expect(reliableColumns(2)).toBe(3);
    expect(reliableColumns(3)).toBe(2);
    expect(reliableColumns(7)).toBe(1); // only "now" is trustworthy
  });
});

describe('openProblemsFrom', () => {
  it('counts leftover deadlocks plus delayed trains', () => {
    const o = option({ kpis: { totalDelay: 0, deadlocks: 2, done: 3, meanDelay: 0, episodeSteps: 0, episodeFinished: false } });
    expect(openProblemsFrom(o, 3)).toBe(5);
  });

  it('never goes negative', () => {
    const o = option({ kpis: { totalDelay: 0, deadlocks: -1, done: 0, meanDelay: 0, episodeSteps: 0, episodeFinished: false } });
    expect(openProblemsFrom(o, -2)).toBe(0);
  });

  it('handles a missing option', () => {
    expect(openProblemsFrom(undefined, 1)).toBe(1);
  });
});

describe('buildStrategyForecast', () => {
  it('produces three rows over four columns', () => {
    const fc = buildStrategyForecast(option(), 0);
    expect(fc.columns.length).toBe(4);
    expect(fc.rows.length).toBe(3);
    fc.rows.forEach((r) => expect(r.cells.length).toBe(4));
  });

  it('keeps the full horizon when little is open', () => {
    const fc = buildStrategyForecast(option(), 0);
    expect(fc.reliableColumns).toBe(4);
    expect(fc.horizonMinutes).toBe(30);
    expect(fc.columns.every((c) => c.confidence !== 'unknown')).toBeTrue();
  });

  it('greys out the far future when several problems are open', () => {
    const fc = buildStrategyForecast(option(), 3);
    expect(fc.horizonMinutes).toBe(10);
    expect(fc.columns[3].confidence).toBe('unknown');
    expect(fc.columns[2].confidence).toBe('unknown');
    fc.rows.forEach((r) => {
      expect(r.cells[3].level).toBe('unknown');
      expect(r.cells[3].label).toBe('unklar');
    });
    // the near term stays readable
    expect(fc.rows[0].cells[0].level).not.toBe('unknown');
  });

  it('shows connections as lost when the option reduces arrivals', () => {
    const fc = buildStrategyForecast(
      option({ kpiDeltas: { totalDelay: 0, deadlocks: 0, done: -2, meanDelay: 0, episodeSteps: 0, episodeFinished: false } }),
      0,
    );
    const connections = fc.rows[1];
    expect(connections.cells[2].label).toBe('verloren');
    expect(connections.cells[2].level).toBe('bad');
  });

  it('shows connections as kept when arrivals hold', () => {
    const fc = buildStrategyForecast(option(), 0);
    expect(fc.rows[1].cells[1].label).toBe('gehalten');
    expect(fc.rows[1].cells[1].level).toBe('good');
  });

  it('marks the delay side effect when the option adds delay', () => {
    const fc = buildStrategyForecast(
      option({ kpiDeltas: { totalDelay: 30, deadlocks: 0, done: 0, meanDelay: 4, episodeSteps: 0, episodeFinished: false } }),
      0,
    );
    expect(fc.rows[2].cells[0].label).toBe('steigt');
    expect(fc.rows[2].cells[3].level).toBe('bad');
  });

  it('keeps the conflict unresolved when the option adds deadlocks', () => {
    const fc = buildStrategyForecast(
      option({ kpiDeltas: { totalDelay: 0, deadlocks: 2, done: 0, meanDelay: 0, episodeSteps: 0, episodeFinished: false } }),
      0,
    );
    expect(fc.rows[0].cells[2].label).toBe('offen');
  });

  it('survives a missing option', () => {
    const fc = buildStrategyForecast(undefined, 0);
    expect(fc.rows.length).toBe(3);
  });

  // ── Director strategy focus as the subject ──────────────────────────────
  // Same table, different subject: a focus is described by how it changes the
  // three axes against the plan currently driving.

  it('reads a focus that buys its goal with delay', () => {
    const signals = signalsFromFocusDelta({
      punctuality: -0.2,
      connections: 0.1,
      stability: 0,
    });
    expect(signals).toEqual({ addsDelay: true, keepsConnections: true, addsRipple: false });

    const fc = buildForecastFromSignals(signals, 0);
    expect(fc.rows[2].cells[0].label).toBe('steigt');
    expect(fc.rows[1].cells[1].label).toBe('gehalten');
    expect(fc.rows[0].cells[3].label).toBe('stabil');
  });

  it('reads a focus that gives up stability as raising the knock-on risk', () => {
    const signals = signalsFromFocusDelta({
      punctuality: 0.05,
      connections: -0.1,
      stability: -0.3,
    });
    expect(signals).toEqual({ addsDelay: false, keepsConnections: false, addsRipple: true });

    const fc = buildForecastFromSignals(signals, 0);
    expect(fc.rows[0].cells[2].label).toBe('offen');
    expect(fc.rows[1].cells[2].label).toBe('verloren');
  });

  it('treats an unchanged axis as no regression', () => {
    expect(signalsFromFocusDelta({ punctuality: 0, connections: 0, stability: 0 })).toEqual({
      addsDelay: false,
      keepsConnections: true,
      addsRipple: false,
    });
  });

  it('shrinks the horizon for an explicit subject too', () => {
    const fc = buildForecastFromSignals(
      { addsDelay: false, keepsConnections: true, addsRipple: false },
      3,
    );
    expect(fc.horizonMinutes).toBe(10);
    expect(fc.rows[0].cells[3].label).toBe('unklar');
  });
});
