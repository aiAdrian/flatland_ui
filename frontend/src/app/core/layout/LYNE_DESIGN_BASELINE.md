# Lyne / SBB Design Baseline

The complete UI design must be based on the SBB Lyne design system.

Reference:
https://lyne-angular-storybook.app.sbb.ch/angular/guides/getting-started

Current package in this project:

- @sbb-esta/lyne-elements

Rules:

1. Lyne/SBB components are the primary design source.
2. Do not invent custom panel styling if a Lyne/SBB component or token exists.
3. Panel layout structure is owned by the shared layout framework.
4. Feature panels must not define their own external width, margin, border, radius, shadow, or expansion behavior.
5. All visible panels must eventually use the shared PanelShell.
6. The PanelShell uses Lyne/SBB components and design tokens wherever possible.
7. Existing feature components are embedded as content inside the PanelShell.
8. Migration must be incremental and must not break existing functionality.

Target structure:

Column
  PanelShell
    Feature Component

Panel width is controlled by the layout column.
Panel outer appearance is controlled by PanelShell.
Panel inner business UI remains owned by the feature component.
