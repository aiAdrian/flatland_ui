import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
import { MODE_INTROS, modeIntroFor } from '../../core/demo/mode-intro-configs';

/**
 * Guided-demo mode-intro screen: shown before the human starts each mode's
 * scenario, so the mode is explained before they act in it (not learned by
 * trial and error mid-run). Content comes from mode-intro-configs.ts.
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

  readonly totalModes = MODE_INTROS.length;

  readonly intro = computed(() => modeIntroFor(this.store.interactionMode()));

  startScenario(): void {
    this.store.dismissDemoIntro();
  }

  exit(): void {
    this.store.stopDemo();
  }
}
