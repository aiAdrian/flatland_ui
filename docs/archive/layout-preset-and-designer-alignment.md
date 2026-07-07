# Layout Preset and Designer Alignment

## Purpose

This document explains how system/default layout presets, user-edited designer layouts, runtime layout selection, and component panel definitions should stay aligned.

Use it as prompt context when changing:

- default layout presets
- user layout persistence
- runtime layout loading
- designer palette entries
- panel type names
- plugin host mappings
- import/export compatibility

The goal is that runtime can render both system presets and designer-saved layouts through the same layout pipeline.

---

## Short Agent Context

Use this text as context for a new AI agent:

```text
We are working in the Flatland Dispatcher Angular frontend.

There are two related layout sources:
1. System/default layout presets shipped with the app.
2. User-created layouts saved by the Layout Designer.

Both should use the same FlatlandDesign shape:
- id
- name
- optional createdAt/updatedAt
- layout.columns
- columns[].panels
- panels[].type/title/config/sizing

Runtime should be able to render both system presets and user-created layouts through the same pipeline:
FlatlandDesign -> columns -> panels -> PanelShellComponent -> PanelPluginHostComponent -> concrete Angular component.

Important:
- Presets and designer layouts must stay compatible.
- Panel types in presets should exist in the designer palette or be intentionally preset-only.
- Panel types must be mapped in PanelPluginHostComponent or safely fallback.
- Runtime must fall back to default if the selected layout id is stale.
```

---

## Why Alignment Matters

System presets and designer layouts must stay aligned because the runtime should not care whether a layout came from code or localStorage.

Healthy layout system:

```text
System preset
  -> same shape as designer-saved layout
  -> same runtime renderer
  -> same panel shell
  -> same plugin host
  -> same concrete components
```

If presets and designer layouts drift apart, bugs appear.

Typical bugs:

- runtime can render presets but not user layouts
- designer preview works but runtime fails
- saved layouts miss fields expected by presets
- panel types exist in presets but not in designer palette
- designer can create panel types not mapped in plugin host
- imported layouts break because fields are inconsistent

The goal is one compatible layout contract.

---

## Canonical Layout Shape

A valid layout should be representable as:

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

Columns:

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

Panels:

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

System presets should avoid private runtime-only fields that the designer cannot preserve.

---

## Preset Rules

System/default presets should:

- use stable ids
- use human-readable names
- use the same column/panel structure as designer layouts
- use panel type strings that exist in plugin host
- preferably use panel type strings visible in designer palette
- include useful titles
- include safe default sizing
- keep `panel.config` JSON-serializable
- avoid functions, service instances, DOM nodes or circular data

Good preset ids:

```text
default-dispatcher
operations-overview
map-and-agents
compact-monitoring
```

Bad preset ids:

```text
layout-1
test
tmp
new
```

Preset ids should be stable because they may be referenced by runtime selection storage.

---

## Designer Rules

Designer-created layouts should:

- use the same shape as presets
- generate unique ids for new layouts
- generate unique ids for new panels
- preserve `panel.type` exactly
- preserve `panel.config` as JSON
- persist to canonical localStorage keys
- remain editable after reload
- remain renderable by runtime

The designer should not create panel types that runtime cannot safely render.

If a type is experimental, the plugin host must still provide a placeholder fallback.

---

## Panel Type Alignment

Every panel type used in any system preset should be checked against:

1. Designer palette.
2. Default panel creation logic.
3. PanelPluginHostComponent mapping.
4. Concrete component availability.
5. Unknown fallback behaviour.

For each `panel.type`, ask:

```text
Does a preset use this type?
Can the designer palette create this type?
Can the plugin host render this type?
Does the component work without active session?
Does the component work in runtime?
Does the component work in designer preview?
```

If the type is intentionally preset-only, document that reason. Otherwise it should usually be visible in the designer palette as well.

---

## Runtime Layout Resolution

Runtime should resolve a layout in a predictable order:

1. Explicit runtime selected layout id.
2. Designer active layout id.
3. First stored user layout.
4. System/default preset.

If a stored selected id is stale:

- ignore the stale id
- choose a valid fallback
- update selected id if appropriate
- do not crash

This is important after:

- Clear All Layouts
- deleting localStorage
- switching branches
- importing invalid layout JSON
- renaming system preset ids
- removing system preset ids

---

## Storage Keys

Canonical keys:

```text
flatland.designer.designs.v1
flatland.designer.active.v1
flatland.runtime.selectedLayoutId.v1
```

Legacy keys that may need read compatibility:

```text
flatland.layoutDesigner.designs.v1
flatland.layoutDesigner.active.v1
flatland.layouts.v1
```

Recommended storage behaviour:

Read:

- canonical first
- legacy if needed
- ignore invalid JSON
- ignore invalid layout objects
- deduplicate by id
- ensure default preset fallback

Write:

- canonical designer layouts key
- canonical designer active key
- runtime selected key when runtime selection changes

---

## Import / Export Alignment

Exported layouts should be valid `FlatlandDesign` JSON.

Imported layouts should be validated before becoming active.

Validation checklist:

