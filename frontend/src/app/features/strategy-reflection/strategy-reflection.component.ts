import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal } from '@angular/core';
import { OperatorModelService, ValueAxis } from '../../core/operator-model.service';
import { SessionStore } from '../../core/session.store';
import { VALUE_AXIS_LABELS } from '../../core/reflection-moments';

/**
 * Director's reflection surface — the reflection agent's voice in this mode.
 *
 * Director deliberately does not ask "why did you hold train 7?" (the store
 * suppresses that prompt here): the human does not dispatch individual trains.
 * But it does make one decision, and a strong one — which objective the plan
 * should pursue — and until now nothing responded to it. The operator model got
 * no evidence, so "what the AI learned about you" was permanently empty and the
 * mode had no co-learning loop at all.
 *
 * Three things happen here, in this order:
 *
 * 1. **Mirroring**: the choice is played back with its price, taken from the
 *    planner's own delta ("Anschlüsse gewählt, Preis −31 Pünktlichkeit").
 * 2. **Confirmation** with the existing overfitting guard: as a rule / just this
 *    once / no. 'once' is what keeps a single situational choice from becoming a
 *    standing preference.
 * 3. **Contradiction check**: when the choice runs against the profile carried
 *    over from earlier sessions, that is said out loud — as a question, not a
 *    correction. A profile that silently overwrites itself teaches nothing.
 */
@Component({
  selector: 'app-strategy-reflection',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './strategy-reflection.component.html',
  styleUrl: './strategy-reflection.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class StrategyReflectionComponent {
  store = inject(SessionStore);
  private model = inject(OperatorModelService);

  readonly pending = computed(() => this.store.pendingStrategyReflection());

  axisLabel(axis: ValueAxis | null): string {
    return axis ? VALUE_AXIS_LABELS[axis] : '—';
  }

  /**
   * The dominant axis of the profile carried over from earlier sessions, if it
   * is established enough to be worth mentioning.
   */
  readonly profileAxis = computed<ValueAxis | null>(() => {
    const p = this.model.profile();
    if (!p || p.evidenceCount < 3) return null;
    return p.valueProfile.dominant;
  });

  /** Set when this choice contradicts the carried-over profile. */
  readonly contradiction = computed<{ was: ValueAxis; now: ValueAxis } | null>(() => {
    const pending = this.pending();
    const was = this.profileAxis();
    if (!pending || !was) return null;
    const now = pending.axis as ValueAxis;
    return was === now ? null : { was, now };
  });

  /** How consistent this choice is with what the model already believes. */
  readonly consistent = computed<boolean>(() => {
    const pending = this.pending();
    const was = this.profileAxis();
    return !!pending && !!was && was === (pending.axis as ValueAxis);
  });

  /**
   * Why *now*? The axis is already stated by the choice itself, so these chips
   * capture the **situation** that made this focus the right one — which is the
   * condition half of a learnable preference ("learn the condition, not the
   * option"). Labels are shared with the override prompt's vocabulary where they
   * overlap, so `RATIONALE_AXIS_BY_LABEL` keeps working on them.
   */
  readonly chips: ReadonlyArray<{ id: string; label: string }> = [
    { id: 'connection', label: 'Schützt Anschluss' },
    { id: 'delay', label: 'Geringe Zusatzverspätung' },
    { id: 'deadlock', label: 'Vermeide Deadlock' },
    { id: 'disruption', label: 'Störung im Netz' },
    { id: 'reserve', label: 'Reserve aufbauen' },
    { id: 'critical', label: 'Kritische Lage' },
    { id: 'experience', label: 'Erfahrungswert' },
  ];

  readonly selected = signal<Set<string>>(new Set<string>());
  readonly note = signal('');
  readonly noteOpen = signal(false);

  toggleChip(id: string): void {
    this.selected.update((set) => {
      const next = new Set(set);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  isSelected(id: string): boolean {
    return this.selected().has(id);
  }

  toggleNote(): void {
    this.noteOpen.update((v) => !v);
  }

  setNote(value: string): void {
    this.note.set(value);
  }

  /** Chosen chips plus an optional note, joined. Empty when nothing was said —
   *  answering without a reason stays allowed, it is just weaker evidence. */
  private reasonText(): string {
    const parts = this.chips
      .filter((c) => this.selected().has(c.id))
      .map((c) => c.label);
    const note = this.note().trim();
    if (note) parts.push(note);
    return parts.join('; ');
  }

  readonly hasReason = computed(
    () => this.selected().size > 0 || this.note().trim().length > 0,
  );

  answer(response: 'yes' | 'once' | 'no'): void {
    this.store.answerStrategyReflection(response, this.reasonText() || undefined);
    this.selected.set(new Set<string>());
    this.note.set('');
    this.noteOpen.set(false);
    // Refresh so the effect panel reflects the new evidence rather than waiting
    // for the next poll.
    this.model.loadProfile().subscribe({ error: () => void 0 });
  }

  dismiss(): void {
    this.store.dismissStrategyReflection();
    this.selected.set(new Set<string>());
    this.note.set('');
    this.noteOpen.set(false);
  }
}
