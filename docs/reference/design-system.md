# Design system — Lyne consistency, coupling, and independence

> The reference doc for "what design system do we actually have." Two
> questions, kept deliberately apart because they have different owners and
> different costs:
>
> - **Part I — Consistency.** Given that [frontend-lyne-conventions.md](frontend-lyne-conventions.md)
>   prescribes a specific vocabulary (`sbb-title`, `sbb-card`, `sbb-status`, …),
>   how consistently do the ~50 widgets under `frontend/src/app/features/`
>   actually use it — both against the convention and against each other?
> - **Part II — Independence.** How hard is it to fork SBB Lyne or replace it,
>   given that we want to open-source this codebase (OpenRail Association and
>   similar) while continuing to use Lyne for internal SBB applications?
>
> Part I is grounded in a grep across `frontend/src/app/features/` on
> 2026-09-05. Part II is grounded in a grep/read of `frontend/src/` and of
> `node_modules/@sbb-esta/lyne-elements@4.14.0` on 2026-08-23; numbers there
> are unchanged except where Part I's fixes are noted inline. Counts are
> occurrences unless stated otherwise.
>
> Companion of [frontend-lyne-conventions.md](frontend-lyne-conventions.md)
> (the rules both parts check against) and
> [colour-usage-audit.md](colour-usage-audit.md).

## Part I — Widget consistency audit (2026-09-05)

### Summary

**Between widgets**, consistency is good: the same handful of Lyne components
and the same grey-token vocabulary recur everywhere, and two structural rules
are followed without exception. **Against the convention**, there are three
whole Lyne component categories the codebase never adopted, despite
`frontend-lyne-conventions.md` prescribing them explicitly — not occasional
drift, the default.

### What's consistent

- **`sbb-expansion-panel`** dominates (25 uses, ~55 % of all Lyne component
  usage) with a uniform header/content pattern.
- **Grey tokens** — `--sbb-color-charcoal/granite/cloud/milk/white` — are 77 %
  of all token references (see Part II §2b). A real mapping table, not
  ad-hoc picks.
- **`sbb-tag`/`sbb-tag-group`** (22 uses) is the deliberately-adopted
  facet-chip vocabulary in the Widget and Algorithm Galleries.
- **`CUSTOM_ELEMENTS_SCHEMA`**: zero components use an `<sbb-*>` tag without
  declaring it. The registration convention in
  [frontend-lyne-conventions.md §3](frontend-lyne-conventions.md) is followed
  without exception.
- No `sbb-button`/`sbb-secondary-button`/`sbb-transparent-button` is ever used
  with `routerLink` — the `*-link` rule (§4) holds.
- `npm run lint:styles` passes clean — the ~30 files with hex/rgba are all
  correctly registered in `LEGACY_DEBT` (`.stylelintrc.cjs`), no new
  violation.

### The three adopted-in-name-only categories

| Lyne component | Convention says | Reality (before 2026-09-05) |
|---|---|---|
| `sbb-title` | Use for every heading; "don't fake headings with styled divs" | **0 uses.** All 35 headings across 20 files were raw `<h1>`–`<h4>`, several with custom classes (`.panel-title`, `.intro-title`, `.so-tile__title`) doing what `visual-level` is for |
| `sbb-card` | Content cards, `color="milk"` + `sbb-card-link slot="action"` | **0 uses.** 11 files hand-roll `.card`/`__card` classes |
| `sbb-status` | Status pills via the `type` prop, not hand-coloured badges | **0 uses.** 29 files (`agents-table`, `director-directive`, `flatland-map`, `recommendations-panel`, `strategy-options`, `timetable`, `toolbar`, …) hand-roll `.status`/`.badge`/`.pill`/`.chip` classes |

