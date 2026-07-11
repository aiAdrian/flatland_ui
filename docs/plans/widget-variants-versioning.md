# Widget variants & versioning

> Dated plan, 2026-07-11. Today there is **one implementation per widget type**.
> We want multiple **variants** of the same widget "role" that can be swapped,
> and to keep older versions (e.g. the pre-rebuild Recommendations panel)
> **selectable**, not just in git history.

## Current seam (what exists)

- A panel is `panel.type` (a string). `panel-plugin-host`'s `@switch (panel.type)`
  maps each `type` → exactly one component
  (`frontend/src/app/features/layout/components/panel-plugin-host/panel-plugin-host.component.html`).
- The **Widget Catalog** (`frontend/src/app/core/widgets/widget-catalog.ts`,
  `WidgetMeta`) lists each `type` with `kind` (taxonomy), modes, zone, etc.
- Per-mode availability: `frontend/src/app/core/layout/panel-mode-availability.ts`
  (keyed by `type`). Persisted layouts reference `type`.

So `type` today conflates **"which role"** and **"which implementation"**.

## Model (additive, no schema break)

Keep `type` as the **implementation key** — one variant = one `type` + one
component in the `@switch`. Add a light **grouping** so variants of the same role
are discoverable and swappable:

- `WidgetMeta.role?: string` — the shared role id (e.g. `'recommendations'`).
  Widgets with the same `role` are variants of one another.
- `WidgetMeta.variantLabel?: string` — human label (e.g. `'v1 · simple card'`,
  `'v2 · scored strategy cards'`).
- (optional) `WidgetMeta.variantDefault?: boolean` — the variant offered by
  default for that role.

The Widget Gallery/palette groups by `role`; the runtime `@switch` is unchanged
(still per `type`). Persisted layouts keep working (they store a concrete `type`).

**Variants ≠ history.** Variants are parallel alternatives a user can pick.
Git is history. Because we want v1 *selectable*, it becomes a variant.

## Step 1 (now): keep v1 of Recommendations as a variant — DONE (2026-07-11)

Implemented & verified: `features/recommendations-classic/` (type
`recommendations-classic`, role `recommendations`, `v1 · simple card`), registered
in the `@switch`, the catalog (both variants tagged with `role`/`variantLabel`),
`panel-mode-availability`, and the layout-designer palette. Both variants render
side-by-side in the Widget Gallery; `ng build` + `lint:styles` green; no console
errors. Details below.


- Recover the pre-rebuild component (from git `HEAD`, since the flagship rebuild
  is uncommitted) as `features/recommendations-classic/` →
  `type: 'recommendations-classic'`, `role: 'recommendations'`,
  `variantLabel: 'v1 · simple card'`. Colours tokenised so it passes the lint
  gate (design unchanged).
- New scored-cards panel keeps `type: 'recommendations'`, gains
  `role: 'recommendations'`, `variantLabel: 'v2 · scored strategy cards'`,
  `variantDefault: true`.
- Register the classic `@case`, catalog entry, and `panel-mode-availability`
  (same modes: `['recommendation']`). Both appear in the gallery; additive.

## Step 2 (later, separate): the variant switcher

- A UI to swap the variant **in a live layout slot** (same role, different
  implementation) without removing/re-adding a panel. Touches the palette /
  panel header and possibly `PanelInstance` (store which variant).
- Optional: a `variantOf`/`role` filter in the palette so variants group visually.

## Do-not / risks

- Don't turn `kind` into the variant axis — `kind` is the taxonomy
  (event/context/…); `role` is "same functional slot, different implementation".
- Keep the `@switch` the single runtime mapping; don't add a parallel registry
  that can drift from it.
- Avoid duplicating large chunks of logic across variants — share via
  `shared/ui/` primitives (as v2 already does).
- Persisted-layout compatibility: never rename an existing shipped `type`.

## Verification (Step 1)

- Gallery shows both Recommendations variants (v1 classic, v2 scored).
- Adding the `recommendations-classic` panel renders the old simple-card design.
- v2 still renders the scored cards. `ng build` + `lint:styles` green.
