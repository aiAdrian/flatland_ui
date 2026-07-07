# Deutsche Zusammenfassung — UI Layout Designer / Plugin Panel Framework

Ziel dieses Vorhabens ist der Aufbau eines flexiblen, dynamischen UI‑Layout‑Systems für die Flatland UI. Die bestehende Applikation funktioniert aktuell gut und darf durch diesen Umbau nicht beschädigt werden. Deshalb soll das neue Layout‑Framework zunächst parallel zur bestehenden Oberfläche entstehen und erst später kontrolliert aktiviert werden.

Das neue System soll Layouts mit einer, zwei oder drei Spalten unterstützen. Jede Spalte soll frei konfigurierbare Panels enthalten können. Diese Panels sollen sich wie Plugins verhalten: Sie besitzen eine gemeinsame Panel‑Hülle, können verschoben, in der Grösse verändert, gespeichert, geladen, exportiert und importiert werden. Die konkrete Panel‑Funktionalität soll dabei zunächst nicht neu geschrieben werden. Bestehende Panels werden später lediglich in die neue Panel‑Shell eingebettet.

Die aktuell zwingend zu unterstützenden Panels sind:

1. Notifications Panel
2. Layer Visibility Panel
3. KPI Filter Panel
4. Scenario Panel
5. Recommendations Panel
6. Agents Panel
7. Agent Inspector Panel
8. Flatland Map
9. Marey Chart / Graphic Timetable

Die wichtigste Anforderung ist, dass die bestehende Funktionalität dieser Panels erhalten bleibt. Bestehende Logik in `SessionStore`, Map, Marey Chart, Forecast, Layer Visibility, Agent Selection, Hover‑Verknüpfung und Action Overrides darf nicht entfernt oder ersetzt werden. Der Umbau muss schrittweise und rückbaubar erfolgen.

Die Kommunikation zwischen den Panels soll langfristig über einen zentralen Informationsbus laufen. Dieser besteht aus zwei Teilen:

- einem `EventBus` für kurzfristige Ereignisse, zum Beispiel Agent ausgewählt, Agent gehovered, Zelle gehovered, Szenario‑Preview ausgewählt oder Layer Visibility geändert;
- einem `SharedState` für dauerhaften globalen UI‑Zustand, zum Beispiel aktuell selektierter Agent, gehoverte Zelle, aktives Szenario, sichtbare Layer oder aktives Layout.

Wichtig ist: EventBus und SharedState sollen anfangs nur ergänzend eingeführt werden. Bestehende direkte Store‑Zugriffe werden nicht sofort entfernt. Stattdessen werden Ereignisse und Zustände zunächst gespiegelt, damit das bestehende Verhalten stabil bleibt.

Die Umsetzung soll in kleinen, klar getrennten Schritten erfolgen. Jeder Schritt soll als kleines Python‑Update‑Skript geliefert werden, das direkt aus dem Repository‑Root ausgeführt werden kann. Jedes Skript soll genau einen verständlichen Zweck haben, zum Beispiel Datenmodelle anlegen, EventBus hinzufügen, SharedState hinzufügen, PanelRegistry erstellen, LayoutStore einführen, PanelShell erstellen, LayoutRenderer erstellen oder Designer‑Route ergänzen.

Der erste technische Schritt ist eine nicht invasive Foundation‑Phase. Dabei werden nur neue Dateien unter `frontend/src/app/core/layout/` und `frontend/src/app/features/layout/` erstellt. Die bestehende UI wird dabei nicht ersetzt und nicht aktiv umgebaut. Erst wenn diese Grundlage kompiliert und committed ist, wird eine Sandbox‑Route für den Layout Designer ergänzt. Danach können echte Panel‑Adapter gebaut werden, die die bestehenden Komponenten nur einbetten, nicht neu implementieren.

Der UI‑Designer soll später ermöglichen, Panels visuell zu platzieren, zwischen Spalten zu verschieben und in der Grösse zu verändern. Layouts sollen im LocalStorage gespeichert und zusätzlich als JSON‑Datei exportiert bzw. importiert werden können. Auf einer späteren Startseite soll eine Liste gespeicherter Designs erscheinen, aus der ein Design ausgewählt oder ein neues Design erstellt werden kann.

Die visuelle Richtung lautet: weniger ist mehr. Das UI soll einfacher, ruhiger und klarer werden, mit weniger visueller Unruhe, konsistenten Panels, konsistentem Spacing, neutralen Statusanzeigen und möglichst SBB/Lyne‑naher Gestaltung. Funktionale Stabilität ist aber wichtiger als optische Änderungen.

Nach jedem Umsetzungsschritt müssen Build und Tests geprüft werden. Frontend‑Budget‑Warnings sind akzeptabel, solange der Build erfolgreich abgeschlossen wird. Änderungen sollen in kleinen, sinnvollen Commits gesichert werden.

