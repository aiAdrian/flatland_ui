# Component Shell, Plugin Host and Panel API

## Purpose

This document describes how the Flatland Dispatcher UI renders layout-driven components through the panel shell and plugin host architecture.

It is intended as a prompt-ready technical reference for AI-assisted development. Use it when adding new layout components, changing panel rendering, debugging preview/runtime rendering, or extending the Layout Designer palette.

---

## Prompt Context

Use this context block when asking an AI assistant to work on component shell or plugin integration:

```text
We are working in the Flatland Dispatcher Angular frontend.

The UI is layout-driven:
- A FlatlandDesign describes the full UI layout.
- A layout contains columns.
- Columns contain panels.
- Panels are rendered by PanelShellComponent.
- PanelShellComponent delegates the concrete content to PanelPluginHostComponent.
- PanelPluginHostComponent maps panel.type to an Angular component.
- Unknown panel types must render a safe placeholder and must not crash.
- Components must work in runtime and in Layout Designer live preview.

When adding a new panel component:
1. Define a stable kebab-case panel type.
2. Add it to the Layout Designer palette.
3. Add default panel metadata.
4. Map the panel type in PanelPluginHostComponent.
5. Ensure the component has an embedded-safe API and CSS.
6. Ensure it renders safely without active session data.
7. Test in designer preview and runtime.
```

---

## High-Level Architecture

The layout rendering pipeline is:

```text
FlatlandDesign
  ↓
Runtime layout renderer
  ↓
Column renderer
  ↓
PanelShellComponent
  ↓
PanelPluginHostComponent
  ↓
Concrete Angular component
```

The important separation is:

```text
Layout data decides what exists.
Panel shell decides how a panel is framed.
Plugin host decides which component is rendered.
Concrete components decide their own content.
```

---

## Core Data Model

### FlatlandDesign

A design is the complete saved layout.

Conceptual shape:

```ts
export interface FlatlandDesign {
  id: string;
  name: string;
  createdAt?: string;
  updatedAt?: string;
  layout: {
    columns: DesignerColumn[];
  };
}
```

### DesignerColumn

A column describes one vertical runtime area.

```ts
export interface DesignerColumn {
  id: string;
  title?: string;
  zone?: 'left' | 'center' | 'right' | string;
  widthPx?: number;
  widthFr?: number;
  panels: DesignerPanel[];
}
```

### DesignerPanel

A panel describes one component instance.

```ts
export interface DesignerPanel {
  id: string;
  type: string;
  title: string;
  zone?: string;
  minHeight?: number;
  height?: number | 'auto';
  expanded?: boolean;
  config?: Record<string, unknown>;
}
```

The exact TypeScript interfaces may evolve. The conceptual contract should remain stable.

---

## PanelShellComponent

The shell is the visual wrapper around a panel.

Typical responsibilities:

```text
- render the panel title
- render a header
- choose canvas or accordion/scroll mode
- apply panel height and min-height
- apply zone-specific shell styling
- keep layout sizing stable
- delegate content to PanelPluginHostComponent
```

The shell should not implement business logic for specific panel types.

Good shell logic:

```text
OK:
- show title
- show header
- choose canvas shell for map/chart panels
- choose scroll shell for list/detail panels
- pass panel and zone to plugin host
```

Avoid shell logic like:

```text
Avoid:
- direct agent filtering
- direct simulation state mutation
- direct map interaction
- component-specific state handling
- special-case business rules for one panel type
```

---

## PanelPluginHostComponent

The plugin host resolves a `panel.type` string to a concrete Angular component.

Conceptual example:

```ts
switch (panel.type) {
  case 'agents-list':
    return AgentsPanelComponent;

  case 'flatland-map':
  case 'simulation-map':
    return FlatlandMapComponent;

  case 'graphic-timetable':
  case 'marey-chart':
    return GraphicTimetableComponent;

  case 'agent-inspector':
    return AgentInspectorComponent;

  case 'impact':
    return ImpactPanelComponent;

  default:
    return PlaceholderComponent;
}
```

The actual project may use Angular template control flow instead of a TypeScript switch. The rule is the same: map stable panel type strings to components.

