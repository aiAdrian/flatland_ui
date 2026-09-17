import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
import { MODE_INTRO_LABELS_EN, modeIntroFor } from '../../core/demo/mode-intro-configs';
import { TourContextService } from '../../core/demo/tour-context.service';

/**
 * Guided-demo mode-intro screen: shown before the human starts each mode's
 * scenario, so the mode is explained before they act in it (not learned by
 * trial and error mid-run). Content comes from mode-intro-configs.ts, or from
 * the running tour's briefing when it brings its own.
 */
@Component({
  selector: 'app-mode-intro',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './mode-intro.component.html',
  styleUrl: './mode-intro.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ModeIntroComponent {
  store = inject(SessionStore);
  private readonly tour = inject(TourContextService);

  readonly totalModes = computed(() => this.store.demoSequence().length);

  readonly intro = computed(() => {
    const mode = this.store.interactionMode();
    return this.tour.modeIntroFor(mode) ?? modeIntroFor(mode);
  });

  readonly labels = computed(() => this.intro().labels ?? MODE_INTRO_LABELS_EN);

  startScenario(): void {
    this.store.dismissDemoIntro();
  }

  exit(): void {
    this.store.stopDemo();
  }
}
