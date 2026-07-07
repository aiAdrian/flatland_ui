# Colour-usage audit — semantic families, consistency, collisions

> Analysis only (no code changes). Inventory of every colour concept in the
> frontend today, grouped by *what it encodes* — the input needed before any
> "pick a colour scheme before the session starts" config UI or visual-encoding
> registry gets built. Companion of
> [frontend-lyne-conventions.md](frontend-lyne-conventions.md) (the bare-token
> rule) and the planned
> [visual-encoding registry](../../frontend/…) (memory `visual-encoding-registry`).
>
> **Every claim below is grounded in a grep/read of `frontend/src/` on
> 2026-07-04.** Counts are occurrences, not distinct tokens.

## 1. Inventory

### 1a. Lyne semantic tokens in use (`--sbb-color-*`)

11 distinct `--sbb-color-*` tokens are actually referenced in
`frontend/src/**/*.{scss,html,ts}` (frequency):

| Token | Uses | Role |
|---|---:|---|
| `--sbb-color-charcoal` | 136 | primary text / strong fills |
| `--sbb-color-granite` | 119 | secondary / muted text |
| `--sbb-color-cloud` | 118 | borders, dividers, disabled |
| `--sbb-color-milk` | 50 | panel / muted backgrounds |
| `--sbb-color-red` | 46 | errors / malfunctions / severity-high |
| `--sbb-color-white` | 42 | surface / on-colour text |
| `--sbb-color-orange` | 26 | warnings / Director mode / reliability-medium |
| `--sbb-color-blue` | 18 | Recommendation mode / decision-support kind / recommended |
| `--sbb-color-iron` | 12 | tertiary text |
| `--sbb-color-green` | 4 | Co-Learning mode / reliability-high / "recommended scenario" |
| `--sbb-color-violet` | 1 | kind-prediction badge only |

(Verified: `grep -rhoE '--sbb-color-[a-z0-9-]+' src | sort | uniq -c`.)

### 1b. App-level tokens defined in `src/styles.scss` (the TOKEN_LAYER file)

