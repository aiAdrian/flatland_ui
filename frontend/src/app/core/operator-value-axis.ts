import { DecisionLogEntry } from './decision-log';
import { ValueAxis } from './operator-model.service';

/**
 * Mapping the operator's **stated** reason onto a value axis — the cleanest
 * evidence we have for Co-Learning Level B (`docs/plans/co-learning-direction.md`):
 * when the operator says *why*, that beats inferring it from KPI deltas.
 *
 * Keyed by the reason-chip **ids** from
 * `features/rationale-capture/rationale-capture.component.ts`, which the capture
 * surface passes along with the rationale. The ids do not change with the
 * viewer's language, while the labels do (i18n plan, phase 3).
 */
export const RATIONALE_AXIS_BY_ID: Readonly<Record<string, ValueAxis>> = {
  connection: 'connection',
  delay: 'punctuality',
  ripple: 'stability',
  deadlock: 'stability',
  // 'critical' / 'experience' / 'other' carry no axis on purpose: they say
  // *that* it mattered, not which trade-off was chosen.
};

/** The axis a set of chosen reason chips is evidence for; first match wins. */
export function valueAxisFromRationaleIds(ids?: readonly string[] | null): ValueAxis | null {
  for (const id of ids ?? []) {
    const axis = RATIONALE_AXIS_BY_ID[id];
    if (axis) return axis;
  }
  return null;
}

/**
 * German chip labels as they were worded before the interface had languages.
 * Kept so decisions recorded then still resolve to their axis.
 */
export const RATIONALE_AXIS_BY_LABEL: ReadonlyArray<readonly [string, ValueAxis]> = [
  ['Schützt Anschluss', 'connection'],
  ['Geringe Zusatzverspätung', 'punctuality'],
  ['Niedriges Ripple-Risiko', 'stability'],
  ['Vermeide Deadlock', 'stability'],
  // 'Kritische Lage' / 'Erfahrungswert' / 'Sonstiges' carry no axis on purpose:
  // they say *that* it mattered, not which trade-off was chosen.
];

/**
 * First matching chip label wins. Returns `null` when the reason names no
 * trade-off — the model then falls back to inferring the axis from the option's
 * KPI deltas (or records no preference evidence at all).
 */
export function valueAxisFromRationale(rationale?: string | null): ValueAxis | null {
  if (!rationale) return null;
  for (const [label, axis] of RATIONALE_AXIS_BY_LABEL) {
    if (rationale.includes(label)) return axis;
  }
  return null;
}

/**
 * The axis a decision is evidence for. An explicitly stated axis wins: a
 * Director strategy choice names the priority outright, so matching reason-chip
 * labels would only be able to lose information.
 */
export function valueAxisFor(entry: DecisionLogEntry): ValueAxis | null {
  return (entry.valueAxis as ValueAxis | undefined) ?? valueAxisFromRationale(entry.rationale);
}

/**
 * Was this a **deliberate** decision (evidence for the preference model) or a
 * **passive** one (recorded, but must not shape preferences)?
 *
 * - `'ai'` owner → passive: the AI auto-applied it (countdown expiry /
 *   autonomous Director). The operator let it happen.
 * - human **with** a stated reason → deliberate.
 * - human **override** → deliberate: actively deviating is engagement, even
 *   without a stated reason.
 * - human **accept** without a reason → passive: "just following the
 *   recommendation" (deck slide 5's blind-accept case).
 * - human **strategy choice** → deliberate: the operator picked one objective
 *   over two alternatives whose costs were on screen. There is no passive way to
 *   do that.
 */
export function isDeliberate(entry: DecisionLogEntry): boolean {
  if (entry.accountableOwner !== 'human') return false;
  if (entry.rationale || entry.hypothesisResponse) return true;
  if (entry.valueAxis) return true;
  return entry.action === 'override';
}

/** Did the operator go along with the AI's suggestion? */
export function followedAi(entry: DecisionLogEntry): boolean {
  if (entry.aiSuggestion == null) return false;
  return entry.action !== 'override';
}
