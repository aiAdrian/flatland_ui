# i18n strategy — runtime language support (EN base, DE next)

> Dated plan, 2026-07-11. Decision: the app mixes DE/EN inline strings today
> (no i18n library). We want long-term multi-language support with a runtime
> toggle. This sets the direction and the governance that stops the mixing from
> growing. Relates to the planned DE/EN toggle (memory: `planned_i18n_language_toggle`).

## Decisions

- **Source language = English.** Keys and base copy are authored in English;
  code, comments and consortium docs are already English, so EN is the neutral
  base. German is added as a translation, surfaced via the toggle.
- **Library = Transloco** (runtime locale switch, no per-locale rebuild; works
  with standalone + signals). **Not** `@angular/localize` — it compiles one
  bundle per locale and makes a live toggle awkward.
- **Governance mirrors the colour gate.** We already stop new hardcoded colours
  with a stylelint gate + opportunistic migration + a `LEGACY_DEBT` register
  (`frontend/.stylelintrc.cjs`). Apply the exact same pattern to strings:
  - **New UI strings must go through translation keys** — no new inline literals.
  - **Migrate legacy inline text opportunistically** when a file is touched.
  - Keep a debt register (files still holding inline copy); shrink it over time.
  - Optionally add a lint/check later to enforce "no new inline user-facing text".

This makes the mixed-language problem **shrink over time** instead of a big-bang
translation.

## Approach

1. **Add Transloco** (`@jsverse/transloco`), two locales: `en` (default), `de`.
   Translation files `src/assets/i18n/en.json`, `de.json`.
2. **A language signal + toggle** — wire the already-planned DE/EN switch to
   `TranslocoService.setActiveLang`; persist choice (localStorage), default `en`.
3. **Key convention** — namespaced by feature, e.g. `rationale.why.title`,
   `recommendations.accept`. Keep keys English-descriptive.
4. **First migration target: the just-shipped rationale-capture** (currently
   German inline — deck slide 7). Move its strings to keys as the worked example,
   then migrate other panels opportunistically.
5. **Debt register** — a short list (doc or config) of files still holding inline
   user-facing text; remove entries as they migrate.

## Do-not / risks

- Don't machine-translate blindly — study-facing copy (survey, mode intros)
  needs human wording; validated survey items come from `AI4REALNET/hmisurveys`
  (CLAUDE.md), not home-grown translations.
- Don't route log/debug/dev-only strings through i18n — user-facing only.
- Pluralisation/number formatting: use Transloco's built-ins, not string concat.
- The default-locale choice (EN) is the one hard-to-reverse decision — settled here.

## Verification

- Toggle flips all migrated strings live (no reload); default is EN.
- `en.json` / `de.json` have matching key sets (a check can enforce parity).
- Existing tests green; no inline literals added in touched files.

## Not now (later)

- A lint gate for "no new inline user-facing text" (parallel to `color-no-hex`).
- Locale-aware date/number formatting across the app.
- Additional locales beyond DE/EN.
