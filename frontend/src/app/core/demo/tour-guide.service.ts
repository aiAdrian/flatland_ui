import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { SessionStore } from '../session.store';
import { TourContextService } from './tour-context.service';
import { GuideStepId, TourGuideStep } from './tour-briefings';

/**
 * Progress through the running tour's guide (`TourBriefing.guide`).
 *
 * A step is ticked when the run shows it actually happened, read from the same
 * signals the panels use, and a tick is never taken back. Steps marked
 * `afterEpisode` are not ticked here. The current step drives the hint and the
 * panel highlight.
 */
@Injectable({ providedIn: 'root' })
export class TourGuideService {
  private readonly store = inject(SessionStore);
  private readonly tour = inject(TourContextService);
  private readonly _done = signal<ReadonlySet<GuideStepId>>(new Set());

  readonly steps = computed<TourGuideStep[]>(() => this.tour.briefing()?.guide ?? []);
  readonly active = computed(() => this.steps().length > 0);
  readonly done = this._done.asReadonly();

  /** First step not yet experienced. During the run, steps that belong after the
   *  episode are skipped; once the shift is over they are next in line. */
  readonly current = computed<TourGuideStep | null>(() => {
    const afterShift = this.store.shiftReviewOpen();
    return this.steps().find((s) => (afterShift || !s.afterEpisode) && !this._done().has(s.id)) ?? null;
  });

  /** Every step that happens during the run is done. */
  readonly liveDone = computed(
    () => this.active() && this.steps().filter((s) => !s.afterEpisode).every((s) => this._done().has(s.id)),
  );

  /** For steps the run cannot observe on its own (the debrief sections). */
  markDone(id: GuideStepId): void {
    if (this._done().has(id)) return;
    this._done.set(new Set([...this._done(), id]));
  }

  readonly highlightPanelType = computed(() => this.current()?.panelType ?? null);

  private readonly reached = computed<Set<GuideStepId>>(() => {
    const reached = new Set<GuideStepId>();
    const malfunction = this.store
      .agents()
      .some((a) => !!a.is_malfunctioning || (a.malfunction_remaining ?? 0) > 0);
    const impact = this.store.impact().length > 0;
    if (malfunction || impact) reached.add('detect');
    if (impact) {
      reached.add('assess');
      reached.add('alternatives');
    }
    const human = this.store.decisionLog().filter((e) => e.accountableOwner === 'human');
    if (human.length > 0) reached.add('decide');
    const step = this.store.elapsedSteps();
    if (human.some((e) => step > e.simStep)) reached.add('execute');
    if (human.some((e) => !!e.rationale)) reached.add('reflect');
    if (this.store.learningRecords().length > 0) reached.add('ai-learns');
    return reached;
  });

  constructor() {
    effect(() => {
      this.store.session()?.id;
      this.tour.briefing();
      untracked(() => this._done.set(new Set()));
    });

    effect(() => {
      if (!this.active()) return;
      const reached = this.reached();
      untracked(() => {
        const done = this._done();
        if ([...reached].every((id) => done.has(id))) return;
        this._done.set(new Set([...done, ...reached]));
      });
    });
  }
}
