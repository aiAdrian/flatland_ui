# i18n strategy — runtime language support (EN source, DE and FR)

> Dated plan, 2026-07-11. **Revised 2026-09-17 (danib):** three languages instead
> of two, a scope that is deliberately *not* "every page in every language", and
> sizes measured against the code. The app mixes DE/EN inline strings today (no
> i18n library). We want multi-language support with a runtime toggle, and the
> governance that stops the mixing from growing. Tracked in issue #59.

## Decisions

- **Source language = English.** Keys and base copy are authored in English;
  code, comments and consortium docs are already English, so EN is the neutral
  base. **German and French** are translations, surfaced via the toggle.
- **Library = Transloco** (runtime locale switch, no per-locale rebuild; works
  with standalone + signals). **Not** `@angular/localize` — it compiles one
  bundle per locale and makes a live toggle awkward.
- **Not every page in every language.** English is the fallback: a key missing
  in `de` or `fr` renders in English instead of failing
  (`fallbackLang: 'en'`, `missingHandler.useFallbackTranslation: true`). This
  replaces the earlier key-set parity requirement with a **coverage report** —
  which screens are complete in which language — so partial coverage is a
  visible state, not a broken build.
- **Governance mirrors the colour gate.** We already stop new hardcoded colours
  with a stylelint gate + opportunistic migration + a `LEGACY_DEBT` register
  (`frontend/.stylelintrc.cjs`). Same pattern for strings:
  - **New UI strings in scope go through translation keys** — no new inline literals.
  - **Migrate legacy inline text** phase by phase (below), and opportunistically
    when a file is touched.
  - Keep a debt register of in-scope files still holding inline copy.

## Scope — by who sees it

| Tier | What | Languages |
|---|---|---|
| **In scope** | Start screen · tours, mode intros, tour briefings · the working screen and its widgets (left status, centre views, right decision panels per mode, toolbar, footer, shift review) · backend text that reaches the UI · scenario and disturbance descriptions | EN · DE · FR |
| **English only** | Internal tools: Layout Designer, Infrastructure Builder, Widget Gallery and the widget-catalog metadata, Algorithms Gallery, Contribute, Help/About | EN |
| **Deferred** | **Questionnaires.** They are validated instruments (`AI4REALNET/hmisurveys`); self-translated items would compromise validity. Revisit when the source offers more languages — not before. | as the source provides |

## Size — measured 2026-09-17

Heuristic counts over `frontend/src/app` and `backend/app`, prose only (a first
pass that counted SVG/CSS and log text was discarded). Treat as ±25 %.

| | Words | Strings | Notes |
|---|---:|---:|---|
| In scope — templates | ≈ 2 950 | ≈ 850 | 50 components + `app.component.html` |
| In scope — copy in TypeScript | ≈ 2 900 | ≈ 300 | tour briefings (`core/demo/tour-briefings.ts`) are the largest block; mode intros, strategy copy, layout preset names and purposes |
| In scope — backend + fixtures | ≈ 450 | ≈ 65 | policy names, notifications, disturbance names/descriptions |
| **In scope total** | **≈ 6 300** | **≈ 1 200** | per target language: DE and FR each |
| English only (internal tools) | ≈ 4 850 | — | widget-catalog metadata alone ≈ 2 950 |

Two things the word count understates:

- **≈ 170 strings are German inline today.** They need an English source first;
  the German translation is then nearly free.
- **The backend writes its own sentences.** Those can only be translated if it
  returns codes + parameters and the frontend owns the wording.

## Phases

Effort scale as in `widget-catalog.md`: S ≤ 1 day · M 1–3 days · L 3–5+ days.

| Phase | What | Effort |
|---|---|---|
| **1** | Transloco, `en`/`de`/`fr`, language signal + toggle persisted in localStorage, EN fallback, coverage report | S |
| **2** | The guided path: start screen, tours, mode intros, tour briefings. First visible result: a complete trilingual entry, the rest falling back to English | M |
| **3** | The working screen and its widgets | L |
| **4** | Backend text → codes + parameters; scenario and disturbance descriptions | S–M |
| — | Translation DE + FR, ≈ 6 300 words each | external, not dev time |

Phase 2 before 3 is sequencing, not scope: the widgets are in scope, the guided
path simply reaches a complete state first.

**Key convention** — namespaced by feature, English-descriptive:
`welcome.doors.introduction.title`, `intro.director.focusView`,
`recommendations.accept`. Data-driven copy (`MODE_INTROS`, `TOURS`,
`STRATEGY_COPY`, layout preset `purpose`) keeps its structure and stores keys
instead of prose.

**First worked example:** the start screen (Phase 2) — recent, English, small,
and the first thing every visitor sees. The first *German-inline* case to
migrate is `shift-review`, which shows the EN-source-first step end to end.

## Status — 2026-09-18

All four phases are implemented: 1 083 keys, DE and FR at 100 % (`npm run
i18n:coverage`). The French is a draft and needs a native reviewer before it
is used with participants.

**Phase 3 — how it was done.**
- Panel titles are matched by their stock text (`core/i18n/panel-titles.ts`),
  so a layout someone titled themselves keeps its title in every language.
- Train action options and backend-authored labels are keyed by a stable id
  (action int, package id, conflict window id); the text as sent is the
  fallback.
- Data-driven copy stores keys: `STRATEGY_COPY`, the forecast table, reason
  chips, reflection prompts, moment scoring (`reasonKeys`).
- The reason chips used to feed the preference model by matching their
  German label text. The axis is now keyed by chip id and stated on the
  decision entry (`RATIONALE_AXIS_BY_ID`); the old label table stays as the
  fallback for decisions recorded before.
- Component tests read the English source through `provideTranslocoTesting()`
  (`src/app/testing/transloco-testing.ts`).

**Left in English on purpose.** Internal tools (layout designer, galleries,
builder, contribute), the questionnaires, the cell-inspection tooltips on map
and ZWL, the plugin-host fallbacks for unmapped panels, the legacy welcome card
inside the map, the Flatland state codes `MOVING / WAITING / DONE`, and the
panels no mode offers (`director-weights`, `goal-achievement`, `kpi-filter`).

**Stays in the language it was written in.** Tour-owned content, including the
German interview tour and its debrief; backend-authored recommendation titles
and what-if summaries; train service names.

## Do-not / risks

- **Don't machine-translate study-facing copy unreviewed.** Intros, briefings and
  the decision panels shape what a participant believes the mode does. A machine
  draft is fine; each language needs a human reviewer — for FR that means a
  French speaker on the team or in the consortium.
- **Questionnaires stay out** until validated translations exist (see Scope).
- Don't route log/debug/dev-only strings through i18n — user-facing only.
- Pluralisation/number formatting: use Transloco's built-ins, not string concat.
- The default-locale choice (EN) is the one hard-to-reverse decision — settled here.

## Verification

- Toggle flips all migrated strings live (no reload); default is EN.
- A key missing in `de`/`fr` renders in English, and the coverage report lists it.
- No new inline literals in in-scope files; existing tests green.

## Not now (later)

- A lint gate for "no new inline user-facing text" (parallel to `color-no-hex`).
- Locale-aware date/number formatting across the app.
- Languages beyond EN/DE/FR.
- Translating the internal tools.