- id exists or is generated
- name exists or is generated
- `layout.columns` is an array
- each column has id
- each column has panels array
- each panel has id
- each panel has type
- each panel has title
- config is serializable object if present

Invalid imports should show feedback and must not corrupt current state.

---

## Migration and Compatibility

If a preset or panel type changes, consider migration.

### Renaming a panel type

Bad:

```text
Old saved layouts use "marey-chart".
Code now only supports "graphic-timetable".
Old layouts break.
```

Better:

```text
Plugin host supports both:
- marey-chart
- graphic-timetable
```

or a migration maps old type to new type.

### Adding config fields

Bad:

```ts
const mode = panel.config.mode.toUpperCase();
```

This crashes if old layouts do not have `mode`.

Better:

```ts
const mode = String(panel?.config?.['mode'] || 'default');
```

---

## Default Layout Fallback

There should always be a valid default layout.

The default layout should:

- render without user storage
- render after Clear All Layouts
- render after invalid localStorage
- contain only mapped or safely fallback panel types
- be usable in runtime
- be usable in designer preview

If the app cannot find the selected layout, it should fall back to this default.

---

## Prompt: Change or Add a System Preset

```text
Change or add a Flatland Dispatcher system layout preset.

Context:
- System presets and designer-saved layouts must use the same FlatlandDesign shape.
- Runtime renders both through the same panel shell and plugin host.
- Panel types in presets should be mapped in PanelPluginHostComponent.
- Prefer panel types that are visible in the Layout Designer palette.
- Unknown panel fallback must still work.

Task:
<describe preset change>

Requirements:
- Use stable preset id.
- Use human-readable name.
- Use valid columns and panels.
- Keep panel.config serializable.
- Do not break existing saved layouts.
- Keep runtime fallback to default.
- Keep build green.
```

---

## Prompt: Align Designer and Presets

```text
Align Flatland Dispatcher Layout Designer and system presets.

Context:
- The designer creates FlatlandDesign objects.
- System presets should use the same shape.
- Runtime should render both user layouts and presets.
- Panel types must align across presets, designer palette and plugin host.

Please check:
- all preset panel.type values
- designer palette entries
- default panel creation
- PanelPluginHostComponent mapping
- unknown panel fallback
- runtime selected-layout fallback
- localStorage compatibility
```

---

## Alignment Checklist

Before committing preset/designer alignment changes:

```text
[ ] Presets use valid FlatlandDesign shape.
[ ] Designer saves the same shape.
[ ] Runtime can load presets.
[ ] Runtime can load designer layouts.
[ ] Default fallback exists.
[ ] Stale selected layout id does not crash runtime.
[ ] Preset panel types are mapped or safely fallback.
[ ] Designer palette types match plugin host types.
[ ] Panel config remains serializable.
[ ] Old saved layouts still render or migrate.
[ ] Build passes.
```

<!-- PANEL_RENDERING_EXAMPLE_START -->

## Correct Panel Rendering Example for Presets

System presets and designer-saved layouts should render through the same source-level structure.

Do not document browser-generated DOM as implementation source. Browser output may include Angular generated attributes, SBB shadow DOM, runtime ids, and accessibility ids. These details are useful for diagnosis but not for source code examples.

Correct source-level flow:

```text
FlatlandDesign
  -> columns
  -> panels
  -> PanelShellComponent
  -> PanelPluginHostComponent
  -> concrete Angular component
```

Example preset panel:

```ts
{
  id: 'summary-panel',
  type: 'situation-summary',
  title: 'Situation Summary',
  zone: 'left',
  minHeight: 150,
  height: 'auto',
  config: {}
}
```

The renderer should pass this panel to the shell:

```html
<app-panel-shell
  [panel]="panel"
  [zone]="column.zone">
</app-panel-shell>
```

The shell should provide the generic frame and delegate content rendering:

```html
<app-panel-plugin-host
  [panel]="panel">
</app-panel-plugin-host>
```

The plugin host should map the preset panel type:

```html
@switch (panel.type) {
  @case ('situation-summary') {
    <app-situation-summary></app-situation-summary>
  }

  @case ('new-user-component') {
    <app-new-user-component
      [panel]="panel"
      [embedded]="true">
    </app-new-user-component>
  }

  @default {
    <div class="panel-plugin-host__placeholder">
      <div class="panel-plugin-host__label">Plugin host</div>
      <div class="panel-plugin-host__type">{{ panel.type }}</div>
      <div class="panel-plugin-host__hint">
        No plugin component has been mapped for this panel type yet.
      </div>
    </div>
  }
}
```

Preset alignment rule:

```text
Every panel.type used by a preset must either:
- be mapped in PanelPluginHostComponent, or
- intentionally render the unknown panel fallback.
```

If a preset uses:

```text
type: "goal-achievement"
```

then the plugin host should usually contain:

```html
@case ('goal-achievement') {
  <app-goal-achievement-panel
    [panel]="panel"
    [embedded]="true">
  </app-goal-achievement-panel>
}
```

The designer palette, preset panel type, and plugin host mapping must use the exact same string.

<!-- PANEL_RENDERING_EXAMPLE_END -->
