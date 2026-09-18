import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
import { MODE_INTRO_LABELS_EN, ModeIntro, ModeIntroLabels, modeIntroFor } from '../../core/demo/mode-intro-configs';
import { TourContextService } from '../../core/demo/tour-context.service';
import { LanguageService } from '../../core/i18n/language.service';

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

  private readonly i18n = inject(LanguageService);

  /**
   * A tour that brings its own intro (a briefing) keeps it verbatim — its
   * language is part of the content, e.g. the German interview tour. Otherwise
   * the English source in `MODE_INTROS` is translated key by key, falling back
   * to the English text for anything a language does not cover yet.
   */
  readonly intro = computed<ModeIntro>(() => {
    const mode = this.store.interactionMode();
    const own = this.tour.modeIntroFor(mode);
    if (own) return own;

    const base = modeIntroFor(mode);
    const t = (field: string, fallback: string) => this.i18n.t(`intro.${mode}.${field}`, undefined, fallback);
    return {
      ...base,
      wp: t('wp', base.wp),
      title: t('title', base.title),
      tagline: t('tagline', base.tagline),
      whatHappens: t('whatHappens', base.whatHappens),
      focusView: t('focusView', base.focusView),
      yourRole: t('yourRole', base.yourRole),
      goal: t('goal', base.goal),
      whatYouCanControl: base.whatYouCanControl.map((item, i) => t(`control.${i}`, item)),
      watchFor: base.watchFor.map((item, i) => t(`watch.${i}`, item)),
    };
  });

  readonly labels = computed<ModeIntroLabels>(() => {
    const own = this.intro().labels;
    if (own) return own;
    const entries = Object.entries(MODE_INTRO_LABELS_EN).map(
      ([key, fallback]) => [key, this.i18n.t(`intro.labels.${key}`, undefined, fallback)],
    );
    return Object.fromEntries(entries) as ModeIntroLabels;
  });

  startScenario(): void {
    this.store.dismissDemoIntro();
  }

  exit(): void {
    this.store.stopDemo();
  }
}
