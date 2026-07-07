# UX design topics — deferred backlog

A running collection of UX/UI topics we've identified but **aren't implementing
yet**. Each entry records the problem, the target look, a concrete change list
(with file/line anchors where useful), and what must not be touched — so a future
session can pick it up without re-deriving the context.

Add new topics as `## Topic N — <title>`. Mark an entry `(done)` in the heading
and move it below the open ones when implemented.

---

## Topic 1 — Align Layout Designer to Tile Gallery (visual)

**Status:** deferred · **Surface:** Layout Designer body (`/designer`)

**Problem.** The Designer and the Tile Gallery share the config-shell header but
their **bodies look visually different**. The Gallery is the preferred/reference
look; the Designer should adopt its visual language — same page background,
typography scale, border-radius scale, card / control / section-header
vocabulary, and token usage — without restructuring the editor
(palette | canvas | settings) or breaking its sizing/resize logic.

**Reference (the "better" look) — `frontend/src/app/features/tiles-gallery/`:**
- `:host` bg `--sbb-color-milk`; `.gallery` centered `max-width: 1180px`.
- Cards (`.tile-card`): white bg, `1px solid --sbb-color-cloud`, `border-radius: 8px`,
  `border-top: 3px solid var(--kind-color)`.
- Controls: `.control-label` (11px uppercase `--sbb-color-graphite`), `.segmented`
  (cloud border, radius 6, active = charcoal bg / white text), inputs cloud-bordered
  radius 6.
- Section headers (`.kind-section__head`): `border-left: 4px solid var(--kind-color)`
  + badge + italic subtitle + blurb.
- Pills/chips: `999px` radius, token colors.

**Designer gap (current) — `layout-designer.component.scss`:** the base block
(lines 1–345) uses raw hex (`#f3f3f3 #fafafa #d2d2d2 #c8c8c8 #686868 #fff …`);
`border-radius` 4–5px; `.palette__item` bg `#fafafa`; `.panel-card` border `#c8c8c8`;
`.preview__head` plain flex; meta labels are dense bordered 10px cards; status pills
use bespoke hex (`#2e7d32 #16692b #fff8e1 #6b4a00 …`). A `--designer-*` alias layer
already exists (lines 764–777) and the `DESIGNER_LYNE_TOOLBAR_STYLE` block
(763–1155) already tokenizes toolbar/buttons/meta — that is the migration hook.

### Change list (surface only — color / border / radius / typography / padding)

1. **Retune `--designer-*` aliases** (764–777) to Gallery tokens; add
   `--designer-graphite: var(--sbb-color-graphite)`. Replace `--designer-red-dark`
   and `--designer-*-soft` with `--app-severity-*` / `--app-positive` /
   `--color-muted`.
2. **Migrate base-block hex → tokens:** `:host` bg (1–6), base
   `button`/`input`/`select`/`label` (8–44), `.palette`/`.palette__item`/`__item span`
   (105–140), `.preview__head` (201–210), `.panel-card`/`__head`/`__body` (281–318),
   `.canvas__empty` (261–269 — cosmetic only), `.canvas__column-head` (245–253).
3. **Align radius scale:** buttons/inputs → 6px, cards → 8px, pills → 999px.
4. **Align cards to the tile-card look:** `.palette__item` and `.panel-card` →
   white bg, cloud border, radius 8, accent top-border (palette: `--app-kind-*`;
   panel: neutral `--sbb-color-graphite` or a panel-type accent).
5. **Align section headers:** `.preview__head` and the palette `<h2>` → left 4px
   color bar (graphite) + heading, Gallery-style.
6. **Align meta controls** to flat Gallery `.control-label`s + cloud-bordered
   inputs (replace the dense bordered label-cards), keeping
   `grid-template-columns` untouched.
7. **Status pills** (`.designer-unsaved-pill`, `.live-preview-pill`,
   `.designer-action-btn--dirty/--saved`, `.designer-footer-status`) →
   `--app-positive` / `--app-severity-warn` / `--app-severity-error` tokens.

### Do NOT touch (load-bearing sizing / overflow / resize)

- `:host` flex / `100vh` / overflow (348–352, 780–787); `.designer` /
  `.designer__body` grid + height (98–103, 367–372, 1101–1105, 1173–1175).
- The entire `LAYOUT_DESIGNER_SCREEN_SIZE_FIX` block (347–408).
- `.preview__scroll` height / overflow (212–219, 390–396) — its *background* is OK
  to change.
- `.canvas` min-height / transform (221–229, 398–400); `.canvas__column` min-width;
  `.canvas__column-resize` / `.panel-card__resize` / `.panel-card__runtime` sizing.
- All `.canvas__row*` sizing / position / resize rules (1335–1808, incl. the
  unmarked trailing resize iterations) and `.canvas-row-resizing`.
- Meta `grid-template-columns` (every redefinition).

### Out of scope

The running dispatcher header, mode switcher, and config-shell are already
aligned in prior work — leave them.

### Verification (when implemented)

`npx ng build` and `npx stylelint "src/**/*.scss"` both pass; manually open
`/designer` and `/gallery` side by side and confirm the two bodies share page bg,
card, control, and section-header vocabulary. Drag/resize rows, columns, and
panels in the Designer to confirm sizing/resize behavior is unchanged.
