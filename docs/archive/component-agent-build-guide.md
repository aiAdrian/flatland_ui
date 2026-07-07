

<!-- PANEL_RENDERING_EXAMPLE_START -->

## Correct Source-Level Panel Rendering Example

When a browser inspection shows a rendered panel like:

```text
app-panel-shell
  sbb-expansion-panel
    app-panel-plugin-host
      app-situation-summary
```

do not copy the full browser DOM into source code. The browser DOM contains generated Angular attributes, SBB shadow DOM, generated ids and accessibility wiring.

Use this simplified source-level model instead:

```text
PanelShellComponent
  owns the panel frame

PanelPluginHostComponent
  maps panel.type to the concrete Angular component

Concrete component
  renders feature-specific content
```

Correct plugin host example:

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

If the browser shows the fallback for a panel type, for example:

```text
panel.type = "goal-achievement"
No plugin component has been mapped for this panel type yet.
```

then the correct implementation task is:

```text
1. Create or locate the Angular component.
2. Import it in PanelPluginHostComponent.
3. Add it to standalone imports if needed.
4. Add a matching @case for the exact panel.type.
5. Keep the @default fallback unchanged.
```

Do not edit browser-generated DOM.

<!-- PANEL_RENDERING_EXAMPLE_END -->
