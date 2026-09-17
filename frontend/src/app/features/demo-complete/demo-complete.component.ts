import { Component, CUSTOM_ELEMENTS_SCHEMA, EventEmitter, Output, computed, inject } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';
import { SessionStore } from '../../core/session.store';
import { LanguageService } from '../../core/i18n/language.service';

/**
 * Guided-demo completion screen, shown full-pane once the tour's modes are done
 * — mirrors app-mode-intro (full-pane, not a thin banner) so the finished
 * dashboard/session state doesn't show through underneath.
 *
 * It used to say "All 3 modes done" and list all three modes for every tour,
 * including the two-mode and one-mode ones. It now reads the tour that ran.
 */
@Component({
  selector: 'app-demo-complete',
  standalone: true,
  imports: [TranslocoPipe],
  templateUrl: './demo-complete.component.html',
  styleUrl: './demo-complete.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class DemoCompleteComponent {
  @Output() restart = new EventEmitter<void>();
  @Output() exit = new EventEmitter<void>();

  private readonly store = inject(SessionStore);
  private readonly i18n = inject(LanguageService);

  readonly modesDone = computed(() => {
    const count = this.store.demoSequence().length;
    return this.i18n.t(count === 1 ? 'complete.modesOne' : 'complete.modesMany', { count });
  });

  readonly tagline = computed(() => {
    const modes = this.store.demoSequence()
      .map((mode) => this.i18n.t(`mode.${mode}`, undefined, mode))
      .join(' → ');
    return this.i18n.t(this.store.demoSurveyEnabled() ? 'complete.taglineSurvey' : 'complete.tagline', { modes });
  });
}
