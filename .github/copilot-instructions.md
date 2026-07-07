# GitHub Copilot / VS Code instructions

This project has shared conventions that apply to every AI assistant. Before
suggesting frontend code, follow:

- **[`docs/reference/frontend-lyne-conventions.md`](../docs/reference/frontend-lyne-conventions.md)**
  — SBB Lyne + frontend rules.

Key rules:

- **No hardcoded colours.** Never emit raw hex / `rgb()` / `rgba()` in SCSS or
  templates — use Lyne semantic tokens (`--sbb-color-*`), the app tokens in
  `frontend/src/styles.scss` (`--app-*`, `--layer-color-*`), or `light-dark(a, b)`.
- This is **Angular (standalone + signals) + Lyne web components
  (`@sbb-esta/lyne-elements`) + component SCSS** — **not** React / `lyne-react` /
  CSS Modules / Tailwind. Ignore React-specific Lyne advice.
- Register new Lyne elements via side-effect import in `frontend/src/main.ts` and
  add `CUSTOM_ELEMENTS_SCHEMA` to the standalone component that uses them.

The colour rule is enforced by stylelint: `cd frontend && npm run lint:styles`.

See the conventions doc for the full list. Project overview lives in
[`CLAUDE.md`](../CLAUDE.md) and [`AGENTS.md`](../AGENTS.md).
