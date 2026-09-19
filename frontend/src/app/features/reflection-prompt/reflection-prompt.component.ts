import { CommonModule } from '@angular/common';
import { TranslocoPipe } from '@jsverse/transloco';
import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, effect, inject, signal, untracked } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { LanguageService } from '../../core/i18n/language.service';
import { TrainIdentityService } from '../../core/train-identity.service';
import { buildPreferenceHypothesis, strategyLabelForAction } from '../../core/learning-store.service';
import { valueAxisFromRationaleIds } from '../../core/operator-value-axis';

/** A quick-answer chip; the label is a translation key. */
interface Chip {
  id: string;
  labelKey: string;
}

/** The guided questions this prompt draws from, beside the always-asked factors. */
export type ReflectionQuestionId = 'gut' | 'missing' | 'tradeoff';

/** The factors are the reason chips of `rationale-capture`, same ids: the
 *  preference model reads the value axis from these ids. */
const FACTORS: Chip[] = [
  { id: 'connection', labelKey: 'rationale.chip.connection' },
  { id: 'delay', labelKey: 'rationale.chip.delay' },
  { id: 'ripple', labelKey: 'rationale.chip.ripple' },
  { id: 'deadlock', labelKey: 'rationale.chip.deadlock' },
  { id: 'critical', labelKey: 'rationale.chip.critical' },
  { id: 'experience', labelKey: 'rationale.chip.experience' },
  { id: 'other', labelKey: 'rationale.chip.other' },
];

const GUT: Chip[] = [
  { id: 'fit', labelKey: 'reflectionPrompt.gut.fit' },
  { id: 'against', labelKey: 'reflectionPrompt.gut.against' },
  { id: 'none', labelKey: 'reflectionPrompt.gut.none' },
];

const MISSING: Chip[] = [
  { id: 'duration', labelKey: 'reflectionPrompt.missing.duration' },
  { id: 'connections', labelKey: 'reflectionPrompt.missing.connections' },
  { id: 'otherTrains', labelKey: 'reflectionPrompt.missing.otherTrains' },
  { id: 'nothing', labelKey: 'reflectionPrompt.missing.nothing' },
  { id: 'other', labelKey: 'reflectionPrompt.missing.other' },
];

const POOL: ReflectionQuestionId[] = ['gut', 'missing', 'tradeoff'];

/** A fixed shuffle per decision, so re-rendering or reopening keeps its questions. */
function pickQuestions(seed: number, n: number): ReflectionQuestionId[] {
  const order = [...POOL];
  let s = Math.abs(Math.floor(seed)) % 233280;
  for (let i = order.length - 1; i > 0; i--) {
    s = (s * 9301 + 49297) % 233280;
    const j = Math.floor((s / 233280) * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  return order.slice(0, Math.max(0, Math.min(n, order.length)));
}

/**
 * Reflection with guided questions — the interview tour's "why?" prompt, a
 * variant of `rationale-capture` rather than a change to it (the experiments
 * keep theirs).
 *
 * Always asked: which factors mattered, as the reason chips, because they feed
 * the preference hypothesis and so "the AI learns". Beside it, a few of the
 * team's reflection questions, drawn at random per decision so a run is not a
 * questionnaire: a gut feeling (chips), missing information (chips), and the
 * drawback accepted on purpose (a few words). How many is the session's
 * `reflectionQuestionLimit` (2 by default); the rest sit behind "more
 * questions". Every question is optional. The "most important insight for next
 * time" is asked at the end of the shift instead — right after a decision there
 * rarely is one yet.
 */
@Component({
  selector: 'app-reflection-prompt',
  standalone: true,
  imports: [CommonModule, TranslocoPipe],
  templateUrl: './reflection-prompt.component.html',
  styleUrl: './reflection-prompt.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ReflectionPromptComponent {
  readonly store = inject(SessionStore);
  private readonly i18n = inject(LanguageService);
  private readonly identity = inject(TrainIdentityService);
  private readonly t = (key: string, params?: Record<string, string>, fallback?: string) =>
    this.i18n.t(key, params, fallback);

  readonly factors = FACTORS;
  readonly gutChips = GUT;
  readonly missingChips = MISSING;

  readonly pending = computed(() => this.store.pendingRationale());

  /** The questions offered for this decision, drawn once per decision. */
  readonly suggested = computed<ReflectionQuestionId[]>(() => {
    const p = this.pending();
    return p ? pickQuestions(p.timestamp, this.store.reflectionQuestionLimit()) : [];
  });
  readonly more = computed(() => POOL.filter((q) => !this.suggested().includes(q)));
  readonly showMore = signal(false);
  readonly shown = computed(() => (this.showMore() ? [...this.suggested(), ...this.more()] : this.suggested()));

  readonly selectedFactors = signal<Set<string>>(new Set());
  readonly gut = signal<string | null>(null);
  readonly missing = signal<Set<string>>(new Set());
  readonly tradeoff = signal('');

  readonly hypothesis = computed(() => {
    const p = this.pending();
    return p ? buildPreferenceHypothesis(p.context, strategyLabelForAction(p.action, this.t), this.t) : '';
  });

  constructor() {
    // A new decision starts empty; reopening the same one keeps what was typed.
    let lastSeq: number | null = null;
    effect(() => {
      const seq = this.pending()?.decisionSeq ?? null;
      untracked(() => {
        if (seq !== null && seq !== lastSeq) {
          lastSeq = seq;
          this.reset();
        }
      });
    });
  }

  trainName(handle: number): string {
    return this.identity.nameFor(handle);
  }

  strategyLabel(): string {
    const p = this.pending();
    return p ? strategyLabelForAction(p.action, this.t) : '';
  }

  toggleFactor(id: string): void {
    this.selectedFactors.update((set) => toggled(set, id));
  }

  toggleMissing(id: string): void {
    this.missing.update((set) => toggled(set, id));
  }

  setGut(id: string): void {
    this.gut.set(this.gut() === id ? null : id);
  }

  /** A reason is what makes a hypothesis worth confirming; rejecting one needs none. */
  canConfirm(): boolean {
    return this.selectedFactors().size > 0;
  }

  submit(response: 'yes' | 'once' | 'no'): void {
    if (!this.pending()) return;
    if (response !== 'no' && !this.canConfirm()) return;
    const ids = [...this.selectedFactors()];
    this.store.submitRationale({
      rationale: FACTORS.filter((c) => ids.includes(c.id))
        .map((c) => this.i18n.t(c.labelKey))
        .join('; '),
      valueAxis: valueAxisFromRationaleIds(ids),
      response,
      reflection: this.answers(),
    });
    this.reset();
  }

  dismiss(): void {
    this.store.dismissRationale();
  }

  /** Only what was answered; chip answers as ids, the text as typed. */
  private answers(): Record<string, string> {
    const out: Record<string, string> = {};
    if (this.gut()) out['gut'] = this.gut()!;
    if (this.missing().size > 0) out['missing'] = [...this.missing()].join(',');
    const text = this.tradeoff().trim();
    if (text) out['tradeoff'] = text;
    return out;
  }

  private reset(): void {
    this.selectedFactors.set(new Set());
    this.gut.set(null);
    this.missing.set(new Set());
    this.tradeoff.set('');
    this.showMore.set(false);
  }
}

function toggled(set: Set<string>, id: string): Set<string> {
  const next = new Set(set);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}
