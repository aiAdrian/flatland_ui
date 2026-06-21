# Layout preset & alignment with the Designer prompt

This branch (`experiment/vibecoding-playground`) ships a **fixed, opinionated
three-zone layout**. Adrian's
[`UI_LAYOUT_DESIGNER_IMPLEMENTATION_PROMPT.md`](https://github.com/aiAdrian/flatland_ui/blob/aiAdrian/Designer/docs/UI_LAYOUT_DESIGNER_IMPLEMENTATION_PROMPT.md)
(branch `aiAdrian/Designer`) instead asks for a **configurable layout *designer***
(drag-and-drop panels, 1/2/3 columns, EventBus/SharedState, persistence,
`/layout-designer` route, additive and non-invasive).

The two are **complementary, not competing**:

- The **designer system** is deferred — it is its own larger effort and should be
  built additively as Adrian's prompt describes (new files under `core/layout/`
  and `features/layout/`, mirror-don't-replace, phase by phase).
- Our **three-zone layout is intended to become one `LayoutDefinition` preset**
  inside that system — the "sensible default" a user could start from. This doc
  expresses our current layout in the prompt's own vocabulary so the later
  migration is mechanical.

Panel rewrites on this branch (e.g. Agent Inspector → map overlay) are
**intentional and sanctioned by the project owner** where they improve the
content; they are not accidental regressions.

---

## Our layout expressed as the prompt's models

Illustrative only — matches the field names in the prompt's `PanelDefinition` /
`LayoutDefinition`. Not wired at runtime yet (to avoid clashing with whatever
already exists on `aiAdrian/Designer`).

### Panels (PanelDefinition)

| id | title | category | notes vs. baseline |
|---|---|---|---|
| `situation-summary` | Situation | situation | **new** (Hypervision synthesis) |
| `notifications` | Event Feed | situation | relabelled, criticality markers |
| `agents` | Agents | situation | moved to left column |
| `flatland-map` | Map | visualisation | unchanged core |
| `marey` | Marey | visualisation | unchanged core |
| `layer-visibility` | Layers | visualisation | moved into map controls bar (chips) |
| `agent-inspector` | Agent Details | visualisation | **rewritten** as floating map-corner overlay + actions |
| `scenario` | Policies | intervention | neutral vs. recommended per mode |
| `recommendations` | Recommendations | intervention | shown only in Recommendation mode |
| `kpi-filter` | Options (KPI) | intervention | moved to right column |

### Layout (LayoutDefinition)

```jsonc
{
  "id": "default-three-zone",
  "name": "Three-zone (Situation · Visualisation · Intervention)",
  "mode": "three-column",
  "columns": [
    { "id": "left",   "role": "situation",     "panels": ["situation-summary", "notifications", "agents"] },
    { "id": "center", "role": "visualisation",  "panels": ["flatland-map", "marey" /* + layer-visibility in controls, agent-inspector as overlay */] },
    { "id": "right",  "role": "intervention",   "panels": ["scenario", "recommendations", "kpi-filter"] }
  ]
}
```

Notes:
- `layer-visibility` and `agent-inspector` are **not** ordinary column panels in
  our build — they live in the map controls bar / as a map overlay. In the
  designer model they'd be panels with a "docked to map" capability, or simply
  map-internal widgets. Worth a short discussion when the designer lands.
- Left column splits Event Feed / Agents 50/50; situation-summary is fixed-height
  on top. In the designer this maps to per-panel height + a fixed/auto flag.

---

## What is feature-layer vs. layout-layer

Helps Adrian adopt the parts independently:

**Feature-layer (independent of the layout system — safe to take as-is):**
- Interaction modes `recommendation | co-learning | director` and the single
  `optionPresentation` flag (`SessionStore`).
- KPI filter wiring (`kpiWeights`) + scenario ranking.
- Hypervision `situation-summary`.
- Co-Learning intervention log + reflection panel.
- Header mode switcher + app menu (Settings/Scenarios/Reset).

**Layout-layer (the part that should eventually live inside the designer):**
- The fixed three-column arrangement and panel moves.
- Map controls bar (View + Layers).
- Agent details as a map overlay.

---

## Deferred (Adrian's prompt, not done here)

- `core/layout/` models + `panel-registry` + `layout-store`.
- `ui-event-bus` / `ui-shared-state` services (we use `SessionStore` signals
  directly; an `EventBusService` already exists for some panel events).
- Drag-and-drop, resize, persistence (LocalStorage / JSON), start page.
- `/layout-designer` and runtime layout-view routes.
- Delivery via small Python update scripts.

When we (or Adrian) start the designer: follow the prompt's phase order, keep it
additive, and register `default-three-zone` above as the first built-in preset.
