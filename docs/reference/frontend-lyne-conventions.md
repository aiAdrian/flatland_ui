# Frontend & SBB Lyne Conventions

**Authoritative rules for all frontend work in this repo — for humans and any AI
assistant (Claude Code / Claude Desktop, VS Code Copilot, Cursor, other LLMs).**
If a rule here conflicts with a habit from another project, this file wins.

> This is the Angular adaptation of the SBB Lyne conventions. Our stack is
> **Angular (standalone + signals) + Lyne _web components_ (`@sbb-esta/lyne-elements`)
> + component SCSS** — **not** React / `lyne-react` / CSS Modules / Tailwind. Ignore
> React-specific advice from upstream Lyne skills.

## Tech stack (what actually applies here)

- **Framework**: Angular, standalone components + signals. No NgModules.
- **Components**: Lyne **web components** from `@sbb-esta/lyne-elements`, used as
  custom elements in templates (`<sbb-button>`, `<sbb-expansion-panel>`, …).
- **Styling**: per-component `.scss` + global `src/styles.scss`. Lyne theme is
  `standard-theme.css`.
- **Backend**: FastAPI + Flatland (out of scope for this file).

## 1. No hardcoded colours (hard rule)

Never write raw hex / `rgb()` / `rgba()` in component SCSS or templates. Use:

- **Lyne semantic tokens** — `var(--sbb-color-charcoal)` (text),
  `var(--sbb-color-granite)` (secondary text), `var(--sbb-color-milk)` (bg),
  `var(--sbb-color-cloud)` (borders), etc.
- **App tokens** defined in `src/styles.scss` — `--app-*`, `--color-*`,
  `--layer-color-*`.
- **`light-dark(a, b)`** for anything that must adapt per theme.

Use **bare `var(--token)`** without a hex fallback in new code — the Lyne theme is
always loaded, and a hex fallback (`var(--x, #212121)`) both reintroduces a literal
colour and trips the lint gate (below). New colour needed → **add a token to
`styles.scss`, don't inline it.** Agent colours live in `AgentColorService` /
`agent-color.types.ts`, never in SCSS.

**Why:** ~1085 hardcoded hex + ~170 rgba already exist — that legacy debt is what
blocks a future dark mode (Lyne `.sbb-dark` / `color-scheme`). Keeping colours
tokenised makes dark mode a config flip instead of a repo-wide rewrite. Don't add
to the debt; migrate a file's inline colours when you touch it.

**Enforced by lint.** `npm run lint:styles` (config: `frontend/.stylelintrc.cjs`)
fails on any new hex or named colour. The ~31 pre-existing offender files are
grandfathered in a `LEGACY_DEBT` allowlist in that config — when you tokenise a
file, remove it from the list so the gate starts guarding it. `src/styles.scss` is
the permanent token layer where literal colours are correct. Note: `rgb()/rgba()`
literals are covered by the written rule but not auto-linted yet (no core rule
without high friction on shadows) — still don't add them.

## 2. Prefer tokens for spacing & typography too (recommended)

- **Spacing**: prefer `var(--sbb-spacing-fixed-1x, 4px)` (4px), `-2x` (8px),
  `-3x` (12px), `-4x` (16px) over raw pixel gaps/padding where practical.
- **Typography**: don't reinvent type styles in CSS. Use the Lyne component that
  carries the right typography (e.g. `sbb-title`) rather than hand-styling
  `font-size`/`font-weight`.

## 3. Registering Lyne components (Angular pattern)

Lyne components are web components, so:

- **Register once** via side-effect import in [`src/main.ts`](../../frontend/src/main.ts):
  `import '@sbb-esta/lyne-elements/button.js';`. Sub-components live on sub-paths
  (e.g. `.../button/secondary-button.js`). Add the import there when you use a new
  Lyne element — don't import Lyne into individual components.
- **Add `CUSTOM_ELEMENTS_SCHEMA`** to any standalone component that uses `sbb-*`
  tags in its template (this repo already does this in ~28 components).
- Reach for an existing Lyne component before hand-rolling HTML/CSS for the same
  thing (buttons, dividers, menus, expansion panels, checkboxes, form fields).

## 4. Component usage conventions

- **Buttons**: use the plain element (`sbb-button`, `sbb-secondary-button`,
  `sbb-transparent-button`, `sbb-mini-button`) for click handlers. For real
  navigation (an `href`), use the corresponding **`*-link`** variant so it renders
  a real `<a>`. Pick the visual weight by role: primary action = `sbb-button`,
  secondary = `sbb-secondary-button`, low-emphasis = `sbb-transparent-button`.
- **`sbb-title`** (when you add headings): use `level` for the semantic heading
  (h1–h6) and `visual-level` for the size — they can differ, e.g.
  `<sbb-title level="3" visual-level="5">` is an `h3` that looks like a 20px bold
  heading. Don't fake headings with styled `<div>`s.
- **`sbb-card`** (when you add cards): set `color="milk"` for standard content
  cards. Make the whole card clickable with a `sbb-card-link slot="action"` placed
  **before** the visible content; put `href` on the link, not the card.
- **`sbb-status`** (when you add status pills): use the `type` prop
  (`info` / `success` / `warning` / `error` / `pending` / …) instead of colouring
  a badge by hand.

## What we deliberately left out

- **Accessibility** rules from the upstream skill are intentionally not enforced
  here for now (project decision). Semantic HTML via Lyne components still helps,
  but there's no WCAG gate.
- React / Next.js / `lyne-react` / CSS Modules / Tailwind / `.figma.jsx` — not our
  stack; ignore those parts of any shared Lyne skill.

## Related

- Global tokens & theme setup: [`frontend/src/styles.scss`](../../frontend/src/styles.scss)
- Project guardrails: [`CLAUDE.md`](../../CLAUDE.md)
- Lyne components: https://digital.sbb.ch/en/design-system/lyne/components/
