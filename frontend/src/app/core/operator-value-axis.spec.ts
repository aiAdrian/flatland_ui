import { DecisionLogEntry } from './decision-log';
import { followedAi, isDeliberate, valueAxisFromRationale } from './operator-value-axis';

function entry(overrides: Partial<DecisionLogEntry> = {}): DecisionLogEntry {
  return {
    seq: 1,
    t: 0,
    simStep: 5,
    mode: 'co-learning',
    handle: 0,
    accountableOwner: 'human',
    action: 'accept',
    aiSuggestion: 'Hold train 3',
    decisionTimeMs: 1200,
    ...overrides,
  };
}

describe('valueAxisFromRationale', () => {
  it('maps the connection chip to the connection axis', () => {
    expect(valueAxisFromRationale('Schützt Anschluss')).toBe('connection');
  });

  it('maps the delay chip to punctuality', () => {
    expect(valueAxisFromRationale('Geringe Zusatzverspätung')).toBe('punctuality');
  });

  it('maps both stability chips to stability', () => {
    expect(valueAxisFromRationale('Niedriges Ripple-Risiko')).toBe('stability');
    expect(valueAxisFromRationale('Vermeide Deadlock')).toBe('stability');
  });

  it('finds the chip inside a joined rationale with a free-text note', () => {
    expect(valueAxisFromRationale('Schützt Anschluss; Kritische Lage; mein Kommentar'))
      .toBe('connection');
  });

  it('returns null for reasons that name no trade-off', () => {
    expect(valueAxisFromRationale('Kritische Lage')).toBeNull();
    expect(valueAxisFromRationale('Erfahrungswert; Sonstiges')).toBeNull();
  });

  it('returns null for empty input', () => {
    expect(valueAxisFromRationale(undefined)).toBeNull();
    expect(valueAxisFromRationale('')).toBeNull();
  });
});

describe('isDeliberate (the evidence guard)', () => {
  it('counts a stated reason as deliberate', () => {
    expect(isDeliberate(entry({ rationale: 'Schützt Anschluss' }))).toBeTrue();
  });

  it('counts an override without a reason as deliberate', () => {
    expect(isDeliberate(entry({ action: 'override' }))).toBeTrue();
  });

  it('treats a silent accept as passive ("just following")', () => {
    expect(isDeliberate(entry({ action: 'accept' }))).toBeFalse();
  });

  it('treats an AI-applied decision as passive', () => {
    expect(isDeliberate(entry({ accountableOwner: 'ai', action: 'hold' }))).toBeFalse();
  });

  it('treats a system hold as passive (attributed to neither party)', () => {
    expect(isDeliberate(entry({ accountableOwner: 'system', action: 'hold' }))).toBeFalse();
  });

  it('counts a confirmed hypothesis as deliberate even without chips', () => {
    expect(isDeliberate(entry({ hypothesisResponse: 'yes' }))).toBeTrue();
  });
});

describe('followedAi', () => {
  it('is true when the operator accepted the AI suggestion', () => {
    expect(followedAi(entry({ action: 'accept' }))).toBeTrue();
  });

  it('is false on an override', () => {
    expect(followedAi(entry({ action: 'override' }))).toBeFalse();
  });

  it('is false when there was no AI suggestion', () => {
    expect(followedAi(entry({ aiSuggestion: null }))).toBeFalse();
  });
});
