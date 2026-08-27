import {
  BranchOutcome,
  LearningMomentView,
  comparisonRows,
  predictionVerdict,
} from './learning-moment';

function outcome(overrides: Partial<BranchOutcome> = {}): BranchOutcome {
  return {
    total_delay: 200,
    max_delay: 40,
    arrived: 2,
    trains: 4,
    all_arrived: false,
    steps: 200,
    connections_total: 3,
    connections_kept: 1,
    kept_ratio: 1 / 3,
    predicted_weighted: 0.5,
    ...overrides,
  };
}

function moment(overrides: Partial<LearningMomentView> = {}): LearningMomentView {
  return {
    id: 'lm_1',
    step: 42,
    eventType: 'mistake',
    situation: { step: 42 },
    chosen: { id: 'focus_delay', label: 'A · Pünktlichkeit', weights: {} },
    alternative: { id: 'focus_connections', label: 'B · Anschlüsse', weights: {} },
    question: 'Was wäre mit B passiert?',
    options: [
      { id: 'better', label: 'Besser' },
      { id: 'same', label: 'Etwa gleich' },
      { id: 'worse', label: 'Schlechter' },
    ],
    answered: false,
    userPrediction: null,
    ...overrides,
  };
}

function answered(overrides: Partial<LearningMomentView> = {}): LearningMomentView {
  return moment({
    answered: true,
    userPrediction: 'better',
    predictionCorrect: true,
    evidence: {
      source: 'simulation',
      actual: outcome(),
      counterfactual: outcome({ total_delay: 120, arrived: 3, max_delay: 30, connections_kept: 3 }),
      delayRegret: 80,
      arrivalRegret: 1,
      connectionRegret: 2,
      detectionReasons: ['B hätte einen Zug mehr heimgebracht'],
    },
    narrative: {
      source: 'narrator',
      explanation: 'B bringt einen Zug mehr heim.',
      takeaway: 'Ankünfte vor Einzelverspätung wägen.',
    },
    ...overrides,
  });
}

describe('learning moments', () => {
  describe('before the operator answers', () => {
    it('has no comparison to show, because the payload carries none', () => {
      expect(comparisonRows(moment())).toEqual([]);
    });

    it('has no verdict', () => {
      expect(predictionVerdict(moment())).toBe('');
    });
  });

  describe('after the operator answers', () => {
    it('names a right guess and a wrong one differently', () => {
      expect(predictionVerdict(answered())).toContain('Richtig');
      expect(predictionVerdict(answered({ predictionCorrect: false }))).toContain(
        'Anders',
      );
    });

    it('builds one row per measured quantity', () => {
      const rows = comparisonRows(answered());
      expect(rows.map((r) => r.label)).toEqual([
        'Angekommen',
        'Verspätung gesamt',
        'Schlimmster Zug',
        'Anschlüsse gehalten',
      ]);
    });

    it('marks the better side per row, not per moment', () => {
      const rows = comparisonRows(answered());
      const byLabel = new Map(rows.map((r) => [r.label, r]));
      // Fewer arrivals and more delay under the choice → the alternative wins.
      expect(byLabel.get('Angekommen')!.better).toBe('alternative');
      expect(byLabel.get('Verspätung gesamt')!.better).toBe('alternative');
    });

    it('reads delay as lower-is-better and arrivals as higher-is-better', () => {
      const rows = comparisonRows(
        answered({
          evidence: {
            source: 'simulation',
            actual: outcome({ total_delay: 100, arrived: 4 }),
            counterfactual: outcome({ total_delay: 300, arrived: 1 }),
            delayRegret: -200,
            arrivalRegret: -3,
            connectionRegret: 0,
            detectionReasons: [],
          },
        }),
      );
      const byLabel = new Map(rows.map((r) => [r.label, r]));
      expect(byLabel.get('Verspätung gesamt')!.better).toBe('actual');
      expect(byLabel.get('Angekommen')!.better).toBe('actual');
    });

    it('calls an equal row equal rather than picking a winner', () => {
      const rows = comparisonRows(
        answered({
          evidence: {
            source: 'simulation',
            actual: outcome({ max_delay: 40 }),
            counterfactual: outcome({ max_delay: 40 }),
            delayRegret: 0,
            arrivalRegret: 0,
            connectionRegret: 0,
            detectionReasons: [],
          },
        }),
      );
      expect(rows.find((r) => r.label === 'Schlimmster Zug')!.better).toBe('equal');
    });

    it('omits connections when the episode has none to keep', () => {
      const rows = comparisonRows(
        answered({
          evidence: {
            source: 'simulation',
            actual: outcome({ connections_total: 0, connections_kept: 0 }),
            counterfactual: outcome({ connections_total: 0, connections_kept: 0 }),
            delayRegret: 0,
            arrivalRegret: 0,
            connectionRegret: 0,
            detectionReasons: [],
          },
        }),
      );
      expect(rows.some((r) => r.label === 'Anschlüsse gehalten')).toBe(false);
    });
  });
});
