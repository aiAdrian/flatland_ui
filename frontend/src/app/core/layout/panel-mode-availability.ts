import { InteractionMode } from '../events/event-types';

/**
 * Single source of truth for which panel *types* are offered per interaction
 * mode. Mirrors docs/reference/panel-mode-matrix.md.
 *
 * Only panels that are restricted to specific modes are listed; any type not
 * present here is available in every mode ('all'). This is the availability the
 * future mode-scoped-layout resolver will read; until it exists, the hardcoded
 * default layout (AppComponent) consults it directly instead of scattering
 * `@if (store.isCoLearning())` / `aiInControl()` checks across the template.
 *
 * Behaviour per mode stays inside the panel components (read
 * `store.interactionMode()`); this map is availability only.
 */
export const PANEL_MODE_AVAILABILITY: Record<string, InteractionMode[]> = {
  // Per-conflict suggestions belong to Recommendation mode. Director's central
  // surface is the A/B/C *strategy* window (`app-strategy-options`): when the AI
  // dispatches autonomously the operator's job is to choose the objective, not
  // to accept individual dispatch alerts.
  recommendations: ['recommendation'],
  // v1 variant of the recommendations widget (docs/plans/widget-variants-versioning.md);
  // same mode availability as the default v2.
  'recommendations-classic': ['recommendation'],
  'co-learning-reflection': ['co-learning'],
  // Superseded in Director by the A/B/C strategy window. Offered in no mode
  // (empty ≠ absent), kept wired so re-enabling it is a config flip.
  'goal-achievement': [],
  'director-directive': ['director'],
  // Strategic (policy) surface. In Recommendation the `recommendations` panel is
  // the policy surface, so `scenario` would only duplicate it — hide it there.
  // Co-Learning uses it as the *neutral* compare surface (and the §3.3 what-if
  // base). Director no longer offers it: swapping the *algorithm* is a different
  // question from setting the *objective*, and mixing both on one screen was the
  // main source of "which of these actually steers the AI?".
  scenario: ['co-learning'],
  // Offered in NO mode (empty ≠ absent: absent would mean all modes). The
  // Director directive lever is `director-weights`; a second, unconnected
  // weight surface in the same mode confused more than it steered. The
  // kpiPriorities signal itself stays, at its defaults, because the
  // scenario/recommendation fetches read it in every mode. Rationale:
  // docs/reference/panel-mode-matrix.md.
  'kpi-filter': [],
  // The goal_directed planner's raw dials + plan provenance. Superseded on the
  // Director screen by the A/B/C strategy tiles, which set the same three
  // weights but say what each setting costs. Two levers for one objective made
  // it unclear which one governs. Offered in no mode (empty ≠ absent), kept
  // wired so re-enabling it is a config flip.
  'director-weights': [],
  // Per-train table: dispatcher-level detail. Director supervises objectives
  // while the AI owns individual trains, so it is noise there.
  agents: ['recommendation', 'co-learning'],
};

/** True if the given panel type is offered in the given interaction mode. */
export function isPanelAvailableInMode(type: string, mode: InteractionMode): boolean {
  const modes = PANEL_MODE_AVAILABILITY[type];
  return modes === undefined || modes.includes(mode);
}
