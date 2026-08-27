/**
 * Learning Moments: the client's view of `backend/app/core/learning_moments.py`.
 *
 * A moment interrupts shortly after a decision that turned out to matter and
 * asks the operator to *predict* what the alternative would have done, before
 * showing the measured answer. The backend owns detection and the counterfactual;
 * this module only types the payload and holds the labels.
 *
 * The split between `evidence` and `narrative` is load-bearing and is preserved
 * all the way into the UI: `evidence` is simulator output, `narrative` is an
 * interpretation of it. Both are optional here because the payload that carries
 * the *question* deliberately contains neither — otherwise a client could reveal
 * the answer before the operator has committed to a guess.
 */

/** Why a decision was worth interrupting for. */
export type LearningMomentEvent = 'mistake' | 'near_miss' | 'surprising_success';

/** What the operator can predict about the alternative. */
export type LearningMomentPrediction = 'better' | 'same' | 'worse';

/** One simulated branch. Field names mirror the backend dataclass. */
export interface BranchOutcome {
  total_delay: number;
  max_delay: number;
  arrived: number;
  trains: number;
  all_arrived: boolean;
  steps: number;
  connections_total: number;
  connections_kept: number;
  kept_ratio: number;
  predicted_weighted: number | null;
}

export interface LearningMomentOption {
  id: LearningMomentPrediction;
  label: string;
}

export interface LearningMomentSide {
  id: string;
  label: string;
  weights: Record<string, number>;
}

/** Measured differences. Positive = the alternative would have been better. */
export interface LearningMomentEvidence {
  source: 'simulation';
  actual: BranchOutcome;
  counterfactual: BranchOutcome;
  delayRegret: number;
  arrivalRegret: number;
  connectionRegret: number;
  detectionReasons: string[];
}

export interface LearningMomentNarrative {
  source: 'narrator';
  explanation: string | null;
  takeaway: string | null;
}

export interface LearningMomentView {
  id: string;
  step: number;
  eventType: LearningMomentEvent;
  situation: Record<string, unknown>;
  chosen: LearningMomentSide;
  alternative: LearningMomentSide;
  question: string;
  options: LearningMomentOption[];
  answered: boolean;
  userPrediction: LearningMomentPrediction | null;
  /** Present only once the operator has answered. */
  evidence?: LearningMomentEvidence;
  narrative?: LearningMomentNarrative;
  predictionCorrect?: boolean | null;
}

export interface LearningMomentEvaluation {
  session_id: string;
  step: number;
  triggered: boolean;
  reason?: string | null;
  moment?: LearningMomentView;
}

export interface LearningMomentSummary {
  total: number;
  answered: number;
  mispredicted: number;
  byType: Partial<Record<LearningMomentEvent, number>>;
  takeaways: string[];
  /** The one sentence the moments say together, or null when they say nothing. */
  pattern: string | null;
}

export interface LearningMomentList {
  session_id: string;
  moments: LearningMomentView[];
  summary: LearningMomentSummary;
  config: {
    maxPerEpisode: number;
    minStepsBetween: number;
    delayThreshold: number;
    arrivalThreshold: number;
    nearMissMaxDelay: number;
  };
}

export const LEARNING_MOMENT_EVENT_LABELS: Record<LearningMomentEvent, string> = {
  mistake: 'Fehlgriff',
  near_miss: 'Knapp gutgegangen',
  surprising_success: 'Überraschender Erfolg',
};

/**
 * The headline of the reveal: was the guess right, and if not, in which
 * direction. Deliberately not a score — one wrong guess is the point of the
 * exercise, not a failure to report.
 */
export function predictionVerdict(moment: LearningMomentView): string {
  if (!moment.answered || moment.predictionCorrect == null) return '';
  return moment.predictionCorrect ? 'Richtig geschätzt.' : 'Anders als gedacht.';
}

/**
 * The comparison rows the reveal shows, measured values only.
 *
 * Returns an empty list before the operator has answered, because the evidence
 * is not in the payload then.
 */
export function comparisonRows(
  moment: LearningMomentView,
): { label: string; actual: string; alternative: string; better: 'actual' | 'alternative' | 'equal' }[] {
  const ev = moment.evidence;
  if (!ev) return [];
  const rows: {
    label: string;
    actual: string;
    alternative: string;
    better: 'actual' | 'alternative' | 'equal';
  }[] = [];

  const compare = (
    label: string,
    actual: number,
    alternative: number,
    lowerIsBetter: boolean,
    format: (v: number) => string = (v) => String(v),
  ) => {
    let better: 'actual' | 'alternative' | 'equal' = 'equal';
    if (actual !== alternative) {
      const actualWins = lowerIsBetter ? actual < alternative : actual > alternative;
      better = actualWins ? 'actual' : 'alternative';
    }
    rows.push({ label, actual: format(actual), alternative: format(alternative), better });
  };

  compare('Angekommen', ev.actual.arrived, ev.counterfactual.arrived, false,
    (v) => `${v} / ${ev.actual.trains}`);
  compare('Verspätung gesamt', ev.actual.total_delay, ev.counterfactual.total_delay, true,
    (v) => `${v} Schritte`);
  compare('Schlimmster Zug', ev.actual.max_delay, ev.counterfactual.max_delay, true,
    (v) => `${v} Schritte`);
  if (ev.actual.connections_total > 0) {
    compare('Anschlüsse gehalten', ev.actual.connections_kept,
      ev.counterfactual.connections_kept, false,
      (v) => `${v} / ${ev.actual.connections_total}`);
  }
  return rows;
}
