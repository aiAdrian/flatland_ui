import { DecisionLogEntry } from './decision-log';
import { isDeliberate, valueAxisFor } from './operator-value-axis';
import { ValueAxis } from './operator-model.service';

/**
 * Reflection-moment selection — which decisions are actually *worth* discussing.
 *
 * Co-Learning expects several reflection moments per run, not a fixed
 * questionnaire (see `co-learning-reflection.component.ts`). A whole shift is
 * too much to review, so this picks the few decisions that carry signal, using
 * transparent additive scoring (no LLM, no model):
 *
 *   pattern deviation        +5   the operator broke their own habit
 *   override                 +4   they actively deviated from the AI
 *   deferred to the AI       +3   the AI acted; over-reliance signal
 *   confirmed a preference   +3   they turned a decision into a rule
 *   stated a reason          +2   there is something to talk about
 *   one-off ('once')         +2   explicitly *not* a rule — why?
 *   passive accept            0   nothing was expressed
 *
 * Ties break toward the later decision (fresher in memory). Diversity first:
 * we prefer one of each case type before taking a second of the same kind.
 */

export type ReflectionCaseType =
  | 'pattern_deviation'
  | 'override'
  | 'deferred_to_ai'
  | 'confirmed_preference'
  | 'one_off'
  | 'reasoned'
  | 'passive_accept';

export interface ReflectionMoment {
  entry: DecisionLogEntry;
  score: number;
  caseType: ReflectionCaseType;
  /** Human-readable scoring trace, so the selection stays explainable. */
  reasons: string[];
  /** The value axis the operator expressed, when they named one. */
  axis: ValueAxis | null;
  /** The axis their earlier decisions in comparable situations suggested. */
  expectedAxis: ValueAxis | null;
}

export const MAX_REFLECTION_MOMENTS = 3;

/** Director's own decision kind: choosing the objective the plan pursues. */
export const STRATEGY_ACTION = 'strategy';

/** German labels for the reflection panel (the panel copy is German). */
export const REFLECTION_CASE_LABELS: Record<ReflectionCaseType, string> = {
  pattern_deviation: 'Musterbruch',
  override: 'Override',
  deferred_to_ai: 'der KI überlassen',
  confirmed_preference: 'Präferenz bestätigt',
  one_off: 'Einzelfall',
  reasoned: 'mit Begründung',
  passive_accept: 'stille Zustimmung',
};

/** German labels for the value axes. */
export const VALUE_AXIS_LABELS: Record<ValueAxis, string> = {
  punctuality: 'Pünktlichkeit',
  connection: 'Anschluss',
  stability: 'Netzstabilität',
  throughput: 'Durchsatz',
};

/** Preference order when picking a diverse set. */
const CASE_PRIORITY: ReflectionCaseType[] = [
  'pattern_deviation',
  'override',
  'deferred_to_ai',
  'confirmed_preference',
  'one_off',
  'reasoned',
  'passive_accept',
];

/**
 * The axis the operator expressed most often *before* this entry — their habit
 * up to that point. Only deliberate decisions count, mirroring the model's
 * evidence guard.
 */
function habitBefore(log: DecisionLogEntry[], index: number): ValueAxis | null {
  const counts = new Map<ValueAxis, number>();
  for (let i = 0; i < index; i++) {
    const e = log[i];
    if (!isDeliberate(e)) continue;
    const axis = valueAxisFor(e);
    if (axis) counts.set(axis, (counts.get(axis) ?? 0) + 1);
  }
  let best: ValueAxis | null = null;
  let bestCount = 0;
  for (const [axis, n] of counts) {
    if (n > bestCount) {
      best = axis;
      bestCount = n;
    }
  }
  // A single prior decision is not a habit yet.
  return bestCount >= 2 ? best : null;
}

/** Score one decision. Exported for testing and for the debug view. */
export function scoreMoment(
  log: DecisionLogEntry[],
  index: number,
): ReflectionMoment {
  const entry = log[index];
  // `valueAxisFor`, not the rationale text alone: a Director strategy choice
  // *states* its axis, and matching reason-chip labels would miss it whenever the
  // operator gave a Director-specific reason ("Störung im Netz") or none at all.
  // Without this the highest-scoring case — breaking your own pattern (+5) —
  // could never fire for the one decision Director actually asks for.
  const axis = valueAxisFor(entry);
  const expectedAxis = habitBefore(log, index);

  let score = 0;
  const reasons: string[] = [];
  let caseType: ReflectionCaseType = 'passive_accept';

  if (expectedAxis && axis && axis !== expectedAxis) {
    score += 5;
    reasons.push('Weicht vom eigenen Muster ab (+5)');
    caseType = 'pattern_deviation';
  }
  if (entry.accountableOwner === 'human' && entry.action === 'override') {
    score += 4;
    reasons.push('Override der KI-Empfehlung (+4)');
    if (caseType === 'passive_accept') caseType = 'override';
  }
  if (entry.accountableOwner === 'ai') {
    score += 3;
    reasons.push('Der KI überlassen (+3)');
    if (caseType === 'passive_accept') caseType = 'deferred_to_ai';
  }
  if (entry.hypothesisResponse === 'yes') {
    score += 3;
    reasons.push('Als Präferenz bestätigt (+3)');
    if (caseType === 'passive_accept') caseType = 'confirmed_preference';
  }
  if (entry.hypothesisResponse === 'once') {
    score += 2;
    reasons.push('Bewusst als Einzelfall markiert (+2)');
    if (caseType === 'passive_accept') caseType = 'one_off';
  }
  if (entry.rationale) {
    score += 2;
    reasons.push('Grund angegeben (+2)');
    if (caseType === 'passive_accept') caseType = 'reasoned';
  }
  if (score === 0) {
    reasons.push('Stille Zustimmung (+0)');
  }

  return { entry, score, caseType, reasons, axis, expectedAxis };
}

/**
 * Pick at most `max` moments worth reflecting on: highest score first, but
 * preferring a *diverse* set of case types before doubling up. Returns them in
 * chronological order, so the reflection walks the shift forward.
 */
export function selectReflectionMoments(
  log: DecisionLogEntry[],
  max = MAX_REFLECTION_MOMENTS,
): ReflectionMoment[] {
  if (log.length === 0) return [];

  // Chronological, so "before this decision" is well-defined.
  const chronological = [...log].sort((a, b) => a.seq - b.seq);
  const scored = chronological
    .map((_, i) => scoreMoment(chronological, i))
    // 'system' holds belong to neither party — nothing to reflect on.
    .filter((m) => m.entry.accountableOwner !== 'system')
    .filter((m) => m.score > 0);

  const byScore = [...scored].sort(
    (a, b) => b.score - a.score || b.entry.seq - a.entry.seq,
  );

  const picked: ReflectionMoment[] = [];
  for (const caseType of CASE_PRIORITY) {
    if (picked.length >= max) break;
    const candidate = byScore.find(
      (m) => m.caseType === caseType && !picked.includes(m),
    );
    if (candidate) picked.push(candidate);
  }
  for (const m of byScore) {
    if (picked.length >= max) break;
    if (!picked.includes(m)) picked.push(m);
  }

  return picked.sort((a, b) => a.entry.seq - b.entry.seq);
}