---

## Known Panel Types

Common panel types include:

```text
agents-list
simulation-map
flatland-map
marey-chart
graphic-timetable
agent-inspector
goal-achievement
impact
timeline
validation
cell-inspector
```

Some panel types may intentionally render a placeholder until the corresponding component exists.

---

## Component API Contract

A component rendered through the layout system should support embedded rendering.

Recommended API:

```ts
@Input() panel?: DesignerPanel;
@Input() zone?: string;
@Input() previewMode?: 'live' | 'wireframe';
@Input() embedded?: boolean;
```

Not every existing component has all these inputs. When adding new components, prefer this shape.

### Required Behaviour

A layout plugin component must:

```text
- render without an active session
- render without selected agent/cell
- handle missing or partial data
- fit inside the parent panel
- respect constrained width and height
- avoid fixed viewport positioning
- avoid global side effects during render
- work in runtime
- work in designer live preview
```

### Recommended States

Each plugin should provide safe states:

```text
- loading
- empty
- unavailable
- active data
- error/fallback if needed
```

Example:

```html
@if (!session) {
  <div class="empty-state">
    No active session.
  </div>
} @else {
  <!-- component content -->
}
```

---

## Embedded Styling Rules

Panel components should be layout-safe.

Recommended base CSS:

```scss
:host {
  display: block;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}
```

For scrollable content:

```scss
:host {
  min-height: 0;
  overflow: auto;
}
```

For canvas/map/chart components:

```scss
:host {
  display: block;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

svg,
canvas {
  display: block;
  width: 100%;
  height: 100%;
}
```

Avoid:

```scss
position: fixed;
width: 100vw;
height: 100vh;
```

unless the component is intentionally a global overlay.

---

## Canvas Panels

Canvas panels are panels that should fill their available body area.

Typical examples:

```text
flatland-map
simulation-map
graphic-timetable
marey-chart
```

Canvas panels usually need:

```text
- height: 100%
- min-height: 0
- overflow: hidden
- parent-driven resize
- no hardcoded viewport height
```

The shell may mark them with canvas mode, for example:

```text
layout-panel-shell--canvas
panel-plugin-host--canvas
```

---

## Scroll Panels

Scroll panels are panels that contain lists, detail cards or forms.

Typical examples:

```text
agents-list
agent-inspector
impact
timeline
validation
cell-inspector
```

Scroll panels should:

```text
- allow vertical scrolling if content is long
- avoid horizontal overflow
- work at narrow widths
- render meaningful empty states
```

---

## Adding a New Component

### Step 1: Choose a Panel Type

Use stable lowercase kebab-case:

```text
service-quality
dispatch-recommendations
network-health
train-conflicts
```

Avoid temporary or ambiguous names:

```text
panel1
newComponent
service quality
tmp-widget
```

### Step 2: Add Palette Entry

Add the component to the Layout Designer palette.

Conceptual example:

```ts
{
  type: 'service-quality',
  title: 'Service Quality',
  description: 'Shows punctuality and service quality indicators.',
  minHeight: 150
}
```

The exact palette structure may differ. It should at least define:

```text
- type
- title
- optional default minHeight
- optional default config
```

### Step 3: Add Default Panel Creation

When dropped into a layout, the designer should create:

```ts
{
  id: createId(),
  type: 'service-quality',
  title: 'Service Quality',
  minHeight: 150,
  height: 'auto',
  expanded: true,
  config: {}
}
```

### Step 4: Create the Component

Example:

```ts
@Component({
  selector: 'app-service-quality-panel',
  templateUrl: './service-quality-panel.component.html',
  styleUrl: './service-quality-panel.component.scss',
})
export class ServiceQualityPanelComponent {
  @Input() panel?: DesignerPanel;
  @Input() zone?: string;
  @Input() embedded = true;
}
```

### Step 5: Map it in the Plugin Host

Template-style example:

```html
@if (panel.type === 'service-quality') {
  <app-service-quality-panel
    [panel]="panel"
    [zone]="zone"
    [embedded]="true">
  </app-service-quality-panel>
}
```

