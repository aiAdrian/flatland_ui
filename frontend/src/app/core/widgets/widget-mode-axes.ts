import { InteractionMode } from '../events/event-types';
import { WidgetMeta } from './widget-catalog';

/**
 * Mode presentation adapter for the Widget Gallery — the seam for the planned
 * two-axis split.
 *
 * ## Why this file exists
 *
 * `InteractionMode` currently carries two independent things at once:
 *
 *   A. **Autonomy level** — who owns Monitoring / Generating / Selecting /
 *      Implementing (Timpe & Kolrep 2002; Parasuraman, Sheridan & Wickens 2000).
 *   B. **Collaboration goal** — what the interaction is *for*: get this decision
 *      right now, or learn about each other (calibrated trust).
 *
 * On axis A, `recommendation` and `co-learning` barely differ — both leave
 * Selecting with the human and Implementing with the system (level 5 in the
 * Timpe/Weyer taxonomy). Their real difference — neutral options, reflection,
 * what-if compare — is axis B, carried on the wrong axis. Conversely
 * "supervised **and** co-learning" cannot be expressed today at all, although a
 * supervisor override in Director is a *stronger* learning signal than a click
 * in Recommendation.
 *
 * The intended resolution keeps `InteractionMode` as a **named preset** over the
 * two axes rather than as the primitive (so the CLAUDE.md guardrail holds — no
 * parallel flag). Experiments consume the presets (fixed, comparable
 * conditions); a prototype consumes the axes (free movement = adjustable
 * autonomy). See `docs/reference/interaction-framework.md` §3, which already
 * models `allocation` as its own concept for exactly this reason.
 *
 * ## What this file does today
 *
 * Nothing semantic. `MODE_PRESETS` documents the mapping; `modeRowsFor()` is the
 * single place the gallery asks "how does this widget behave per mode". When the
 * split lands, this function changes and the gallery's template does not.
 */

/** Axis A — who owns which loop stage. Ordered from most to least human control. */
export type AutonomyLevel = 'advisory' | 'supervised' | 'autonomous';

/** Axis B — what the interaction is designed to achieve. */
export type CollaborationGoal = 'perform' | 'co-learn';

/** The three experiment conditions, resolved onto the two axes. Read-only
 *  documentation today — nothing branches on it yet. */
export const MODE_PRESETS: Record<
  InteractionMode,
  { autonomyLevel: AutonomyLevel; collaborationGoal: CollaborationGoal; wp: string; label: string }
> = {
  recommendation: {
    autonomyLevel: 'advisory',
    collaborationGoal: 'perform',
    wp: 'WP 3.1',
    label: 'Recommendation',
  },
  'co-learning': {
    autonomyLevel: 'advisory',
    collaborationGoal: 'co-learn',
    wp: 'WP 3.3',
    label: 'Co-Learning',
  },
  director: {
    autonomyLevel: 'autonomous',
    collaborationGoal: 'perform',
    wp: 'WP 3.4',
    label: 'Director',
  },
};

export const MODE_ORDER: InteractionMode[] = ['recommendation', 'co-learning', 'director'];

/** One rendered row in a widget's per-mode block. */
export interface ModeRow {
  id: InteractionMode;
  label: string;
  /** Secondary label under the name — the work package today, an axis pair later. */
  sublabel: string;
  /** Behaviour sentence, or null when the widget is not offered in that mode. */
  body: string | null;
}

/** True when the widget behaves identically in every mode — then the gallery
 *  collapses three identical sentences into one line instead of repeating them.
 *  (66 such rows exist across the catalog today.) */
export function sameInAllModes(widget: WidgetMeta): boolean {
  const bodies = MODE_ORDER.map((m) => widget.perMode[m]);
  return bodies.every((b) => b !== null && b === bodies[0]);
}

/** The per-mode rows for one widget. The gallery's only entry point into mode
 *  semantics — see the file header for why that matters. */
export function modeRowsFor(widget: WidgetMeta): ModeRow[] {
  return MODE_ORDER.map((id) => ({
    id,
    label: MODE_PRESETS[id].label,
    sublabel: MODE_PRESETS[id].wp,
    body: widget.perMode[id],
  }));
}
