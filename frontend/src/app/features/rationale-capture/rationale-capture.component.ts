import { CommonModule } from '@angular/common';
import { TranslocoPipe } from '@jsverse/transloco';
import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { LanguageService } from '../../core/i18n/language.service';
import { TrainIdentityService } from '../../core/train-identity.service';
import { buildPreferenceHypothesis, strategyLabelForAction } from '../../core/learning-store.service';

/** One selectable structured "why" chip (LLM-free first cut). */
interface ReasonChip {
  id: string;
  /** Translation key; the label itself lives in the translation files. */
  labelKey: string;
}

/**
 * Workstream B Tier 1 — the "why?" prompt that appears after a human override
 * (deck slide 7). Reads `store.pendingRationale`, offers a handful of structured
 * reason chips + an optional free-text note, shows the generated preference
 * hypothesis, and confirms with **Ja / Nur diesmal / Nein**.
 *
 * "Nur diesmal" is the explicit overfitting guard: a one-off decision that must
 * NOT become a rule — the store promotes it to a transient (in-memory) record
 * only, never to a persisted preference.
 *
 * Presentational capture surface (mode-agnostic store, mode-specific surface);
 * no store writes beyond submit/dismiss. Tokens only — no hardcoded colours.
 */
@Component({
  selector: 'app-rationale-capture',
  standalone: true,
  imports: [CommonModule, TranslocoPipe],
  templateUrl: './rationale-capture.component.html',
  styleUrl: './rationale-capture.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class RationaleCaptureComponent {
  store = inject(SessionStore);
  private readonly i18n = inject(LanguageService);
  private readonly identity = inject(TrainIdentityService);

  trainName(handle: number): string {
    return this.identity.nameFor(handle);
  }

  /** Structured reasons (dispatching trade-offs + experience). Multi-select. */
  readonly chips: ReasonChip[] = [
    { id: 'connection', labelKey: 'rationale.chip.connection' },
    { id: 'delay', labelKey: 'rationale.chip.delay' },
    { id: 'ripple', labelKey: 'rationale.chip.ripple' },
    { id: 'deadlock', labelKey: 'rationale.chip.deadlock' },
    { id: 'critical', labelKey: 'rationale.chip.critical' },
    { id: 'experience', labelKey: 'rationale.chip.experience' },
    { id: 'other', labelKey: 'rationale.chip.other' },
  ];

  /** Selected chip ids. */
  readonly selected = signal<Set<string>>(new Set());
  /** Optional free-text note. */
  readonly note = signal('');

  readonly pending = computed(() => this.store.pendingRationale());

  /** The hypothesis, templated over the context snapshot (no LLM). Recomputed
   *  when the pending override changes. */
  readonly hypothesis = computed(() => {
    const p = this.pending();
    if (!p) return '';
    return buildPreferenceHypothesis(p.context, strategyLabelForAction(p.action));
  });

  strategyLabel(): string {
    const p = this.pending();
    return p ? strategyLabelForAction(p.action) : '';
  }

  toggleChip(id: string): void {
    this.selected.update((set) => {
      const next = new Set(set);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  isSelected(id: string): boolean {
    return this.selected().has(id);
  }

  /** Joined rationale string for the record: chosen chips + optional note. */
  private rationaleText(): string {
    const chips = this.chips
      .filter((c) => this.selected().has(c.id))
      .map((c) => this.i18n.t(c.labelKey));
    const note = this.note().trim();
    if (note) chips.push(note);
    return chips.join('; ');
  }

  /** Disable submit until at least one reason (or a note) is given — honest
   *  capture, not a forced click-through. */
  canSubmit(): boolean {
    return this.selected().size > 0 || this.note().trim().length > 0;
  }

  submit(response: 'yes' | 'once' | 'no'): void {
    if (!this.pending()) return;
    // 'no' may proceed without a rationale (rejecting the hypothesis is itself
    // the answer); for 'yes'/'once' require a reason.
    if (response !== 'no' && !this.canSubmit()) return;
    this.store.submitRationale({ rationale: this.rationaleText(), response });
    this._reset();
  }

  dismiss(): void {
    this.store.dismissRationale();
    this._reset();
  }

  private _reset(): void {
    this.selected.set(new Set());
    this.note.set('');
  }
}
