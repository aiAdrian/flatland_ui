/**
 * Built-in runtime layouts, shipped with the repo.
 *
 * Until now a layout was either the one hardcoded default or something a user
 * had saved into `localStorage` from the Layout Designer. That makes a layout
 * we actually want to study unreviewable: it lives in one browser, nobody can
 * diff it, and clearing site data loses it. A preset is the same data structure
 * as a saved design, but versioned here — so a layout can be proposed, reviewed
 * and changed like any other piece of the product.
 *
 * Presets are offered alongside saved designs in the session dialog. They are
 * *offered*, never auto-applied: mode-scoped layouts (a layout resolving from
 * `interactionMode`) are a separate, unbuilt step — see
 * docs/plans/mode-scoped-layouts-plan.md.
 *
 * **Known gap, inherited:** the saved-layout runtime path does not consult
 * `panel-mode-availability`. So a preset naming a mode-restricted panel (the
 * reflection is `['co-learning']`) will render it in any mode. That is the same
 * bypass the mode-scoped-layouts plan describes in its §1, not something these
 * presets introduce — but it means a preset's *name* currently carries its
 * intended mode, and nothing enforces it. Choose the matching mode when using
 * one until the resolver exists.
 */

export interface LayoutPresetPanel {
  id: string;
  type: string;
  title: string;
  expanded: boolean;
  collapsible: boolean;
  minHeight: number;
  settings?: Record<string, unknown>;
}

export interface LayoutPresetColumn {
  id: string;
  rowId: string;
  name: string;
  /** Percent of the row. */
  width: number;
  role: 'sidebar' | 'main' | 'custom';
  panels: LayoutPresetPanel[];
}

export interface LayoutPreset {
  id: string;
  name: string;
  /** One sentence on what the layout is for, shown as the option's subtitle. */
  purpose: string;
  layout: { columns: LayoutPresetColumn[] };
}

/**
 * Co-Learning, User Study 2 — the layout proposed in the dispatcher review of
 * 2026-08-24 (docs/reading/2026-08-24-dispatcher-review-study2.md).
 *
 * Its point is **subtraction**: "Es braucht nicht alle Informationen, die das
 * Tool bietet." Agent Inspector, Impact, Scenario and Recommendations are all
 * absent — not because they are wrong, but because a study participant should
 * face one decision surface, not seven. What remains is the situation (left),
 * the network (centre) and the decision plus its reflection (right).
 */
const COLEARNING_STUDY2: LayoutPreset = {
  id: 'preset-colearning-study2',
  name: 'Co-Learning · User Study 2',
  purpose: 'Reduzierter Aufbau aus dem Dispatcher-Review: Lage, Streckenspiegel/ZWL, Entscheidung mit Reflexion.',
  layout: {
    columns: [
      {
        id: 'preset-s2-left',
        rowId: 'preset-s2-row',
        name: 'Lage',
        width: 22,
        role: 'sidebar',
        panels: [
          {
            id: 'preset-s2-situation',
            type: 'situation-summary',
            title: 'Situation Summary',
            expanded: true,
            collapsible: true,
            minHeight: 120,
          },
          {
            id: 'preset-s2-notifications',
            type: 'notifications',
            title: 'Notifications',
            expanded: true,
            collapsible: true,
            minHeight: 160,
          },
          {
            id: 'preset-s2-trains',
            type: 'agents',
            title: 'Züge',
            expanded: true,
            collapsible: true,
            minHeight: 200,
          },
        ],
      },
      {
        id: 'preset-s2-center',
        rowId: 'preset-s2-row',
        name: 'Netz',
        width: 50,
        role: 'main',
        panels: [
          {
            id: 'preset-s2-views',
            type: 'view-tabs',
            title: 'Streckenspiegel & ZWL',
            expanded: true,
            collapsible: false,
            minHeight: 520,
            // The review asked for the ZWL back as a peer of the network view,
            // not as a layer toggle — so both are tabs of one centre container.
            settings: { tabs: ['flatland-map', 'marey'] },
          },
        ],
      },
      {
        id: 'preset-s2-right',
        rowId: 'preset-s2-row',
        name: 'Entscheidung',
        width: 28,
        role: 'sidebar',
        panels: [
          {
            id: 'preset-s2-whatif',
            type: 'whatif-compare',
            title: 'What-if Compare',
            expanded: true,
            collapsible: true,
            minHeight: 260,
          },
          {
            id: 'preset-s2-reflection',
            type: 'co-learning-reflection',
            title: 'Reflection',
            expanded: true,
            collapsible: true,
            minHeight: 220,
          },
        ],
      },
    ],
  },
};

