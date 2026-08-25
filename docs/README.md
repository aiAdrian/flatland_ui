# Documentation index

**This file is the single index of all docs.** Every markdown file under `docs/`
is listed here; if you add one, add its line here too. `reference/OVERVIEW.md`
is the narrative entry point (what the app is, how to try it, roadmap) and links
back here for the full list.

Docs are grouped by purpose. Start with **reference/** for the living truth.

## Product

- [product-vision.md](product-vision.md) — mirror of the [wiki Product Vision](https://github.com/aiAdrian/flatland_ui/wiki/Product-Vision) (authoritative there), plus a detailed MVP proposal and an inventory of what exists today

## reference/ — living reference
The authoritative specs and guides for how the app works today.

- [interaction-modes-brief.md](reference/interaction-modes-brief.md) — **authoritative** mode spec (WP 3.1/3.3/3.4), incl. adjustable autonomy and the three control altitudes
- [OVERVIEW.md](reference/OVERVIEW.md) — narrative overview: what this is, how to try it, what's built, roadmap
- [architecture.md](reference/architecture.md) — system architecture: frontend/backend layers, the two pluggable seams, what is deliberately absent
- [director-mode.md](reference/director-mode.md) — the Director planner in depth: data structures, search strategies, re-planning, invariants
- [interaction-framework.md](reference/interaction-framework.md) — widget taxonomy (kind × granularity), function allocation, Human-in-Control, accountability seam
- [interaction-mode-axes.md](reference/interaction-mode-axes.md) — **discussion paper:** `InteractionMode` conflates autonomy level with collaboration goal; two axes, the cells the current model cannot express, and what would change the argument
- [widget-authoring-process.md](reference/widget-authoring-process.md) — how we develop a widget (spec template + build workflow)
- [mode-guide.md](reference/mode-guide.md) — the same task walked through all three modes
- [panel-mode-matrix.md](reference/panel-mode-matrix.md) — per-panel availability & behaviour per mode (documents `panel-mode-availability.ts`)
- [visual-concept.md](reference/visual-concept.md) — canonical names for surfaces & the three zones
- [frontend-lyne-conventions.md](reference/frontend-lyne-conventions.md) — Angular/Lyne rules, incl. the no-hardcoded-colours gate
- [colour-usage-audit.md](reference/colour-usage-audit.md) — colour concepts grouped into semantic families; consistency, collisions, global-config readiness
- [design-system-independence.md](reference/design-system-independence.md) — how deeply Lyne is coupled (measured), what blocks an open-source release, and the 2026-08-23 decision (font decoupled, adapter layer next)
- [data-provenance.md](reference/data-provenance.md) — real simulation vs mock vs derived per widget/endpoint; why **Demo ≠ Mock**
- [component-shell-plugin-api.md](reference/component-shell-plugin-api.md) — panel shell / plugin API
- [wp4-validation-alignment.md](reference/wp4-validation-alignment.md) — **don't forget:** WP4's Validation Campaign Hub (FAB) + Railway KPI catalog — re-check at real WP 4.3 requirements
- [ui-exploration-synthesis.md](reference/ui-exploration-synthesis.md) — cross-model widget ideas (convergence), grounding for the widget catalog
- [ux-design-topics.md](reference/ux-design-topics.md) — deferred UX/UI backlog (open topics with change lists; not yet implemented)

## plans/ — planned work
Designs and roadmaps not yet (fully) built. Each carries its own status line.

**Study, data & process**
- [interaction-logging-plan.md](plans/interaction-logging-plan.md) — study data capture: one self-describing record per session (header + decisions + context + survey), so modes/designs can be compared
- [flatland-43-upgrade.md](plans/flatland-43-upgrade.md) — measured 4.2.6 → 4.3.0 trial: 5 real failures, a 5-line shim, and the seed-stability blocker
- [docs-maintenance-2026-08.md](plans/docs-maintenance-2026-08.md) — audit 2026-08-19: plan currency, doc overlaps, and where AI4REALNET stands on logging
- [scenario-variants.md](plans/scenario-variants.md) — controlled study vs. dynamic "simulated wild"; variant axes
- [scripted-events-plan.md](plans/scripted-events-plan.md) — deterministic scenario events for User Study 2
- [recommendation-reliability.md](plans/recommendation-reliability.md) — guaranteeing a decision moment (variants A–D)
- [ecml2026-flatland-env.md](plans/ecml2026-flatland-env.md) — reuse the ECML 2026 challenge topology & scenarios (to be discussed)

**Modes, agents & interaction**
- [agentic-delegation.md](plans/agentic-delegation.md) — handing the Director planner a bounded assignment (scope + constraints + report + release) instead of configuring it up front
- [co-learning-direction.md](plans/co-learning-direction.md) — Level A (task) vs Level B (AI learns to work with the human)
- [colearning-across-modes.md](plans/colearning-across-modes.md) — Co-Learning as a cross-cutting layer over the 3 automation levels
- [workstream-b-rationale-capture.md](plans/workstream-b-rationale-capture.md) — override "why?" + preference hypothesis + Learning Store (Tier 1 done)
- [localized-blocking-decisions.md](plans/localized-blocking-decisions.md) — hold the affected trains/area, not the whole sim, until the human decides
- [recommender-roadmap.md](plans/recommender-roadmap.md) — policy vs intervention seams, phases
- [flatland-ecosystem-reuse-plan.md](plans/flatland-ecosystem-reuse-plan.md) — survey of the AI4REALNET + flatland-association repos: what we reuse, what we leave

**Widgets**
- [widget-catalog.md](plans/widget-catalog.md) — candidate widgets A1–D2: sources, effort, contribution to the core questions (the *pipeline*; `core/widgets/widget-catalog.ts` is the *registry*)
- [widget-a1-risk-uncertainty.md](plans/widget-a1-risk-uncertainty.md) — spec: Risk & Uncertainty (first cut built)
- [widget-a2-decision-log.md](plans/widget-a2-decision-log.md) — spec: Decision Log & Accountability Strip (first cut built)
- [widget-b1-whatif-compare.md](plans/widget-b1-whatif-compare.md) — spec: What-if Compare, "my solution vs. AI" (first cut built)
- [widget-b3-network-correlation-graph.md](plans/widget-b3-network-correlation-graph.md) — spec: network correlation graph (planned)
- [widget-linkmap-zwl.md](plans/widget-linkmap-zwl.md) — spec: Link Map / ZWL port from the sibling HMI (planned)
- [widget-timetable.md](plans/widget-timetable.md) — spec: Timetable / Fahrplan (shipped)
- [widget-variants-versioning.md](plans/widget-variants-versioning.md) — multiple selectable variants per widget role; keeping v1 alongside v2

**Layout & app shell**
- [mode-scoped-layouts-plan.md](plans/mode-scoped-layouts-plan.md) — *which* layout renders per interaction mode (availability landed, resolver open)
- [layout-grid-model-plan.md](plans/layout-grid-model-plan.md) — *what a layout can say*: grid areas instead of pixel columns
- [center-view-tabs.md](plans/center-view-tabs.md) — one tabbed centre surface instead of stacked panels
- [i18n-strategy.md](plans/i18n-strategy.md) — runtime language support (EN base, DE next) via Transloco

**Simulation & domain**
- [cities-stations-plan.md](plans/cities-stations-plan.md) — surfacing Flatland's cities as named stations (partly superseded — see its status line)
- [heterogeneous-tracks.md](plans/heterogeneous-tracks.md) — track classes/costs so reroute becomes a real trade-off

## reading/ — dated research notes
External research, read once and recorded so it need not be repeated.

- [2026-08-23-co-study4grid-uebernahme.md](reading/2026-08-23-co-study4grid-uebernahme.md) — full read of RTE's Co-Study4Grid: which interaction patterns and CI gates we could adopt for Co-Learning and this HMI, ranked (DE)
- [2026-08-24-dispatcher-review-study2.md](reading/2026-08-24-dispatcher-review-study2.md) — Disponenten-Review des Co-Learning-Aufbaus für User Study 2; enthält die offene VMax-Frage (DE)
- [2026-08-22-hmi-review-workshop.md](reading/2026-08-22-hmi-review-workshop.md) — HMI review of the Recommendation & Co-Learning screens: feedback, what was fixed, what stays open (DE)
- [2026-08-16-flatland-oekosystem-recherche.md](reading/2026-08-16-flatland-oekosystem-recherche.md) — full read of the AI4REALNET + flatland-association ecosystem (DE)
- [2026-07-16-co-learning-reflection-reading.md](reading/2026-07-16-co-learning-reflection-reading.md) — literature behind the reflection module

## scenarios/ — study & scenarios
Experiment design and scenario material.

- [experiment-storyboard.md](scenarios/experiment-storyboard.md) — study storyboard, 3 conditions, scenario-difficulty matching
- [railway-scenarios.md](scenarios/railway-scenarios.md) — AI4REALNET D1.1/D4.1 scenarios + malfunction taxonomies
- [guided-demo-scenario.md](scenarios/guided-demo-scenario.md) — the guided demo walkthrough
- [widget-01-conflict-aware-marey.md](scenarios/widget-01-conflict-aware-marey.md) — conflict-aware Marey scenario sheet

## infrastructure_builder/
- [requirements.md](infrastructure_builder/requirements.md) — requirements for the in-app infrastructure builder

## delegation/ — delegation records
Dated records of tasks handed to other agents/models, with the brief and the review outcome. Kept for reflection.

- [2026-07-11-mvp-rationale-capture-glm.md](delegation/2026-07-11-mvp-rationale-capture-glm.md) — Workstream B Tier 1 built by GLM 5.2; reviewed + live-verified
- [2026-07-11-gallery-fixture-previews-glm.md](delegation/2026-07-11-gallery-fixture-previews-glm.md) — fixture-backed live previews in the Widget Gallery

## archive/ — one-off artefacts
Prompts, superseded analyses and finished discussion material. Kept for provenance; **not maintained**.

- [event-based-architecture-analysis.md](archive/event-based-architecture-analysis.md) — relationship to InteractiveAI / event-based architecture
- [variant-visualisation.md](archive/variant-visualisation.md) — ways to show alternatives beyond the Marey
- [onboarding-tickets-2026-06.md](archive/onboarding-tickets-2026-06.md) — kickoff discussion tickets (the kickoff has happened)
- [widget-b1-followups-prompt.md](archive/widget-b1-followups-prompt.md) — the verbatim brief handed to the building agent for widget B1
- [ui-exploration-prompt.md](archive/ui-exploration-prompt.md) — reusable prompt that generated the UI exploration synthesis
- [UI_LAYOUT_DESIGNER_IMPLEMENTATION_PROMPT.md](archive/UI_LAYOUT_DESIGNER_IMPLEMENTATION_PROMPT.md)
- [layout-designer-prompt-guide.md](archive/layout-designer-prompt-guide.md)
- [layout-preset-and-designer-alignment.md](archive/layout-preset-and-designer-alignment.md)
- [component-agent-build-guide.md](archive/component-agent-build-guide.md)
