import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { TranslocoService } from '@jsverse/transloco';

/** Interpolation parameters for a translation (`{{name}}` placeholders). */
export type TranslateParams = Record<string, unknown>;

export type Lang = 'en' | 'de' | 'fr';

const STORAGE_KEY = 'flatland.lang';
const LANGS: readonly Lang[] = ['en', 'de', 'fr'];

/** The language a visitor chose last time, else English — the source language. */
export function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && (LANGS as readonly string[]).includes(stored)) return stored as Lang;
  } catch {
    // localStorage may be unavailable (private mode, embedded preview).
  }
  return 'en';
}

/**
 * The app's language, as a signal, plus a translate helper for copy that lives
 * in TypeScript rather than in a template.
 *
 * Scope follows docs/plans/i18n-strategy.md: English is the source, German and
 * French are translations, and English is the fallback — a key missing in `de`
 * or `fr` renders in English instead of failing. Internal tools and the
 * questionnaires are deliberately not translated.
 */
@Injectable({ providedIn: 'root' })
export class LanguageService {
  private readonly transloco = inject(TranslocoService);

  /** Labels are endonyms: a language is named in itself, whichever is active. */
  readonly languages: ReadonlyArray<{ code: Lang; label: string }> = [
    { code: 'en', label: 'English' },
    { code: 'de', label: 'Deutsch' },
    { code: 'fr', label: 'Français' },
  ];

  readonly lang = signal<Lang>(initialLang());

  /**
   * Bumped whenever a translation file finishes loading or the language
   * changes. `t()` reads it, so any `computed` that translates re-evaluates on
   * its own — no caller has to remember to subscribe.
   */
  private readonly version = signal(0);

  constructor() {
    const events = this.transloco.events$.subscribe((e) => {
      if (e.type === 'translationLoadSuccess' || e.type === 'langChanged') {
        this.version.update((v) => v + 1);
      }
    });
    inject(DestroyRef).onDestroy(() => events.unsubscribe());
  }

  setLang(code: Lang): void {
    if (!LANGS.includes(code)) return;
    this.lang.set(code);
    this.transloco.setActiveLang(code);
    try {
      localStorage.setItem(STORAGE_KEY, code);
    } catch {
      // Not persisting is acceptable; the choice still applies to this visit.
    }
  }

  /**
   * Translate a key. When no translation exists in any language — typically
   * data-driven copy whose English source lives in TypeScript (tours, mode
   * intros) — `fallback` is returned, so a missing key never reaches the screen.
   */
  t(key: string, params?: TranslateParams, fallback?: string): string {
    this.version();
    this.lang();
    const value = this.transloco.translate<string>(key, params ?? {});
    if ((value === key || value === '') && fallback !== undefined) return fallback;
    return value;
  }
}
