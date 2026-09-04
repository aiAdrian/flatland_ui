# Design-system independence — Lyne, branding, and open source

> Analysis **and decision record**. It answers one question: how hard is it to
> fork SBB Lyne or replace it, given that we want to open-source this codebase
> (OpenRail Association and similar) while continuing to use Lyne for internal
> SBB applications?
>
> **Every number below is grounded in a grep/read of `frontend/src/` and of
> `node_modules/@sbb-esta/lyne-elements@4.14.0` on 2026-08-23.** Counts are
> occurrences unless stated otherwise.
>
> Companion of [frontend-lyne-conventions.md](frontend-lyne-conventions.md)
> (the bare-token rule, which turns out to be the load-bearing part of the
> answer) and [colour-usage-audit.md](colour-usage-audit.md).

## 1. Three concerns that get conflated

"It's odd that SBB is everywhere" is really three separate problems with three
different costs. Keeping them apart is most of the work.

| | Status | Cost to fix |
|---|---|---|
| **Licence** | Already fine — Lyne is **MIT** | none |
| **Branding** | Real but cosmetic — `sbb-` in element and token names | medium |
| **Runtime dependency** | **The actual problem** — proprietary font from SBB servers | small |

### 1a. Licence — already solved

Lyne is **MIT**, published at
`github.com/sbb-design-systems/lyne-components`. Nothing about it blocks an
open-source release. This is not a problem that needs solving.

### 1b. Branding — cosmetic

35 distinct `--sbb-*` tokens and 16 `sbb-*` element names, plus SBB red as
`--sbb-color-primary`. Visible in source, invisible to users.

### 1c. Runtime dependency — the one that matters

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

## 2. How deep is the coupling? (measured)

Shallower than expected.

### 2a. Components — 16 distinct, 133 occurrences, 31 files

| Component | Uses |
|---|---:|
| `sbb-expansion-panel` (+ `-header`, `-content`) | **73** |
| buttons (`button`, `secondary-`, `transparent-`, `menu-button`) | 40 |
| `sbb-divider` | 9 |
| form controls (`checkbox`, `checkbox-group`, `radio-button`, `radio-button-group`, `toggle-check`) | 7 |
| `sbb-menu`, `sbb-menu-link` | 2 |
| `sbb-loading-indicator-circle` | 2 |

The expansion-panel trio alone is **55 %** of all usage. Practically speaking
there is *one* component that would be expensive to replace, plus buttons.

> **Note:** `sbb-tag` is registered in `frontend/src/main.ts:12` but appears in
> **zero** templates. The `sbb-tag { … }` rules in
> `toolbar.component.scss` and `view-toggle.component.scss` target nothing —
> `view-toggle` actually uses `sbb-checkbox-group`. Dead code worth removing,
> or worth adopting deliberately (see the Widget Gallery proposal).

### 2b. Tokens — 1255 references, but only 35 distinct

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

## 3. `off-brand-theme.css` is not the answer

The package ships a file with a promising name. It is not what it sounds like:
diffed against `standard-theme.css` it differs in **exactly four lines** —
`--sbb-color-primary{,85,125,150}` switch from red to royal blue. Same SBB
typeface, same SBB CDN, same token names. It exists for SBB subsidiaries, not
for de-branding.

## 4. Options

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
- **16 thin component wrappers**, of which `expansion-panel` is 55 % — so
  realistically *one* wrapper that matters, plus buttons
- **font decoupling** — done, see §5

After B, Lyne is one theme adapter among several: internal builds load the Lyne
adapter, open-source builds a neutral one. Same components, same code, a build
flag.

## 5. Decision, 2026-08-23

**A is implemented. B is the agreed direction. C is rejected. D stays open and
becomes cheap only once B exists.**

### What was implemented

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

### Why Inter (since 2026-09-03; IBM Plex Sans before that)

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

### Verification

A full page load produces **zero requests to external hosts**; the only font
requests are the two self-hosted files:

```
GET /media/inter-latin-wght-normal.woff2  → 200
GET /media/inter-latin-wght-italic.woff2  → 200
```

```bash
npx ng build && grep -c "cdn.app.sbb.ch" dist/frontend/browser/*.css   # → 0
```

## 6. Swapping the font

Three steps, no other file involved:

```bash
npm i @fontsource-variable/source-sans-3
```

then in `frontend/src/styles.scss` change the two `@import` lines and the value
of `--sbb-typo-font-family`.

## 7. Open items

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
- **Remove the dead `sbb-tag` rules** in `toolbar.component.scss` and
  `view-toggle.component.scss`, or adopt `sbb-tag` deliberately.
