import { DecisionLogEntry } from './decision-log';
import {
  MAX_REFLECTION_MOMENTS,
  scoreMoment,
  selectReflectionMoments,
} from './reflection-moments';

let seq = 0;
function entry(overrides: Partial<DecisionLogEntry> = {}): DecisionLogEntry {
  seq += 1;
  return {
    seq,
    t: seq * 1000,
    simStep: seq,
    mode: 'co-learning',
    handle: 0,
    accountableOwner: 'human',
    action: 'accept',
    aiSuggestion: 'Hold train 3',
    decisionTimeMs: 900,
    ...overrides,
  };
}

beforeEach(() => (seq = 0));

describe('scoreMoment', () => {
  it('gives a silent accept no score', () => {
    const log = [entry()];
    const m = scoreMoment(log, 0);
    expect(m.score).toBe(0);
    expect(m.caseType).toBe('passive_accept');
  });

  it('scores an override above a merely reasoned accept', () => {
    const override = scoreMoment([entry({ action: 'override' })], 0);
    const reasoned = scoreMoment([entry({ rationale: 'Schützt Anschluss' })], 0);
    expect(override.score).toBeGreaterThan(reasoned.score);
    expect(override.caseType).toBe('override');
    expect(reasoned.caseType).toBe('reasoned');
  });

  it('flags an AI-applied decision as over-reliance signal', () => {
    const m = scoreMoment([entry({ accountableOwner: 'ai', action: 'hold' })], 0);
    expect(m.caseType).toBe('deferred_to_ai');
    expect(m.score).toBe(3);
  });

  it('scores a confirmed preference', () => {
    const m = scoreMoment(
      [entry({ rationale: 'Schützt Anschluss', hypothesisResponse: 'yes' })],
      0,
    );
    expect(m.caseType).toBe('confirmed_preference');
    expect(m.score).toBe(5); // +3 confirmed, +2 reason
  });

  it('detects a deviation from the operators own habit', () => {
    const log = [
      entry({ rationale: 'Schützt Anschluss' }),
      entry({ rationale: 'Schützt Anschluss' }),
      entry({ rationale: 'Geringe Zusatzverspätung' }), // the break
    ];
    const m = scoreMoment(log, 2);
    expect(m.caseType).toBe('pattern_deviation');
    expect(m.expectedAxis).toBe('connection');
    expect(m.axis).toBe('punctuality');
    expect(m.score).toBeGreaterThanOrEqual(7); // +5 deviation, +2 reason
  });

  it('needs at least two prior decisions before calling something a habit', () => {
    const log = [
      entry({ rationale: 'Schützt Anschluss' }),
      entry({ rationale: 'Geringe Zusatzverspätung' }),
    ];
    expect(scoreMoment(log, 1).caseType).not.toBe('pattern_deviation');
    expect(scoreMoment(log, 1).expectedAxis).toBeNull();
  });

  it('ignores passive decisions when learning the habit', () => {
    const log = [
      entry({ rationale: 'Schützt Anschluss', accountableOwner: 'ai' }),
      entry({ rationale: 'Schützt Anschluss', accountableOwner: 'ai' }),
      entry({ rationale: 'Geringe Zusatzverspätung' }),
    ];
    // the two AI-owned entries are not the operator's habit
    expect(scoreMoment(log, 2).expectedAxis).toBeNull();
  });
});

describe('selectReflectionMoments', () => {
  it('returns nothing for an empty log', () => {
    expect(selectReflectionMoments([])).toEqual([]);
  });

  it('skips decisions with no signal at all', () => {
    const log = [entry(), entry(), entry()];
    expect(selectReflectionMoments(log)).toEqual([]);
  });

  it('never returns more than the cap', () => {
    const log = Array.from({ length: 10 }, () => entry({ action: 'override' }));
    expect(selectReflectionMoments(log).length).toBe(MAX_REFLECTION_MOMENTS);
  });

  it('prefers a diverse set of case types over three of a kind', () => {
    const log = [
      entry({ action: 'override' }),
      entry({ action: 'override' }),
      entry({ accountableOwner: 'ai', action: 'hold' }),
      entry({ rationale: 'Schützt Anschluss', hypothesisResponse: 'yes' }),
    ];
    const types = selectReflectionMoments(log).map((m) => m.caseType);
    expect(new Set(types).size).toBe(3);
  });

  it('excludes system holds (attributed to neither party)', () => {
    const log = [entry({ accountableOwner: 'system', action: 'hold' })];
    expect(selectReflectionMoments(log)).toEqual([]);
  });

  it('returns the picked moments in chronological order', () => {
    const log = [
      entry({ rationale: 'Schützt Anschluss' }),
      entry({ action: 'override' }),
      entry({ accountableOwner: 'ai', action: 'hold' }),
    ];
    const seqs = selectReflectionMoments(log).map((m) => m.entry.seq);
    expect(seqs).toEqual([...seqs].sort((a, b) => a - b));
  });

  it('picks the pattern deviation first when one exists', () => {
    const log = [
      entry({ rationale: 'Schützt Anschluss' }),
      entry({ rationale: 'Schützt Anschluss' }),
      entry({ rationale: 'Geringe Zusatzverspätung' }), // deviation
      entry({ accountableOwner: 'ai', action: 'hold' }),
    ];
    const types = selectReflectionMoments(log).map((m) => m.caseType);
    expect(types).toContain('pattern_deviation');
  });

  // ── Director strategy choices ────────────────────────────────────────────
  // The one decision Director asks of the human states its axis explicitly, so
  // the selection must read it from the entry rather than from reason-chip text.

  it('reads the axis of a strategy choice even without a matching reason chip', () => {
    const log = [
      entry({ action: 'strategy', valueAxis: 'connection', rationale: 'Strategie: Anschlüsse halten; Störung im Netz', hypothesisResponse: 'yes' }),
    ];
    const m = scoreMoment(log, 0);
    expect(m.axis).toBe('connection');
  });

  it('spots a strategy choice that breaks the operator own pattern', () => {
    // Two prior connection-first choices, then a punctuality one: the +5 case,
    // which could never fire while the axis came from chip labels only.
    const log = [
      entry({ action: 'strategy', valueAxis: 'connection', rationale: 'Strategie: Anschlüsse halten', hypothesisResponse: 'yes' }),
      entry({ action: 'strategy', valueAxis: 'connection', rationale: 'Strategie: Anschlüsse halten', hypothesisResponse: 'yes' }),
      entry({ action: 'strategy', valueAxis: 'punctuality', rationale: 'Strategie: Verspätung minimieren', hypothesisResponse: 'yes' }),
    ];
    const m = scoreMoment(log, 2);
    expect(m.expectedAxis).toBe('connection');
    expect(m.caseType).toBe('pattern_deviation');
    expect(m.score).toBeGreaterThanOrEqual(5);
  });

  it('selects a strategy choice as a reflection moment', () => {
    const log = [
      entry({ action: 'strategy', valueAxis: 'connection', rationale: 'Strategie: Anschlüsse halten', hypothesisResponse: 'yes' }),
    ];
    const picked = selectReflectionMoments(log);
    expect(picked.length).toBe(1);
    expect(picked[0].entry.action).toBe('strategy');
  });
});