Diese Datei dient als Übergabe‑Prompt. Ein zukünftiger AI‑Assistent soll zuerst prüfen, ob die Foundation‑Phase bereits existiert. Falls nicht, soll er mit kleinen Python‑Skripten für Phase 1 beginnen. Falls Phase 1 bereits vorhanden ist, soll er mit der Designer‑Sandbox‑Route weitermachen. Die bestehende Applikation darf niemals in einem grossen Schritt ersetzt werden.

---

# UI Layout Designer / Plugin Panel Framework — Implementation Plan

## Purpose

This document is the handover and implementation plan for building a flexible UI layout framework for the Flatland UI project.

The goal is to build a dynamic UI layout system that can switch between one-, two- and three-column layouts. Each column can contain configurable UI panels. Panels should behave like plugins, have a unified panel shell, be movable, resizable, persistable, and communicate through a central information bus.

The central information bus consists of:

1. EventBus
2. SharedState

This document should allow a future AI assistant session to continue safely after context loss, crash, or another day of development.

---

## Most Important Rule

Do not break or rewrite the current working panel functionality.

The current UI works well. Existing panels must keep their current behavior.

The new layout system must first be implemented in parallel as a non-invasive foundation. Only after the foundation is stable should existing panels be wrapped into the new layout system.

Do not remove or rewrite:

- existing SessionStore logic
- existing Forecast / Marey logic
- existing Override logic
- existing hover / selection logic
- existing Layer Visibility logic
- existing panel-specific logic

Migration must happen gradually.

---

## Required Development Style

Implementation should be delivered as small, understandable Python update scripts.

Each script should have exactly one clear purpose, for example:

- create layout models
- create EventBus
- create SharedState
- create PanelRegistry
- create LayoutStore
- create PanelShell
- create LayoutRenderer
- create LayoutDesigner
- add PluginHost
- add drag and drop
- add resize
- add persistence
- add start page
- connect runtime layout view

Do not provide one huge patch.

Each answer should explain briefly in prose what the script does, then provide the Python script.

---

## Branch

Continue work on:

    aiAdrian/Designer

Before making changes:

    cd ~/workspace/ai4realnet/flatland_ui
    git status
    git branch --show-current

Expected branch:

    aiAdrian/Designer

---

## Existing Panels That Must Be Supported

The layout framework must fully support these existing panels:

1. Notifications Panel
2. Layer Visibility Panel
3. KPI Filter Panel
4. Scenario Panel
5. Recommendations Panel
6. Agents Panel
7. Agent Inspector Panel
8. Flatland Map
9. Marey Chart / Graphic Timetable

These panels should become plugin-like panels, but their internal behavior must not be changed initially.

---

## Target Architecture

Create a new parallel layout framework under:

    frontend/src/app/core/layout/
    frontend/src/app/features/layout/

Suggested files:

    frontend/src/app/core/layout/layout.models.ts
    frontend/src/app/core/layout/ui-event-bus.service.ts
    frontend/src/app/core/layout/ui-shared-state.service.ts
    frontend/src/app/core/layout/panel-registry.service.ts
    frontend/src/app/core/layout/layout-store.service.ts
    frontend/src/app/core/layout/index.ts

    frontend/src/app/features/layout/panel-shell/
    frontend/src/app/features/layout/layout-renderer/
    frontend/src/app/features/layout/layout-designer/
    frontend/src/app/features/layout/panel-plugin-host/

---

## Core Concepts

### PanelDefinition

Describes available panel types.

Fields:

- id
- title
- description
- category
- component selector or component mapping
- default size
- capabilities:
  - movable
  - resizable
  - closable
  - collapsible
  - fullscreen optional

### PanelInstance

Represents a placed panel in a layout.

Fields:

- instanceId
- panelId
- columnId
- order
- widthPx
- heightPx
- collapsed
- locked
- visible
- config

### LayoutDefinition

Represents a complete UI layout.

Fields:

- id
- name
- description
- version
- mode: one | two | three
- columns
- panels
- createdAt
- updatedAt

### EventBus

Used for transient communication between panels.

Example events:

- ui.panel.focused
- agent.selected
- agent.hovered
- trajectory.cell.hovered
- scenario.preview.selected
- layer.visibility.changed
- marey.point.hovered
- map.cell.hovered
- override.changed

### SharedState

Used for durable global UI state.

Example keys:

- selectedAgent
- hoveredAgent
- hoveredCell
- activeScenarioId
- previewScenarioId
- layerVisibility
- designerMode
- activeLayoutId
- showMap
- showMarey

---

## Migration Rule

Existing panels should initially continue to use existing stores and services.

The new EventBus and SharedState should first be introduced as optional mirrors, not as replacements.

Preferred migration pattern:

    this.store.selectedHandle.set(handle);
    this.uiBus.emit('agent.selected', { handle });
    this.sharedState.set('selectedAgent', handle, 'agents-panel');

Avoid immediate replacement of existing store logic.

---

## Phase 1 — Foundation Only, No Activation

Goal: add new files only. Do not change existing UI behavior.

