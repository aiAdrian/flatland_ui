import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal } from '@angular/core';
import { AgentDTO } from '../../core/models';
import { OperatorModelService, ValueAxis } from '../../core/operator-model.service';
import { SessionStore } from '../../core/session.store';
import { ReflectionCaseType, REFLECTION_CASE_LABELS, VALUE_AXIS_LABELS } from '../../core/reflection-moments';
import { ShiftKpis, buildShiftReview, statedReason } from '../../core/shift-review';

/**
 * Director shift review — the end-of-shift evaluation this mode did not have.
 *
 * Before this, `episodeDone` in Director meant the directive bar disappeared and
 * a survey button appeared in the footer. Nothing was reviewed, even though the
 * material was all computed already: the moment selection, the confirmed
 * learnings, the inferred weights, the planner's own workload.
 *
 * Three parts, in the order a debrief actually runs:
 *
 * 1. **Bilanz** — how the shift ended, and how much of it the AI ran alone.
 * 2. **Momente** — at most three decisions worth discussing, chosen by
 *    transparent scoring (`selectReflectionMoments`) with the trace shown, so
 *    the selection can be argued with rather than trusted.
 * 3. **Was die KI gelernt hat** — confirmed preferences, the weights they imply,
 *    one-offs kept explicitly apart, and any tension left open as a question.
 *
 * No LLM: every sentence is a template over measured values.
 */
@Component({
  selector: 'app-shift-review',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './shift-review.component.html',
  styleUrl: './shift-review.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ShiftReviewComponent {
  store = inject(SessionStore);
  private model = inject(OperatorModelService);

  private isMalfunctioning(a: AgentDTO): boolean {
    return (
      !!a.is_malfunctioning ||
      (a.malfunction_remaining ?? 0) > 0 ||
      String(a.state ?? '').toUpperCase().includes('MALFUNCTION')
    );
  }

  readonly kpis = computed<ShiftKpis>(() => {
    const agents = this.store.agents();
    return {
      total: agents.length,
      arrived: agents.filter((a) => String(a.state).toUpperCase() === 'DONE').length,
      delayed: agents.filter((a) => (a.delay ?? 0) > 0).length,
      malfunctions: agents.filter((a) => this.isMalfunctioning(a)).length,
      totalDelay: agents.reduce((sum, a) => sum + Math.max(0, a.delay ?? 0), 0),
    };
  });

  readonly review = computed(() =>
    buildShiftReview({
      kpis: this.kpis(),
      ai: this.store.directorAiWorkload(),
      decisionLog: this.store.decisionLog(),
      learningRecords: this.store.learningRecords(),
    }),
  );

  /** Weights the model derived from the shift, when they carry a preference. */
  readonly weights = computed(() => {
    const p = this.model.profile();
    if (!p) return null;
    const w = p.suggestedDirectorWeights;
    const neutral = w.punctuality === w.connections && w.connections === w.stability;
    return neutral ? null : w;
  });

  readonly valueProfile = computed(() => this.model.profile()?.valueProfile ?? null);

  /**
   * Rules confirmed in *earlier* shifts.
   *
   * `review().confirmed` only knows this shift's records, so a shift without a
   * single goal produced "Noch keine bestätigte Präferenz" directly above
   * "Muster: Connection-first" from the carried-over profile — both true, and
   * reading like a contradiction.
   */
  readonly carriedLearnings = computed(() => this.model.profile()?.confirmedLearnings ?? []);

  /** True when the value pattern comes from earlier shifts rather than this one. */
  readonly patternIsCarried = computed(
    () => this.decisionsThisShift() === 0 && this.priorSessions() > 0,
  );

  // ── Carrying the shift over ──────────────────────────────────────────────
  /**
   * Saving is an explicit act, not a side effect of the episode ending.
   *
   * The backend has had `POST /operator/{id}/end-session` — "fold this session's
   * deliberate evidence into the carried-over prior" — from the start, and
   * nothing in the app ever called it. So every shift's evidence was discarded
   * on reload and the next one started cold, while the UI spoke of a warm start.
   * The operator decides here: this shift's evidence either becomes part of the
   * long-term profile or it does not.
   */
  readonly saveState = signal<'idle' | 'saving' | 'saved' | 'error'>('idle');

  /** How many shifts the profile carries after saving — the proof it stuck. */
  readonly priorSessions = computed(() => this.model.profile()?.priorSessions ?? 0);

  /**
   * Goals the operator set **in this shift** — counted from the session's own
   * decision log, not from the backend profile.
   *
   * The profile's `evidenceCount` holds every raw signal since the last saved
   * shift, and the backend keys those by operator, not by session: after three
   * runs in the same process it reported "6 bewusste Entscheidungen dieser
   * Schicht" for a shift with one goal choice. The decision log is the only
   * source that is actually scoped to this shift.
   */
  readonly decisionsThisShift = computed(() => this.review().choices.length);

  /** Whether there is anything to carry over at all. Offering the button with
   *  an empty profile would promise a transfer of nothing. */
  readonly hasCarryOver = computed(
    () => this.decisionsThisShift() > 0 || this.review().confirmed.length > 0,
  );

  /**
   * True when earlier *shifts* already contribute to the profile.
   *
   * Not `isWarm`: that also turns true from a rule confirmed minutes ago in this
   * very shift, which produced "es enthält bereits 0 frühere Schicht(en)".
   */
  readonly wasWarm = computed(() => this.priorSessions() > 0);

  savePreferences(): void {
    if (this.saveState() === 'saving' || this.saveState() === 'saved') return;
    this.saveState.set('saving');
    this.model.endSession().subscribe({
      next: () => this.saveState.set('saved'),
      error: () => this.saveState.set('error'),
    });
  }

  /** Leave the review without ending anything — only while the shift could go
   *  on. A review must not be a trap. */
  readonly canReopen = computed(() => !this.store.episodeDone() && this.store.shiftEnded());

  reopenShift(): void {
    this.store.reopenShift();
  }

  caseLabel(caseType: ReflectionCaseType): string {
    return REFLECTION_CASE_LABELS[caseType];
  }

  axisLabel(axis: ValueAxis | null): string {
    return axis ? VALUE_AXIS_LABELS[axis] : '—';
  }

  /** The operator's own words for a moment, without the bookkeeping prefix. */
  reasonOf(rationale?: string): string | null {
    return statedReason(rationale);
  }

  responseLabel(response?: 'yes' | 'once' | 'no' | null): string | null {
    if (response === 'yes') return 'als Regel bestätigt';
    if (response === 'once') return 'nur dieses Mal';
    if (response === 'no') return 'als Präferenz verneint';
    return null;
  }

  /** Share of trains that reached their target, for the headline. */
  readonly arrivedPct = computed(() => {
    const k = this.kpis();
    return k.total === 0 ? 0 : Math.round((k.arrived / k.total) * 100);
  });
}