| Token group | Members | Purpose (from the file's own comments) | Consumers (`grep -l`, file count) |
|---|---|---|---|
| `--color-*` (legacy) | `default, focus, muted, focus-edit, related, warning` | "Global UI semantic colours (P2 / concept-alignment). NOT for agents." Defined as raw `rgba()` | **~1 file each** — effectively dead; only `styles.scss` defines them |
| `--layer-color-*` | `next-decisions (#eb0000), switches (#762C8F), signals (#DC8C00), grid (#787878)` | "Layer colours — single source of truth. Used by layer-visibility dots AND map markers, so the legend colour always matches the map." | **2 files** — `layer-visibility`, `flatland-map` (the legend/marker contract holds) |
| `--app-select-*` | `select-color (#f939e9 magenta), -dark, -bg, -ring, -glow` | "Selection / active edit color. Must not be warning orange." | **9 files** — agent-inspector, impact-panel, left-sidebar, recommendations-panel, … (the active-selection accent) |
| `--app-hover-*` | `hover-bg, -border, -border-dark, -ring, -ring-soft, -glow` | "Neutral hover/focus. Red/orange are reserved for semantic states." | **9 files** — broadly the hover/focus accent |
| `--app-reliability-*` | `high (green), medium (orange), low (red), band (cloud), band-wide (red)` | Tile A1 reliability level + uncertainty band (Trust kind) | **2 files** — `risk-uncertainty-panel.component.scss` only (+ `styles.scss` def) |
| `--app-kind-*` | `event, context, prediction, decision-support, control, capitalization, trust` | Tile `kind` badge in the Layout Designer palette (interaction-framework §2) | **1 consumer** — `layout-designer.component.scss` (+ `styles.scss` def) |

### 1c. Agent / train identity palette — `AgentColorService`

`src/app/core/agent-color.types.ts` + `agent-color.service.ts`:

- **6 train types** in a fixed display order (public contract, tests pin it):
  `normal`, `intercity`, `interregio`, `sbahn`, `sbahnWerktag`, `gueterzug`.
- **Round-robin assignment**: `agent.handle % TRAIN_TYPES.length`
  (`agent-color.service.ts:18`). A deployment with N agents gets at most 6
  distinct colour identities; handles beyond 6 wrap modulo.
- **Two parallel palettes per type**: `colors` (tinted, alpha 0.7 — for fills,
  dots, badges) and `colorsSolid` (alpha 1.0 — for lines, strokes, agent paths).
- **4 states each**: `default / focus / muted / related`.
- **~40 distinct hex/rgba values**, all from "the SBB Flatland UX colour spec"
  (per the file's header comment) — *not* Lyne tokens. Examples: intercity
  focus `#762C8F` (Intercity violet), sbahn focus `#3C3F8F` (indigo), normal
  `#6E6E6E` (grey), gueterzug `#1C78B5` (blue).
- **Consumers (6 components)**: `agent-inspector`, `left-sidebar`,
  `marey-chart`, `impact-panel`, `notifications-panel`, `flatland-map`
  (via `getColorSolid` / `getColor`). Agent colours are deliberately kept
  *out of SCSS* (CLAUDE.md guardrail) — they are a runtime service.

### 1d. Remaining hardcoded colours (the legacy debt)

**~1321 raw `#hex` / `rgba()` occurrences** across `*.scss` + `*.html`
(CLAUDE.md's "~1085" has grown). Top files by count:

| File | Count | Apparent purpose (sampled) |
|---|---:|---|
| `layout-designer.component.scss` | 222 | UI chrome: greys `#d2d2d2`/`#fafafa`/`#686868`, selection `#eb0000` (LEGACY_DEBT-listed) |
| `app.component.scss` | 159 | header/footer chrome + **mode dots** (blue/green/orange, see §2e) |
| `flatland-map.component.scss` | 109 | map chrome + an amber `#ffaa00` stroke (line 59), red malfunction `#eb0000` |
| `marey-chart.component.scss` | 101 | almost all structural greys (`#fff`, `#888`, `#212121`, `#d2d2d2`) |
| `left-sidebar.component.scss` | 94 | roster chrome + malfunction red, warning orange (token-based) |
| `scenario-panel.component.scss` | 71 | **`#00973b` green hardcoded for "recommended scenario"** (lines 41, 50, 91) |
| `styles.scss` | 58 | correct — TOKEN_LAYER (token definitions) |
| `impact-panel.component.scss` | 54 | severity chip red, recommended blue (token-based) |
| `notifications-panel.component.scss` | 50 | event-feed kind markers |

All 31 component `.scss` files in this list are grandfathered in
`.stylelintrc.cjs`'s `LEGACY_DEBT` set; new files are guarded by default.

## 2. Semantic families

Grouped by *what the colour encodes*, not by file.

| Family | Encodes | Defined where | Consumed where (consistency) | Global-config candidate? | Risk if reassigned |
|---|---|---|---|---|---|
| **Agent/train identity** | *which train is which* | `AgentColorService` + `agent-color.types.ts` (6 types, round-robin, tinted+solid) | 6 components — **consistent** (single service, one contract, tests pin it) | **Partial** — palette is the SBB Flatland UX spec; a study *could* swap palettes, but identity is the round-robin contract, not a per-tile choice | **High** — per-tile override breaks the identity mapping (agent 0 = normal everywhere). Must stay a single global service |
| **Authorship** (human vs AI) | *who produced this step/branch* — planned: human blue solid / AI amber dashed | **Not yet in code.** Memory `visual-encoding-registry` defines v1: human `#0079c7` solid 👤, AI `#ffaa00` dashed 🤖 | No consumer yet (the what-if tile B1 / `recommender-roadmap` will be first). No informal authorship colouring found in the codebase today | **Yes** — it is the v1 registry role, designed to be configured-once-before-session | Hue overload (see §3): blue & amber each already mean 3 other things → registry must carry line-style + icon + label, not hue alone |
| **Trust / reliability / uncertainty** | *how much to rely on this AI output* | `--app-reliability-*` in `styles.scss` (green/orange/red/cloud) | **1 consumer** (`risk-uncertainty-panel`) — consistent by default (only one tile) | **Yes** — a study-calibrated reliability palette is a natural global knob | Collides with severity (red/orange/green) and mode (green/orange); must move in lockstep with those families, not independently |
| **Severity / status** | *how bad / alert vs warn vs ok* | Scatter: global `.malfunction-indicator` (`styles.scss`, `#eb0000`), `--sbb-color-red/orange` in impact/left-sidebar/notifications, hardcoded `#eb0000` in several | **Inconsistent** — mix of tokens and raw `#eb0000`; severity-high uses `--sbb-color-red` (impact-panel:97) but malfunction indicator hardcodes the same red | **Partial** — semantics are universal, but currently scattered raw; needs a `--app-severity-*` family first | Reassigning per-tile would fragment the alert language; should be one global severity ramp |
| **Mode identity** | *which interaction mode is active* | `app.component.scss:98-100,447,945-947` — recommendation=blue `#0079c7`, co-learning=green `#00973b`, director=orange `#ffaa00` (header `mode-dot`, footer, `mode-locked`) | **Consistent** within `app.component.scss` (one file, three selectors) | **No** — mode identity is the mode-switch UI itself, not a per-study variable; making it configurable would sever the visual link to the mode taxonomy | Low if left fixed; **high collision risk** if made configurable (blue/amber overload, §3) |
| **Layer identity** | *which map layer a glyph belongs to* | `--layer-color-*` in `styles.scss` (red/violet/orange/grey) | **2 consumers** (`layer-visibility` dots + `flatland-map` markers) — **consistent** by design (single source → legend matches map) | **Partial** — a study could pick a layer palette, but the legend/marker contract must stay a single token | Reassigning per-tile breaks the legend-matches-map invariant; must stay one shared token |
| **Tile-kind tag** (designer only) | *which interaction-framework function class a panel is* | `--app-kind-*` in `styles.scss` (7 colours) | **1 consumer** (`layout-designer` palette badge) | **No** — taxonomy colour is arbitrary, not study-variable; designer-only | Low; palette badge only, no runtime meaning |
| **Structural / Lyne base** | UI chrome — borders, backgrounds, text | `--sbb-color-charcoal/granite/cloud/milk/white/iron` (136/119/118/50/42/12 uses) | Mostly token-based in new files; legacy files hardcode the same greys (`#d2d2d2`, `#686868`, `#212121`) | **No** — Lyne theme territory; a future dark mode flips these via Lyne, not a per-session config | None — leave to Lyne tokens; opportunistic migration only |

## 3. Divergence & collision call-outs (the owner's concern)

These are the cases where a concept is coloured locally/ad-hoc instead of by a
shared token, or where two families share a hue — the traps for a future global
config.

1. **`scenario-panel.component.scss` defines its own "recommended" green.**
   Lines 41, 50, 91 hardcode `#00973b` / `rgba(0,151,59,0.12)` for the
   "recommended scenario" badge — the *same* green that is
   `--app-reliability-high`, `--app-kind-capitalization`, and the Co-Learning
   mode dot. If reliability or mode ever becomes configurable, this tile will
   silently keep its local green and diverge. Should be a shared
   "recommended/positive" token.

2. **`flatland-map.component.scss` hardcodes an amber stroke `#ffaa00` (line 59).**
   That amber is also Director mode, `--app-reliability-medium`,
   `--app-kind-trust`, and the planned AI-authorship colour. Five families on
   one hue. Needs a named purpose, not a raw hex.

3. **Blue (`#0079c7` / `--sbb-color-blue`) is overloaded across families.**
   It carries: Recommendation-mode identity (`app.component.scss:98`),
   tile-kind `decision-support` (`--app-kind-decision-support`), the
   "recommended option" border (`impact-panel.component.scss:210`), the planned
   human-authorship colour, and is visually adjacent to the S-Bahn agent focus
   colour `#3C3F8F` (`agent-color.types.ts`, sbahn `colorsSolid.focus`). Making
   *any* of these independently configurable will collide with the others.

4. **Amber/orange (`#ffaa00` / `--sbb-color-orange`) is overloaded across families.**
   Director-mode identity, `--app-reliability-medium`, `--app-kind-trust`,
   the planned AI-authorship colour, and warning/severity events
   (`left-sidebar` orange border). Same problem as blue.

5. **Severity is not a token family.** Red `#eb0000` appears as
   `--sbb-color-red` (impact-panel, left-sidebar), as the global
   `.malfunction-indicator` raw hex (`styles.scss:73`), and as raw `#eb0000` in
   `layout-designer` selection outlines and `flatland-map`. Same colour, three
   definitions. A `--app-severity-*` ramp would unify it.

6. **`--color-*` (P2 concept-alignment) is dead debt.** Six tokens defined in
   `styles.scss:41-46`, each consumed by ~1 file. They duplicate Lyne
   (`--color-warning` ≈ `--sbb-color-orange`; `--color-default` ≈ granite).
   Candidate for removal, not for becoming a config family.

7. **No informal authorship colouring exists today** (good). The what-if tile
   (B1) will be the first consumer; it should pull from the planned registry,
   not hardcode blue/amber — this is exactly the precedent
   `risk-uncertainty-panel.component.scss` already set (it tokens its
   reliability levels rather than hardcoding, caught/enforced by the stylelint
   gate).

## 4. Open questions for the owner

1. **Blue/amber collision — which family yields?** Recommendation-mode blue,
   human-authorship blue, decision-support-kind blue, and the S-Bahn agent are
   four claims on one hue. The registry plan already says authorship must use
   *line-style + icon + label* (not hue) for exactly this reason — confirm that
   authorship stays hue-free, or decide which other family re-hues.
2. **Is "recommended/positive" a family?** scenario-panel's local green,
   impact-panel's recommended-blue, and `--app-reliability-high` green all mean
   "the thing to favour" but use three colours. Should there be one
   "positive/recommended" token, or is the mode (recommended vs neutral)
   supposed to drive the colour?
3. **Severity as a first-class family?** It is the most scattered
   (token + raw hex + global indicator). Want a `--app-severity-{info,warn,error,critical}`
   ramp that malfunction, impact severity, and notifications all adopt?
4. **Agent identity — swappable per study, or fixed?** The 6-type palette is
   the SBB Flatland UX spec. Is a study allowed to remap train-type → colour
   (e.g. colour-blind-safe palette), or is identity fixed and only
   *authorship/severity* configurable?
5. **Mode identity — configurable or sacred?** Today blue/green/orange is
   fixed in `app.component.scss`. The registry reserves a `mode` role but
   leaves it a placeholder. Should mode colour ever be study-configurable, or
   always derived from the mode taxonomy?
6. **Layer identity scope.** `--layer-color-*` is the only family today with a
   working "legend matches marker" invariant. Is the future registry allowed to
   re-colour layers, or only authorship/severity (with layers fixed)?

## 5. What this implies for the next step (no work done here)

The registry's v1 scope (authorship only) is well-chosen: it is the only family
that is *not yet* coloured anywhere, so introducing it cannot collide. The
families that *are* already coloured (severity, recommended/positive) should be
tokenised into shared `--app-*` families *before* they become registry roles —
otherwise the registry would formalise today's divergence instead of resolving
it. This audit is the input to that decision; building the registry UI is the
follow-up task.