Switch-style example:

```ts
case 'service-quality':
  return ServiceQualityPanelComponent;
```

### Step 6: Test Runtime and Designer

Designer checklist:

```text
[ ] Appears in palette.
[ ] Can be dragged into a column.
[ ] Can be selected.
[ ] Can be resized if supported.
[ ] Can be saved.
[ ] Still appears after reload.
[ ] Does not crash live preview.
```

Runtime checklist:

```text
[ ] Appears in selected layout.
[ ] Handles no active session.
[ ] Handles active session.
[ ] Respects panel width.
[ ] Respects panel height.
[ ] Does not overlap header/footer.
[ ] Does not break unknown panel fallback.
```

---

## Unknown Panel Fallback

Unknown panel types must not crash the app.

Expected fallback content:

```text
Plugin host
Panel type: <type>
No plugin component has been mapped for this panel type yet.
```

This behaviour is important for:

```text
- imported layouts
- old saved layouts
- future panel types
- partially implemented features
```

---

## Storage Keys

Layouts are usually stored in localStorage.

Preferred canonical keys:

```text
flatland.designer.designs.v1
flatland.designer.active.v1
flatland.runtime.selectedLayoutId.v1
```

Legacy keys may exist:

```text
flatland.layoutDesigner.designs.v1
flatland.layoutDesigner.active.v1
flatland.layouts.v1
```

New code should prefer canonical keys but may read legacy keys for compatibility.

---

## Common Pitfalls

### Side Effects During Template Evaluation

Avoid methods called from templates that mutate state.

Bad:

```ts
designerLayoutOptions(): FlatlandDesign[] {
  this.refreshDesignerLayoutList();
  return this.designs;
}
```

Good:

```ts
designerLayoutOptions(): FlatlandDesign[] {
  return this.designs;
}
```

Refresh explicitly from events:

```html
<select
  (focus)="refreshDesignerLayoutList()"
  (click)="refreshDesignerLayoutList()">
</select>
```

### Fixed Positioning in Embedded Components

A component inside a panel should not assume full viewport ownership.

Bad:

```scss
:host {
  position: fixed;
  inset: 0;
}
```

Good:

```scss
:host {
  display: block;
  width: 100%;
  min-width: 0;
}
```

### Missing Data

Designer preview may render without real runtime data. Components must not throw if services return empty state.

---

## Prompt: Add a New Panel Component

```text
Add a new layout plugin component to the Flatland Dispatcher Angular frontend.

Panel type: <panel-type>
Title: <title>
Purpose: <purpose>

Requirements:
- Add the panel type to the Layout Designer palette.
- Add default panel metadata for new instances.
- Map the panel type in PanelPluginHostComponent.
- The component must render safely with no active session.
- The component must support embedded panel rendering.
- The component must not use fixed viewport positioning.
- The component must work in designer live preview and runtime.
- Unknown panel types must still render the existing placeholder.
- Keep unrelated panel types unchanged.
- Keep the Angular build green.
```

---

## Prompt: Debug a Panel Rendering Problem

```text
Debug a panel rendering issue in the Flatland Dispatcher layout system.

Context:
- Layouts contain columns and panels.
- Panels are rendered by PanelShellComponent.
- Concrete content is resolved by PanelPluginHostComponent using panel.type.
- Components must work in runtime and designer preview.
- Unknown panel types should render a placeholder.

Problem:
<describe the issue>

Please inspect:
- panel.type string
- designer palette entry
- default panel creation
- plugin host mapping
- required component inputs
- shared services used by the component
- shell mode: canvas vs scroll
- component CSS for fixed positioning or overflow
- missing-data handling
```

---

## Implementation Checklist

```text
[ ] Stable kebab-case panel type.
[ ] Palette entry exists.
[ ] Default panel creation exists.
[ ] Plugin host mapping exists.
[ ] Component handles no session.
[ ] Component handles missing selected agent/cell.
[ ] Component has embedded-safe CSS.
[ ] Component renders in designer preview.
[ ] Component renders in runtime.
[ ] Unknown panel fallback still works.
[ ] Build passes.
```

