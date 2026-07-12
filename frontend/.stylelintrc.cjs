/**
 * Stylelint — colour gate only.
 *
 * Purpose: stop NEW hardcoded colours from entering the codebase. We deliberately
 * do NOT extend a full config (e.g. stylelint-config-standard-scss) — that would
 * flag hundreds of unrelated legacy style issues and drown the signal. This config
 * enforces exactly one thing: no raw hex / named colours.
 *
 * Rules & rationale: docs/reference/frontend-lyne-conventions.md (§1).
 * Use Lyne/app design tokens or light-dark() instead of literal colours.
 *
 * TWO allowlists below:
 *   1. TOKEN_LAYER  — files where literal colours are correct (token definitions).
 *                     Permanent. Do not migrate.
 *   2. LEGACY_DEBT  — ~31 files that predate this rule (~1085 hex). Grandfathered.
 *                     This list is a debt register: when you tokenise a file's
 *                     colours, REMOVE it from the list so the gate starts guarding
 *                     it. New files are guarded by default (not on either list).
 */

// Literal colours are the intended content here (the token layer).
const TOKEN_LAYER = [
  'src/styles.scss',
];

// Pre-existing debt. Shrink this list over time; never add to it.
const LEGACY_DEBT = [
  'src/app/app.component.scss',
  'src/app/features/agent-inspector/agent-inspector.component.scss',
  'src/app/features/agents-panel/agents-panel.component.scss',
  'src/app/features/co-learning-reflection/co-learning-reflection.component.scss',
  'src/app/features/demo-complete/demo-complete.component.scss',
  'src/app/features/director-directive/director-directive.component.scss',
  'src/app/features/flatland-map/flatland-map.component.scss',
  'src/app/features/goal-achievement/goal-achievement.component.scss',
  'src/app/features/help-about/help-about.component.scss',
  'src/app/features/impact-panel/impact-panel.component.scss',
  'src/app/features/kpi-filter/kpi-filter.component.scss',
  'src/app/features/layer-visibility/layer-visibility.component.scss',
  'src/app/features/layout-designer/layout-designer.component.scss',
  'src/app/features/layout/components/layout-renderer/layout-renderer.component.scss',
  'src/app/features/layout/components/panel-plugin-host/panel-plugin-host.component.scss',
  'src/app/features/layout/components/panel-shell/panel-shell.component.scss',
  'src/app/features/layout/pages/layout-sandbox/layout-sandbox.component.scss',
  'src/app/features/left-sidebar/left-sidebar.component.scss',
  'src/app/features/marey-chart/marey-chart.component.scss',
  'src/app/features/mode-intro/mode-intro.component.scss',
  'src/app/features/notifications-panel/notifications-panel.component.scss',
  'src/app/features/scenario-panel/scenario-panel.component.scss',
  'src/app/features/simulation-slider/simulation-slider.component.scss',
  'src/app/features/situation-summary/situation-summary.component.scss',
  'src/app/features/status-bar/status-bar.component.scss',
  'src/app/features/survey/survey.component.scss',
  'src/app/features/toolbar/toolbar.component.scss',
  'src/app/features/view-toggle/view-toggle.component.scss',
  'src/app/shared/layout/panels/goal-achievement-panel/goal-achievement-panel.component.scss',
  'src/app/shared/layout/panels/layout-view-toggle-panel/layout-view-toggle-panel.component.scss',
];

const COLOUR_MESSAGE =
  'No hardcoded colours — use Lyne/app design tokens (--sbb-color-*, --app-*) ' +
  'or light-dark(). See docs/reference/frontend-lyne-conventions.md §1.';

module.exports = {
  customSyntax: 'postcss-scss',
  rules: {
    'color-no-hex': [true, { message: COLOUR_MESSAGE }],
    'color-named': ['never', { message: COLOUR_MESSAGE }],
  },
  overrides: [
    {
      files: [...TOKEN_LAYER, ...LEGACY_DEBT],
      rules: {
        'color-no-hex': null,
        'color-named': null,
      },
    },
  ],
};
