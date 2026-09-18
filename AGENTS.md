# AGENTS.md

Cross-tool entry point for AI coding assistants (Codex, Cursor, VS Code agent
mode, and any other LLM-based tool). Claude Code / Claude Desktop read
[`CLAUDE.md`](./CLAUDE.md), which carries the full project context.

## Read these before frontend work

- **[`docs/reference/frontend-lyne-conventions.md`](docs/reference/frontend-lyne-conventions.md)**
  — authoritative frontend & SBB Lyne rules. **Most important: no hardcoded
  colours** (use Lyne / app design tokens or `light-dark()`), and this is an
  **Angular + Lyne web-components + SCSS** project (not React / lyne-react /
  Tailwind — ignore React-specific Lyne advice). The colour rule is enforced:
  `cd frontend && npm run lint:styles`. **Second: no inline user-facing text** —
  English source, German and French translations via keys in
  `frontend/public/i18n/` (§5 of the conventions doc).
- **[`CLAUDE.md`](CLAUDE.md)** — project overview, interaction modes, and guardrails.
- **[`docs/reference/`](docs/reference/)** — architecture and deeper specs.

Keep these files in sync: the conventions doc is the single source of truth; this
file and `CLAUDE.md` only point to it.