**`sbb-title` status: fixed 2026-09-05** — see [§ Fix log](#fix-log-2026-09-05)
below. `sbb-card` and `sbb-status` are still open; see Part I's action list.

### The largest single inconsistency: native `<button>`

**34 of ~50** widget templates use raw `<button>` instead of
`sbb-button`/`sbb-secondary-button`/`sbb-transparent-button`/`sbb-mini-button`
— e.g. [toolbar](../../frontend/src/app/features/toolbar/toolbar.component.html),
[left-sidebar](../../frontend/src/app/features/left-sidebar/left-sidebar.component.html),
[recommendations-panel](../../frontend/src/app/features/recommendations-panel/recommendations-panel.component.html),
[director-directive](../../frontend/src/app/features/director-directive/director-directive.component.html),
[flatland-map](../../frontend/src/app/features/flatland-map/flatland-map.component.html).
Only 8 files use `sbb-button` at all. Some of this is likely legitimate
(icon-only toggles, hit-targets inside an SVG overlay where Lyne doesn't fit),
but at 34 files it is no longer an exception — it is the actual
inter-widget inconsistency, more than any single missing component.

### A lint blind spot

[flatland-map.component.html:219,308,318,420,427](../../frontend/src/app/features/flatland-map/flatland-map.component.html)
hardcodes hex colours directly in SVG attribute bindings (`#ffffff`,
`#eb0000`, `#212121`, `#f939e9`). The "no hardcoded colours" rule (CLAUDE.md /
frontend-lyne-conventions §1) is enforced only by `stylelint` on `*.scss` —
inline template attribute bindings (`[attr.fill]="…"`) are invisible to it.
This is currently the only file that actively violates the colour rule
without the lint gate noticing.

### Action list (priority order)

1. ~~**Adopt `sbb-title`.**~~ **Done, 2026-09-05** — see fix log.
2. **Adopt `sbb-status` for status pills** — 29 files are candidates; highest
   remaining consistency payoff, since status/severity framing is exactly what
   needs to read clearly and identically across the three interaction modes.
3. **Tokenise `flatland-map.component.html`'s inline hex colours**, and close
   the lint blind spot itself — e.g. a CI grep for `#[0-9a-f]{3,6}` across
   `*.html`, not just `*.scss`.
4. **Evaluate `sbb-card`** for the 11 `.card`/`__card` sites — probably not a
   1:1 fit everywhere (some are table rows, not cards); worth a spec question
   at the next `/create-widget` pass rather than a blanket migration. Two of
   the clearest candidates, checked 2026-09-05:
   [`option-card`](../../frontend/src/app/features/recommendations-panel/recommendations-panel.component.html)
   (recommendations-panel) and
   [`scenario-card`](../../frontend/src/app/features/scenario-panel/scenario-panel.component.html)
   (scenario-panel). Both are **multi-action containers** (Accept/Reject/pin
   buttons, or a hover preview) rather than a single-action card, so the fit
   is the plain `<sbb-card color="milk">` wrapper — **not**
   `sbb-card-link`/`sbb-card-button` (those want exactly one card-wide action,
   slotted before the content, which doesn't match either component):

   ```html
   <!-- before -->
   <div class="option-card"
        [class.is-recommended]="card.isRecommended"
        [class.urgent]="isUrgent(card.rec)">
     ...
   </div>

   <!-- after -->
   <sbb-card color="milk"
             class="option-card"
             [class.is-recommended]="card.isRecommended"
             [class.urgent]="isUrgent(card.rec)">
     ...
   </sbb-card>
   ```

   Existing modifier classes (`.is-recommended`, `.urgent`, …) stay and keep
   driving border/background colour via the component's own SCSS — same
   drop-in shape as the `sbb-title` migration: `sbb-card` only supplies
   structure/base colour, not the modifier styling. Needs
   `@sbb-esta/lyne-elements/card.js` added to `main.ts`;
   `CUSTOM_ELEMENTS_SCHEMA` is already present in both components (added for
   `sbb-title`). Not yet applied — recorded here as the concrete next step,
   not done.
5. **Triage the native-`<button>` backlog file by file** — not a blanket
   migration. Per file: "a Lyne button fits" vs. "a deliberate exception"
   (e.g. an SVG-overlay hit-box), and write the exception down instead of
   leaving it silent.

### Fix log, 2026-09-05

**`sbb-title` adopted.** `frontend/src/main.ts` now imports
`@sbb-esta/lyne-elements/title.js` (one import registers `sbb-title` fully;
no sub-path needed, unlike buttons). All 35 native headings across 20 files
were converted to `<sbb-title level="N" visual-level="M">`, keeping each
element's existing class (`.panel-title`, `.title`, `.intro-title`, …) so the
components' own SCSS overrides continue to apply unchanged — `sbb-title`'s
`:host` styles lose the cascade tie to page-authored class rules at equal
specificity, which is why this was a safe drop-in rather than a restyle.
`level` mirrors the semantic nesting the old `h1`–`h4` expressed;
`visual-level` was set two steps smaller where the heading was a small
panel/card title (the common case — panel headers, card titles), left equal
to `level` for page-level titles (Widget/Algorithm Gallery, Help & About, mode
intro). `npx ng build` is clean; verified in the browser preview (Widget
Gallery, `/widgets`) that titles render as bold headings at the expected
size. `sbb-card` and `sbb-status` remain open (action items 2 and 4 above).

## Part II — Design-system independence

> Answers: how hard is it to fork SBB Lyne or replace it, given that we want
> to open-source this codebase while continuing to use Lyne internally?

### 1. Three concerns that get conflated

"It's odd that SBB is everywhere" is really three separate problems with three
different costs. Keeping them apart is most of the work.

| | Status | Cost to fix |
|---|---|---|
| **Licence** | Already fine — Lyne is **MIT** | none |
| **Branding** | Real but cosmetic — `sbb-` in element and token names | medium |
| **Runtime dependency** | **The actual problem** — proprietary font from SBB servers | small |

#### 1a. Licence — already solved

Lyne is **MIT**, published at
`github.com/sbb-design-systems/lyne-components`. Nothing about it blocks an
open-source release. This is not a problem that needs solving.

#### 1b. Branding — cosmetic

35 distinct `--sbb-*` tokens and 16 `sbb-*` element names, plus SBB red as
`--sbb-color-primary`. Visible in source, invisible to users.

#### 1c. Runtime dependency — the one that matters

Lyne's `core.css` and `standard-theme.css` declare the font family `SBB` with:

```css
src: url("https://cdn.app.sbb.ch/fonts/v1_9_subset/SBBWeb-Roman.woff2");
```

The typeface is **not part of the MIT package** — no font binaries ship with it.
It is SBB's proprietary corporate typeface, fetched at runtime from SBB
infrastructure. For a third party running our open-source release that means
two unacceptable things at once: use of a typeface they have no licence for, and
an outbound call to servers that are not theirs. Unlike the naming, this is not
cosmetic.

### 2. How deep is the coupling? (measured)

Shallower than expected.

#### 2a. Components — 17 distinct, 133+ occurrences, 31+ files

| Component | Uses |
|---|---:|
| `sbb-expansion-panel` (+ `-header`, `-content`) | **73** |
| buttons (`button`, `secondary-`, `transparent-`, `menu-button`) | 40 |
| `sbb-divider` | 9 |
| form controls (`checkbox`, `checkbox-group`, `radio-button`, `radio-button-group`, `toggle-check`) | 7 |
| `sbb-menu`, `sbb-menu-link` | 2 |
| `sbb-loading-indicator-circle` | 2 |
| `sbb-title` (added 2026-09-05, Part I) | 35 |

The expansion-panel trio alone is **55 %** of all usage. Practically speaking
there is *one* component that would be expensive to replace, plus buttons.

> **Update, 2026-09-05:** `sbb-tag` was adopted deliberately — it's now the
> facet-chip vocabulary in the Widgets and Algorithm Galleries (22 uses across
> both templates). The dead `sbb-tag { … }` rules this note used to flag in
> `toolbar.component.scss` and `view-toggle.component.scss` (which never had
> any `sbb-tag` element to style — `view-toggle` actually uses
> `sbb-checkbox-group`) have since been removed. `sbb-title` was adopted the
> same day (Part I) — see the fix log above.

#### 2b. Tokens — 1255 references, but only 35 distinct

| Token | Uses |
|---|---:|
| `--sbb-color-charcoal` | 280 |
| `--sbb-color-granite` | 246 |
| `--sbb-color-cloud` | 220 |
| `--sbb-color-white` | 129 |
| `--sbb-color-milk` | 92 |
| *(subtotal — four greys + white)* | **967 = 77 %** |
| `--sbb-color-red` | 48 |
| remaining 29 tokens | 240 |

Across 62 files. Three quarters of the entire "Lyne dependency" in styling is
**four greys and white**. That is a mapping table, not a migration.

### 3. `off-brand-theme.css` is not the answer

The package ships a file with a promising name. It is not what it sounds like:
diffed against `standard-theme.css` it differs in **exactly four lines** —
`--sbb-color-primary{,85,125,150}` switch from red to royal blue. Same SBB
typeface, same SBB CDN, same token names. It exists for SBB subsidiaries, not
for de-branding.

### 4. Options

| | Effort | Satisfies "transferable + Lyne internally"? |
|---|---|---|
| **A** Decouple the font only | hours | partly |
| **B** Complete the adapter layer | days | **yes** |
| **C** Fork Lyne | weeks + ongoing | no |
| **D** Replace with a neutral design system | weeks | only after B |

**C is ruled out.** MIT permits it, but a fork with renamed `sbb-*` elements
severs the upgrade path permanently — and we *want* Lyne internally. That buys
the maintenance burden of a 20 MB component library and keeps two codebases.

**B is the answer to the actual requirement**, and half of it already exists.
`styles.scss` carries an indirection layer today — `--app-kind-*`,
`--app-severity-*`, `--app-positive`, `--layer-color-*` point at Lyne tokens
instead of at hex. The "no hardcoded colours" rule in
[CLAUDE.md](../../CLAUDE.md) built that seam without naming it. What is missing:

- **~35 token aliases** (`--app-text-primary: var(--sbb-color-charcoal)`, …),
  of which 5 carry 77 % of usage
- **17 thin component wrappers**, of which `expansion-panel` is 55 % — so
  realistically *one* wrapper that matters, plus buttons
- **font decoupling** — done, see §5

After B, Lyne is one theme adapter among several: internal builds load the Lyne
adapter, open-source builds a neutral one. Same components, same code, a build
flag.

### 5. Decision, 2026-08-23

**A is implemented. B is the agreed direction. C is rejected. D stays open and
becomes cheap only once B exists.**

#### What was implemented

| File | Change |
|---|---|
| `frontend/package.json` | `@fontsource-variable/inter ^5.3.0` |
| `frontend/src/styles.scss` | Fontsource imports; `--sbb-typo-font-family` override; removed the stale proprietary `"Helvetica Now Text"` fallback |
| `frontend/postcss-drop-sbb-fonts.cjs` | Removes `@font-face` rules whose `src` points at `cdn.app.sbb.ch` |
| `frontend/.postcssrc.json` | Registers that plugin |

**Why a token override is sufficient:** the app never writes
`font-family: SBB` literally — it obtains the face exclusively through
`--sbb-typo-font-family`. CSS custom properties inherit across shadow
boundaries, so overriding it on `:root` also reaches Lyne's web components.
Nothing then matches the family `SBB`, and the browser never requests the
SBB `woff2`. The PostCSS plugin is the second line: it removes the now-dead
rules so the URLs do not sit in the shipped artefact, and so a Lyne upgrade
cannot reintroduce them.

#### Why Inter (since 2026-09-03; IBM Plex Sans before that)

SIL OFL 1.1, drawn for screen UIs: a large x-height and disambiguated glyphs
(`1`/`l`/`I`, `0`/`O`) — the property that matters when a dispatcher reads
train IDs and times off a dense table at a glance. Self-hosted from
`node_modules` via `@fontsource-variable` — **no CDN**, the app stays
offline-capable. One variable axis 100–900 (~48 KB latin) replaces static
cuts, so the 124 places using `font-weight: 600` render as real SemiBold
instead of a synthesised bold. Further subsets (latin-ext, Greek, Cyrillic)
are present and fetched only on demand via `unicode-range` — relevant if the
planned language switch goes beyond DE/EN.

Two caveats worth naming:

- **Figures are proportional by default.** IBM Plex Sans led with tabular
  figures; Inter does not. Where numbers have to line up in columns, the
  component sets `font-variant-numeric: tabular-nums` (Inter ships the
  tabular set, it is just not the default).
- **The name is neutral**, which is why the swap happened — "IBM" formally
  traded one company name for another, even though the licence difference was
  substantive. **Source Sans 3** and **Public Sans** remain equivalent
  neutral-named options, both `@fontsource-variable` packages.

#### Verification

A full page load produces **zero requests to external hosts**; the only font
requests are the two self-hosted files:

```
GET /media/inter-latin-wght-normal.woff2  → 200
GET /media/inter-latin-wght-italic.woff2  → 200
```

```bash
npx ng build && grep -c "cdn.app.sbb.ch" dist/frontend/browser/*.css   # → 0
```

### 6. Swapping the font

Three steps, no other file involved:

```bash
npm i @fontsource-variable/source-sans-3
```

then in `frontend/src/styles.scss` change the two `@import` lines and the value
of `--sbb-typo-font-family`.

### 7. Open items

- **Complete B** — the token-alias layer and the `expansion-panel` wrapper are
  the only two pieces of real work.
- **A neutral design system for a control room.** Lyne is a *passenger-facing*
  system — its catalogue (`journey-header`, `timetable-occupancy-icon`,
  `teaser-hero`, `carousel`, pearl chains) is built for sbb.ch, not for a
  dispatcher workstation. What a control room needs — dense data tables,
  split panes, keyboard navigation, dark mode for shift work — Lyne only
  partly provides. **What we would lose:** Lyne has `light-dark()` throughout,
  so the dark mode planned in CLAUDE.md is a config flip with Lyne and our own
  work without it. Candidate replacements (Shoelace/Web Awesome, Adobe Spectrum
  Web Components, Carbon, Material Web) have **not** been evaluated.
- **`sbb-status` and `sbb-card` adoption** — see Part I's action list (items 2
  and 4); the same "adapter, don't fork" logic in §4 applies once they're in
  use: two more thin wrappers, not new debt.