/**
 * Recommendation, User Study 2 — the same reduction as the Co-Learning preset,
 * asked for in the same review ("die gleichen Kommentare bezüglich Ansicht").
 *
 * Only the right-hand column differs: Recommendation's one decision surface is
 * the ranked recommendation, where Co-Learning's is the what-if plus its
 * reflection. Everything else is deliberately identical, so a study can compare
 * the two conditions without the layout itself being a variable.
 *
 * **This preset does not isolate the modes.** The cross-mode Co-Learning
 * surfaces (`co-learning-effect`, `learning-records`, the confirmed-preference
 * line) render *inside* the recommendations panel, so no layout can remove
 * them — see docs/reading/2026-08-24-dispatcher-review-study2.md §6.
 */
const RECOMMENDATION_STUDY2: LayoutPreset = {
  id: 'preset-recommendation-study2',
  name: 'Recommendation · User Study 2',
  purpose: 'Gleicher reduzierter Aufbau wie Co-Learning, rechts die Empfehlung statt What-if und Reflexion.',
  layout: {
    columns: [
      {
        id: 'preset-r2-left',
        rowId: 'preset-r2-row',
        name: 'Lage',
        width: 22,
        role: 'sidebar',
        panels: [
          {
            id: 'preset-r2-situation',
            type: 'situation-summary',
            title: 'Situation Summary',
            expanded: true,
            collapsible: true,
            minHeight: 120,
          },
          {
            id: 'preset-r2-notifications',
            type: 'notifications',
            title: 'Notifications',
            expanded: true,
            collapsible: true,
            minHeight: 160,
          },
          {
            id: 'preset-r2-trains',
            type: 'agents',
            title: 'Züge',
            expanded: true,
            collapsible: true,
            minHeight: 200,
          },
        ],
      },
      {
        id: 'preset-r2-center',
        rowId: 'preset-r2-row',
        name: 'Netz',
        width: 50,
        role: 'main',
        panels: [
          {
            id: 'preset-r2-views',
            type: 'view-tabs',
            title: 'Streckenspiegel & ZWL',
            expanded: true,
            collapsible: false,
            minHeight: 520,
            settings: { tabs: ['flatland-map', 'marey'] },
          },
        ],
      },
      {
        id: 'preset-r2-right',
        rowId: 'preset-r2-row',
        name: 'Entscheidung',
        width: 28,
        role: 'sidebar',
        panels: [
          {
            id: 'preset-r2-recommendations',
            type: 'recommendations',
            title: 'Empfehlung',
            expanded: true,
            collapsible: true,
            minHeight: 300,
          },
        ],
      },
    ],
  },
};

/**
 * Combined Actions — demo (widget E1, docs/plans/widget-e1-combined-actions.md).
 *
 * The situation and the timetable on the left, the network and the ZWL big in
 * the middle, and the coordinated actions down the right — next to the two views
 * they change. Point at an action and the map marks who is released in what
 * order while the ZWL shifts their lines in time.
 *
 * The centre is `view-tabs` rather than a bare map on purpose: an action's
 * *timing* consequence is only visible in the ZWL, its *ordering* consequence
 * only on the map, and neither alone answers the question.
 *
 * The right column is 32 %, not the 26 % it started at: below that the train
 * sequence gets under ~200 px, four chips wrap onto a second line, and the panel
 * can no longer fit its column without scrolling.
 */
