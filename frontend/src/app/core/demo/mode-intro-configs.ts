import { InteractionMode } from '../events/event-types';

/**
 * Content for the guided-demo mode-intro screen: shown before the human starts
 * each mode's scenario, so they understand the mode before acting in it.
 *
 * This is deliberately data-driven (not hardcoded template branches) — it is
 * the seam a future "Experiment Designer" would write to, the same way
 * survey-configs.ts is editable content today. Swap/extend this array to
 * define new or reworded modes without touching the rendering component.
 */
export interface ModeIntro {
  mode: InteractionMode;
  wp: string;
  title: string;
  tagline: string;
  whatHappens: string;
  /** Where the operator should look in this mode — the primary view/surface.
   *  Grounded in the mode↔presentation design (docs/plans/center-view-tabs.md). */
  focusView: string;
  yourRole: string;
  whatYouCanControl: string[];
  watchFor: string[];
  goal: string;
}

export const MODE_INTROS: ModeIntro[] = [
  {
    mode: 'recommendation',
    wp: 'WP 3.1',
    title: 'Recommendation',
    tagline: 'AI suggests, you decide.',
    whatHappens:
      'As trains run, the AI watches for conflicts. When one appears, it proposes a preferred solution with a confidence score.',
    focusView:
      'The map — you act on each conflict where it happens; the recommendation card on the right is the AI’s suggested fix.',
    yourRole:
      'You stay in charge — accept the AI’s suggestion, or choose differently yourself.',
    whatYouCanControl: [
      'Accept or reject the AI’s suggested policy change',
      'Override any individual train’s next decision yourself',
      // Removed 2026-09-13: "Adjust KPI priorities (time / energy / routing)".
      // `kpi-filter` is offered in no mode (panel-mode-availability.ts) and
      // kpiPriorities sits at its defaults, so the screen never showed the dial
      // this line promised.
    ],
    watchFor: [
      'A recommendation card on the right, with a confidence % and countdown',
      'Policies ranked with “Recommended” / “Avoid” badges',
    ],
    goal: 'Get all trains to their destination with as little delay as possible.',
  },
  {
    mode: 'co-learning',
    wp: 'WP 3.3',
    title: 'Co-Learning',
    tagline: 'Neutral options, you decide and reflect.',
    whatHappens:
      'Same kind of situation — but this time the AI doesn’t push a favorite. It lays out the options neutrally.',
    focusView:
      'The map — compare your own action (blue) against the AI’s plan (yellow) right where the trains run; the what-if compare on the right deepens it. Reflection opens separately when you’re ready.',
    yourRole:
      'You choose freely; every decision is recorded. Afterwards, you reflect on what you did — and get the AI’s perspective on it too.',
    whatYouCanControl: [
      'Choose freely between neutral options — nothing is ranked for you',
      'Override any individual train’s decision yourself',
      'Trigger “Reflect now” at any point during the run',
      // Removed 2026-09-13, same reason as in Recommendation: no KPI dial is
      // offered in any mode.
    ],
    watchFor: [
      'No ranking or badges on the options',
      'A “Reflect now” option becomes available as you go, and opens on its own once a decision is resolved',
    ],
    goal:
      'Same task — but the focus here is what you learn about the situation, and about working with the AI.',
  },
  {
    // Rewritten 2026-09-13 against what the Director screen actually renders.
    // Every line here was checked in a running session: the panels present, the
    // controls that exist, the wording the tiles use. The previous copy pointed
    // at a "Goal Achievement dashboard" that is offered in no mode, promised KPI
    // re-weighting that no surface exposes, and promised taking over a single
    // train — which Director cannot do at all: no agent inspector, no trains
    // roster, and the impact panel suppresses its per-decision hooks there.
    // That last one is a real gap in adjustable autonomy, not a copy problem;
    // it is the autonomy dial in docs/plans/mode-layouts-three-zones.md §6.
    mode: 'director',
    wp: 'WP 3.4',
    title: 'Director',
    tagline: 'You set the goal, the AI acts.',
    whatHappens:
      'You choose which objective the plan should pursue. The AI then dispatches every train on its own and re-plans as the situation changes.',
    focusView:
      'The three strategy tiles above the map. “Auf Karte” draws the chosen plan onto the map as dashed routes, so you see what an objective changes before committing it.',
    yourRole:
      'Supervise the objective, not the trains. You steer by changing what the plan optimises for.',
    whatYouCanControl: [
      'Choose the objective: delay, connections, or stability',
      'Preview it on the map, and replay it, before committing',
      'Swap the dispatching policy in the toolbar',
      'Pause, resume, or end the shift',
    ],
    watchFor: [
      'The AI-activity feed: what the planner decided, and when it re-planned',
      'The forecast: what the objective gives, and what it costs',
      'Dashed look-ahead routes on the map after a preview',
    ],
    goal:
      'See how well the AI performs autonomously — and notice where you feel the pull to intervene.',
  },
];

export function modeIntroFor(mode: InteractionMode): ModeIntro {
  const found = MODE_INTROS.find((m) => m.mode === mode);
  if (!found) throw new Error(`No mode-intro content for mode "${mode}"`);
  return found;
}
