import {
  ApplicationConfig,
  CUSTOM_ELEMENTS_SCHEMA,
  inject,
  isDevMode,
  provideAppInitializer,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { TranslocoService, provideTransloco } from '@jsverse/transloco';
import { firstValueFrom, forkJoin } from 'rxjs';
import { initialLang } from './core/i18n/language.service';
import { TranslocoHttpLoader } from './core/i18n/transloco-loader';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideHttpClient(withFetch()),
    // i18n (docs/plans/i18n-strategy.md): English source, German and French
    // translations, English as the fallback. `logMissingKey` stays off because
    // partial coverage is intended — not every page exists in every language.
    provideTransloco({
      config: {
        availableLangs: ['en', 'de', 'fr'],
        defaultLang: initialLang(),
        fallbackLang: 'en',
        reRenderOnLangChange: true,
        prodMode: !isDevMode(),
        missingHandler: { useFallbackTranslation: true, logMissingKey: false },
      },
      loader: TranslocoHttpLoader,
    }),
    // Load English and the chosen language before the first render, so the
    // start screen never flashes raw keys.
    provideAppInitializer(() => {
      const transloco = inject(TranslocoService);
      const lang = initialLang();
      return firstValueFrom(forkJoin([transloco.load('en'), transloco.load(lang)]));
    }),
  ],
};