const COMBINED_ACTIONS_DEMO: LayoutPreset = {
  id: 'preset-combined-actions-demo',
  name: 'Combined Actions · Demo',
  purpose: 'Lage und Fahrplan links, Netz/ZWL gross in der Mitte, rechts die kombinierten Aktionen zum Umsortieren.',
  layout: {
    columns: [
      {
        id: 'preset-ca-context',
        rowId: 'preset-ca-row',
        name: 'Lage',
        // Left and right are deliberately equal: they carry the same weight in
        // the task (what is going on ↔ what to do about it), and an asymmetric
        // pair read as an accident rather than as a hierarchy.
        width: 24,
        role: 'sidebar',
        panels: [
          {
            id: 'preset-ca-situation',
            type: 'situation-summary',
            title: 'Situation Summary',
            expanded: true,
            collapsible: true,
            minHeight: 110,
          },
          {
            id: 'preset-ca-notifications',
            type: 'notifications',
            title: 'Notifications',
            expanded: true,
            collapsible: true,
            minHeight: 140,
          },
        ],
      },
      {
        id: 'preset-ca-network',
        rowId: 'preset-ca-row',
        name: 'Netz & ZWL',
        // The centre is the widest thing on the screen by a clear margin: the
        // Streckenspiegel and the ZWL are what the operator actually reads, and
        // at 44 % both were cramped.
        width: 52,
        role: 'main',
        panels: [
          {
            id: 'preset-ca-views',
            type: 'view-tabs',
            title: 'Streckenspiegel & ZWL',
            expanded: true,
            collapsible: false,
            minHeight: 520,
            settings: { tabs: ['flatland-map', 'marey'] },
          },
          {
            // Context, not events: the timetable says what each train is
            // *supposed* to do, which is the frame you read the network view
            // against — so it belongs under it, not in the event column.
            id: 'preset-ca-timetable',
            type: 'timetable',
            title: 'Fahrplan',
            expanded: true,
            collapsible: true,
            minHeight: 180,
          },
        ],
      },
      {
        id: 'preset-ca-actions',
        rowId: 'preset-ca-row',
        name: 'Kombinierte Aktionen',
        width: 24,
        role: 'sidebar',
        panels: [
          {
            id: 'preset-ca-combined',
            type: 'combined-actions',
            title: 'Combined Actions',
            expanded: true,
            collapsible: true,
            minHeight: 420,
          },
        ],
      },
    ],
  },
};

/**
 * Combined Actions · Package variant — the second answer to the same problem.
 *
 * Roman's variant is not a different *mode*, it is a different interface to the
 * same decision, so it gets a layout rather than a fourth `InteractionMode`.
 * The reading order is its argument: what is wrong on the left, the network in
 * the middle, the one action that answers it on the right — the dispatcher
 * reads left to right, from problem to remedy, instead of meeting three options
 * before knowing what they are for.
 *
 * The left column is wider than the demo preset's 24 %: the problem overview is
 * prose-shaped, and below ~28 % its sentences wrapped every three words.
 */
const COMBINED_ACTIONS_PACKAGE: LayoutPreset = {
  id: 'preset-combined-actions-package',
  name: 'Combined Actions · Package variant',
  purpose: 'Problem links, Netz/ZWL in der Mitte, rechts ein einzelnes Aktionspaket zum Umsortieren und Bestätigen.',
  layout: {
    columns: [
      {
        id: 'preset-cap-problem',
        rowId: 'preset-cap-row',
        name: 'Problem',
        width: 28,
        role: 'sidebar',
        panels: [
          {
            id: 'preset-cap-overview',
            type: 'problem-overview',
            title: 'Problem Overview',
            expanded: true,
            collapsible: true,
            minHeight: 200,
          },
          {
            id: 'preset-cap-situation',
            type: 'situation-summary',
            title: 'Situation Summary',
            expanded: true,
            collapsible: true,
            minHeight: 110,
          },
        ],
      },
      {
        id: 'preset-cap-network',
        rowId: 'preset-cap-row',
        name: 'Netz & ZWL',
        width: 44,
        role: 'main',
        panels: [
          {
            id: 'preset-cap-views',
            type: 'view-tabs',
            title: 'Streckenspiegel & ZWL',
            expanded: true,
            collapsible: true,
            minHeight: 320,
          },
        ],
      },
      {
        id: 'preset-cap-action',
        rowId: 'preset-cap-row',
        name: 'Aktion',
        width: 28,
        role: 'sidebar',
        panels: [
          {
            id: 'preset-cap-package',
            type: 'combined-actions-package',
            title: 'Combined Actions',
            expanded: true,
            collapsible: true,
            minHeight: 420,
          },
        ],
      },
    ],
  },
};

export const LAYOUT_PRESETS: readonly LayoutPreset[] = [
  COLEARNING_STUDY2,
  RECOMMENDATION_STUDY2,
  COMBINED_ACTIONS_DEMO,
  COMBINED_ACTIONS_PACKAGE,
];
