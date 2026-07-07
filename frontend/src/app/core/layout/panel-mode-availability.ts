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
  recommendations: ['recommendation'],
  'co-learning-reflection': ['co-learning'],
  'goal-achievement': ['director'],
  'director-directive': ['director'],
};

/** True if the given panel type is offered in the given interaction mode. */
export function isPanelAvailableInMode(type: string, mode: InteractionMode): boolean {
  const modes = PANEL_MODE_AVAILABILITY[type];
  return modes === undefined || modes.includes(mode);
}
