import { EnvironmentProviders, importProvidersFrom } from '@angular/core';
import { TranslocoTestingModule } from '@jsverse/transloco';
import en from '../../../public/i18n/en.json';

/**
 * Transloco for component tests: the real English source, preloaded.
 *
 * Specs assert on what a component renders, so they need the actual copy rather
 * than raw keys — and English, because that is the source language
 * (docs/plans/i18n-strategy.md). No HTTP, so a spec never waits for a file.
 */
export function provideTranslocoTesting(): EnvironmentProviders[] {
  return [
    importProvidersFrom(
      TranslocoTestingModule.forRoot({
        langs: { en: en as Record<string, unknown> },
        translocoConfig: {
          availableLangs: ['en'],
          defaultLang: 'en',
          fallbackLang: 'en',
          missingHandler: { useFallbackTranslation: true, logMissingKey: false },
        },
        preloadLangs: true,
      }),
    ),
  ];
}
