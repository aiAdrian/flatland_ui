import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { SessionStore } from '../session.store';
import { OperatorModelService } from '../operator-model.service';
import { InteractionMode } from '../events/event-types';
import { ModeIntro } from './mode-intro-configs';
import { TourBriefing } from './tour-briefings';

/**
 * The running tour's briefing, for surfaces outside the tour pages: the mode
 * intro, the Co-Learning module badges on panels, the map fit. Everything here
 * is gated on `demoActive`, so experiments and free sessions never see it.
 */
@Injectable({ providedIn: 'root' })
export class TourContextService {
  private readonly store = inject(SessionStore);
  private readonly _briefing = signal<TourBriefing | null>(null);

  readonly briefing = computed(() => (this.store.demoActive() ? this._briefing() : null));
  readonly mapFocusCols = computed(() => this.briefing()?.mapFocusCols ?? null);
  readonly hasDebrief = computed(() => !!this.briefing()?.debrief);
  readonly reasonDialog = computed(() => !!this.briefing()?.reasonDialog);

  private readonly operatorModel = inject(OperatorModelService);
  private operatorIdBeforeTour: string | null = null;

  constructor() {
    // The operator model keys preferences by operator id, not by session. A tour
    // that asks for it runs under its own id and hands the previous one back
    // when the tour ends.
    effect(() => {
      const fresh = !!this.briefing()?.freshOperatorProfile;
      untracked(() => {
        if (fresh && this.operatorIdBeforeTour === null) {
          this.operatorIdBeforeTour = this.operatorModel.operatorId();
          this.operatorModel.operatorId.set(`interview-${Date.now()}`);
        } else if (!fresh && this.operatorIdBeforeTour !== null) {
          this.operatorModel.operatorId.set(this.operatorIdBeforeTour);
          this.operatorIdBeforeTour = null;
        }
      });
    });
  }

  set(briefing: TourBriefing | undefined): void {
    this._briefing.set(briefing ?? null);
  }

  clear(): void {
    this._briefing.set(null);
  }

  modeIntroFor(mode: InteractionMode): ModeIntro | null {
    return this.briefing()?.modeIntros?.[mode] ?? null;
  }

  /** Module name when this panel type is one of the tour's highlighted modules. */
  moduleFor(panelType: string | undefined): string | null {
    if (!panelType) return null;
    return this.briefing()?.moduleBadges?.[panelType] ?? null;
  }
}
