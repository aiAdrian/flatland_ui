import { InteractionMode } from '../events/event-types';

/**
 * Tours — the guided walks, as data.
 *
 * Until now a tour was hardcoded in three unconnected places: the mode sequence
 * in `SessionStore.demoSequence`, the intro copy in `MODE_INTROS`, and the
 * environment in `AppComponent.guidedDemoEnvOpts()`. The "Director Demo" button
 * was a fourth, degenerate copy of the same idea. Adding a layout variant meant
 * editing code in all of them.
 *
 * A tour pins everything: which modes, in which order, in which layout, on which
 * environment, with or without the survey. That is what makes it the simplest
 * entry point on the start screen — there is nothing left to configure, so the
 * person chooses one thing and presses start.
 *
 * This is the first slice of the `Tour` entity in
 * docs/plans/scenario-infrastructure-gallery.md §4.6. Deliberately *not* here
 * yet: the `setupId` reference (Setups do not exist), the per-mode event re-draw
 * (the event budget is unbuilt), and `Experiment` (§4.7 — a different entity,
 * not a flag on this one).
 */
export interface Tour {
  id: string;
  /** Shown in the picker. */
  name: string;
  /** One sentence: what this tour shows, and what it costs in minutes. */
  description: string;
  /** The modes, in order. One entry is a legitimate tour, not a special case. */
  modes: InteractionMode[];
  /**
   * Which layout the tour runs in. `'system'` is the hardcoded default layout;
   * anything else is a preset id. This is the field that makes "the same tour in
   * the old and in the new layout" a choice instead of a code change.
   */
  layout: 'system' | string;
  /** Which environment, by the id the Infrastructure picker uses. */
  infrastructureId: string;
  /** Whether each mode ends with the post-session survey. */
  surveyAfterEachMode: boolean;
  /** Rough wall-clock budget, so a facilitator can plan. */
  expectedMinutes: number;
}

export const TOURS: Tour[] = [
  {
    id: 'three-modes-original',
    name: 'Three modes · original layout',
    description:
      'The same conflict handled in all three modes — Recommendation, Co-Learning, Director — in the hardcoded default layout, with a short survey after each.',
    modes: ['recommendation', 'co-learning', 'director'],
    layout: 'system',
    infrastructureId: 'guided-demo',
    surveyAfterEachMode: true,
    expectedMinutes: 20,
  },
  {
    id: 'two-modes-guide-light',
    name: 'Two modes · Guide Mode Light',
    description:
      'Recommendation and Co-Learning in the three-zone layout: left reports, centre shows the network, right decides. Same environment as the original tour, so the layout is the only difference.',
    modes: ['recommendation', 'co-learning'],
    // Deliberately without Director. A preset layout renders through the generic
    // panel grid, and the Director surfaces — the directive bar, the A/B/C tiles
    // above the map, the forecast's four columns, the shift-review takeover —
    // live only in the hardcoded layout (docs/plans/layout-grid-model-plan.md
    // §2b). A third leg here would show a degraded Director and teach the wrong
    // thing about the mode. It returns once the mode-scoped resolver lands
    // (docs/plans/mode-layouts-three-zones.md P1).
    layout: 'preset-guide-mode-light',
    infrastructureId: 'guided-demo',
    surveyAfterEachMode: true,
    expectedMinutes: 14,
  },
  {
    id: 'director-only',
    name: 'Director only',
    description:
      'Straight into the Director screen — strategy tiles, forecast, AI-activity feed — with no walk and no survey. For showing that screen on its own.',
    modes: ['director'],
    layout: 'system',
    infrastructureId: 'guided-demo',
    surveyAfterEachMode: false,
    expectedMinutes: 6,
  },
];

export function tourById(id: string): Tour | undefined {
  return TOURS.find((t) => t.id === id);
}
