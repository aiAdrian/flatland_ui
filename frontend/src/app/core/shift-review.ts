import { DecisionLogEntry } from './decision-log';
import { LearningRecord } from './learning-store.service';
import { ValueAxis } from './operator-model.service';
import { valueAxisFor } from './operator-value-axis';
import {
  ReflectionMoment,
  VALUE_AXIS_LABELS,
  selectReflectionMoments,
} from './reflection-moments';

/**
 * Director shift review — the end-of-shift evaluation.
 *
 * Director had none: at `episodeDone` the directive bar simply disappeared and a
 * survey button showed up in the footer. Everything needed for a real review was
 * already computed and unreachable — the moment selection
 * (`selectReflectionMoments`), the confirmed learnings, the inferred weights.
 *
 * This is a **pure** builder so the whole evaluation is testable without a
 * browser: give it the shift's facts, get the review. No LLM — the wording is
 * templated, and every number traces to something measured.
 */

export interface ShiftKpis {
  total: number;
  arrived: number;
  delayed: number;
  malfunctions: number;
  /** Summed delay over all trains, in the env's own delay unit. */
  totalDelay: number;
}

/** What the autonomous planner did on its own. */
export interface AiWorkload {
  decisions: number;
  replans: number;
}

/** One strategy choice the human made, as the review recounts it. */
export interface ShiftChoice {
  step: number;
  /** Focus title, e.g. "Anschlüsse halten". */
  title: string;
  axis: ValueAxis | null;
  axisLabel: string;
  /** What it gave up, e.g. "31 Punkte Pünktlichkeit". */
  tradedAway: string | null;
  /** The situation the operator stated, without the "Strategie: …" prefix. */
  reason: string | null;
  response: 'yes' | 'once' | 'no' | null;
}

/**
 * A tension in the shift worth asking about rather than resolving silently.
 * Two different priorities across comparable situations is not an error — it is
 * the interesting part, and the operator is the only one who can explain it.
 */
export interface ShiftContradiction {
  axes: Array<{ axis: ValueAxis; label: string; count: number }>;
  question: string;
}

export interface ShiftReview {
  kpis: ShiftKpis;
  ai: AiWorkload | null;
  /** Human strategy choices, chronological. */
  choices: ShiftChoice[];
  /** At most three decisions worth discussing. */
  moments: ReflectionMoment[];
  /** Confirmed ('yes') preferences only — one-offs are excluded by design. */
  confirmed: LearningRecord[];
  oneOffs: LearningRecord[];
  contradiction: ShiftContradiction | null;
  /** True when the human never set a goal — the AI ran the whole shift alone. */
  ranUnattended: boolean;
}

/** Strip the bookkeeping prefix so the review shows what the operator said. */
export function statedReason(rationale?: string): string | null {
  if (!rationale) return null;
  const parts = rationale
    .split(';')
    .map((p) => p.trim())
    .filter((p) => p.length > 0 && !p.startsWith('Strategie:'));
  return parts.length > 0 ? parts.join('; ') : null;
}

function choiceFrom(entry: DecisionLogEntry): ShiftChoice {
  const axis = valueAxisFor(entry);
  // "Strategie: Anschlüsse halten; Schützt Anschluss" → the title.
  const titleMatch = /Strategie:\s*([^;]+)/.exec(entry.rationale ?? '');
  return {
    step: entry.simStep,
    title: titleMatch ? titleMatch[1].trim() : (axis ? VALUE_AXIS_LABELS[axis] : 'Ziel gewählt'),
    axis,
    axisLabel: axis ? VALUE_AXIS_LABELS[axis] : '—',
    tradedAway: entry.tradedAway ?? null,
    reason: statedReason(entry.rationale),
    response: entry.hypothesisResponse ?? null,
  };
}

/**
 * Which priorities the shift actually expressed. Only *deliberate* choices count
 * and only ones that named an axis — the same evidence guard the operator model
 * uses, so the review cannot claim a preference the model would not learn.
 */
function contradictionFrom(choices: ShiftChoice[]): ShiftContradiction | null {
  const counts = new Map<ValueAxis, number>();
  for (const c of choices) {
    if (!c.axis) continue;
    if (c.response === 'no') continue; // explicitly rejected as a preference
    counts.set(c.axis, (counts.get(c.axis) ?? 0) + 1);
  }
  if (counts.size < 2) return null;

  const axes = [...counts.entries()]
    .map(([axis, count]) => ({ axis, label: VALUE_AXIS_LABELS[axis], count }))
    .sort((a, b) => b.count - a.count);

  const [first, second] = axes;
  return {
    axes,
    question:
      `Du hast ${first.count}× ${first.label} und ${second.count}× ${second.label} ` +
      `priorisiert. Was war in der Lage anders — oder hängt es von etwas ab, das ich ` +
      `noch nicht kenne?`,
  };
}

export function buildShiftReview(input: {
  kpis: ShiftKpis;
  ai: AiWorkload | null;
  decisionLog: DecisionLogEntry[];
  learningRecords: LearningRecord[];
}): ShiftReview {
  const choices = input.decisionLog
    .filter((e) => e.action === 'strategy')
    .sort((a, b) => a.seq - b.seq)
    .map(choiceFrom);

  return {
    kpis: input.kpis,
    ai: input.ai,
    choices,
    moments: selectReflectionMoments(input.decisionLog),
    confirmed: input.learningRecords.filter((r) => r.response === 'yes' && !r.once),
    oneOffs: input.learningRecords.filter((r) => r.once),
    contradiction: contradictionFrom(choices),
    // The AI running alone is a legitimate outcome, not an empty state — and it
    // is exactly the case a co-learning study wants to see reported.
    ranUnattended: choices.length === 0,
  };
}