Implement:

1. layout.models.ts
2. ui-event-bus.service.ts
3. ui-shared-state.service.ts
4. panel-registry.service.ts
5. layout-store.service.ts
6. panel-shell
7. layout-renderer with placeholders
8. layout-designer with basic create/save/export/import
9. barrel export index.ts

This phase should not affect existing runtime UI.

After Phase 1:

    cd ~/workspace/ai4realnet/flatland_ui/frontend
    npm run build

    cd ..
    git status
    git add frontend/src/app/core/layout frontend/src/app/features/layout
    git commit -m "Add layout framework foundation"
    git push

---

## Phase 2 — Designer Sandbox Route

Add a sandbox route or dev-only entry point:

    /layout-designer

Important:

- Do not replace the normal simulation view.
- Do not alter the existing default app route.
- Keep it sandboxed.

---

## Phase 3 — Panel Plugin Host

Create a PanelPluginHostComponent that maps panel IDs to existing Angular components.

It should render existing components such as:

- app-notifications
- app-layer-visibility
- app-kpi-filter
- app-scenarios
- app-recommendations
- app-agents
- app-agent-inspector
- app-flatland-map
- app-marey-chart

Important:

- Do not rewrite these panels.
- Just wrap/render them.
- If a component is not standalone, adapt imports carefully.
- Build after each adapter step.

---

## Phase 4 — Drag and Drop

Add panel movement:

- reorder panels within the same column
- move panels between columns
- update PanelInstance.columnId
- update PanelInstance.order
- save layout after changes

Prefer Angular CDK drag/drop if already available. If not, inspect dependencies before adding packages.

---

## Phase 5 — Resize

Add resizing:

- column widths
- panel heights

Persist values in layout:

- PanelInstance.heightPx
- LayoutColumnDefinition.widthFr

---

## Phase 6 — Persistence and Start Page

Implement a start page that lists saved designs.

Required actions:

- select design
- create new design
- duplicate design
- delete design
- export design
- import design file

Storage:

- LocalStorage first
- export/import JSON file

---

## Phase 7 — Runtime Layout View

Add a runtime layout view that renders the selected layout without edit controls.

Important:

- Initially behind a route or feature flag.
- Do not replace existing main UI until verified.
- Existing UI must remain fallback.

---

## Phase 8 — EventBus / SharedState Migration

Gradually connect panels to EventBus and SharedState.

Suggested event flows:

Agent selection:

    Agents Panel -> agent.selected -> Map, Marey, Inspector

SharedState:

    selectedAgent

Agent hover:

    Agents Panel / Map / Marey -> agent.hovered

SharedState:

    hoveredAgent

Cell hover:

    Map / Marey -> trajectory.cell.hovered

SharedState:

    hoveredCell

Scenario preview:

    Scenario Panel -> scenario.preview.selected -> Marey

SharedState:

    previewScenarioId

Layer visibility:

    Layer Visibility -> layer.visibility.changed -> Map, Marey

SharedState:

    layerVisibility

---

## Testing Rules

After every implementation phase:

    cd ~/workspace/ai4realnet/flatland_ui
    python -m pytest -q

Frontend build:

    cd ~/workspace/ai4realnet/flatland_ui/frontend
    npm run build

Budget warnings are acceptable if the build completes with:

    Application bundle generation complete

---

## Commit Rules

Commit small phases separately.

Example commits:

    git commit -m "Add layout framework foundation"
    git commit -m "Add layout designer sandbox route"
    git commit -m "Add panel plugin host"
    git commit -m "Add draggable layout panels"
    git commit -m "Add resizable layout panels"
    git commit -m "Add layout design start page"
    git commit -m "Render selected layout in runtime view"

---

## Existing Recent Work That Must Not Be Broken

Recent stable changes include:

1. Marey history and forecast unified topology enrichment
2. Backend Marey history snapshots
3. Driver-view Marey topology rendering
4. Action override execution only at decision points
5. STOP override sticky at decision point until cleared or replaced
6. Neutral Episode Finished status
7. Layer Visibility UI cleanup

Do not regress these.

---

## Override Semantics To Preserve

Action overrides behave as follows:

LEFT / FORWARD / RIGHT:

    pending until SWITCH or MERGING
    applied once at DP
    then cleared

STOP:

    pending until SWITCH or MERGING
    applied at DP
    remains active until user clears or replaces it

---

## UI Design Direction

The desired UI direction is:

- less is more
- simple
- clean
- SBB / Lyne style
- less visual noise
- no unnecessary green success tags
- neutral information where possible
- consistent panel shell
- consistent spacing
- consistent typography

---

## Next AI Task

Continue from this document.

First ask whether Phase 1 foundation files have already been created.

If not, provide Phase 1 as small Python scripts.

If Phase 1 already exists, inspect files and continue with Phase 2: Designer Sandbox Route.

Always use small Python update scripts and prose explanations.

Never rewrite the whole app in one step.

Never break existing panel functionality.
