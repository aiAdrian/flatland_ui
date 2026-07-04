# Tile authoring — how we develop a new tile

> Our repeatable process for creating a new HMI tile. Authoring happens **in
> Claude Code as a discourse**, not in a WYSIWYG web tool: the web
> [Layout Designer](../../frontend/src/app/features/layout-designer) *composes*
> existing tiles; here we *author* new ones. Grounded in
> [interaction-framework.md](interaction-framework.md) (the taxonomy) and
> tracked in [tile-catalog.md](../plans/tile-catalog.md) (the backlog).

## Principles

1. **Spec before code.** Every tile starts as a written spec (template below).
   The spec is the discourse: it forces the three axes — *what function*
   (`kind`), *how per mode*, *how it interacts with the system* — and usually
   surfaces a backend gap before a line is written.
2. **Grounded.** Each tile names a reference (a consortium deliverable, a paper,
   a control-room practice). No generic-dashboard tiles.
3. **One mode-aware component, not three.** Behaviour that varies by mode lives
   inside a single component that reads `store.interactionMode()` via a
   `modeBehavior` computed (see `impact-panel.component.ts` as the reference
   pattern). Framing that is already a store-level projection uses
   `store.optionPresentation()`.
4. **Honest backend scoping.** Start with data the backend already exposes; mark
   anything richer (e.g. epistemic/aleatoric uncertainty) as a *flagged backend
   extension*, never faked.
5. **Reuse the AI4REALNET algorithm, don't rebuild it** (CLAUDE.md §Cross-reference).
   When a flagged backend extension has a consortium reference implementation —
   e.g. **A3S** for A1's uncertainty/calibration — integrate it by default.
   Building our own algorithm is the exception; if we do, say so explicitly in
   the spec's Open questions/risks section, not by silently diverging.
6. **Wire into the seams, don't fork them.** A finished tile touches a known set
   of registration points (below) — never a parallel mechanism.
7. **No hardcoded colours** (CLAUDE.md / frontend-lyne-conventions) — Lyne tokens
   or `light-dark()`, agent colours via `AgentColorService`.

## The Tile Spec template

Every tile spec (`docs/plans/tile-<id>-<slug>.md`) has these sections:

1. **Identity** — name · `kind` · `granularity` (overview↔detail) · default zone ·
   source(s) · grounding reference.
2. **Promise** — one sentence: what the operator can now do.
3. **Per-mode behaviour** — Recommendation / Co-Learning / Director: availability
   **and** behaviour. For Decision-Support tiles, state the Assessment↔Recommendation
   framing explicitly.
4. **System interaction** — data *in* (store signals, API endpoints), actions
   *out* (store methods), and a **backend table**: available now vs. to-build.
5. **Allocation & accountability touchpoints** — which loop stage; who owns it per
   mode (`allocation`); what **decision events** it emits (feeds the accountability
   seam / [interaction-logging-plan](../plans/interaction-logging-plan.md)).
6. **Acceptance scenario** — one concrete walkthrough + a **measurable** success
   criterion (ties to a core question / study metric).
7. **Effort & changes** — S/M/L (tokens + days), and the list of files/registration
   points to touch.
8. **Open questions / risks** — especially the study-relevant unknowns.

## Build workflow (once a spec is agreed)

1. **Scaffold** a standalone component under `features/<slug>/` (signals +
   `CUSTOM_ELEMENTS_SCHEMA` if Lyne elements are used).
2. **Mode-aware logic** via a `modeBehavior` computed; framing via
   `optionPresentation()` where applicable.
3. **Register** at the known seams:
   - `panel-plugin-host.component.ts` (+ `.html` `@switch`) — type → component
   - `layout-designer.component.ts` `palette` — make it draggable
   - `core/layout/panel-mode-availability.ts` `PANEL_MODE_AVAILABILITY` — mode gating
   - `PanelDefinition` — set `kind` + `granularity` (once those fields land)
   - hardcoded default layout in `app.component.html`/`.ts` only if it ships by default
4. **Backend** (only if the spec's table needs it): add the endpoint/field; keep
   `backend/tests/` green and add coverage for new gating.
5. **Verify**: `ng build` clean; drive it in the preview per mode; check the
   acceptance scenario.
6. **Document**: update [panel-mode-matrix.md](panel-mode-matrix.md) with the new
   row, and flip the tile's status in [tile-catalog.md](../plans/tile-catalog.md).

## Definition of done

- Spec sections 1–8 answered; acceptance scenario demonstrably passes.
- Behaviour differs across the three modes exactly as the spec states.
- Registered at all applicable seams; `panel-mode-matrix` row added.
- `ng build` clean; no hardcoded colours; backend tests green.
- Any deferred capability is written down as a flagged extension, not silently
  dropped.
