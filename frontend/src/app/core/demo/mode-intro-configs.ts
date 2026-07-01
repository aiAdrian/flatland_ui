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
    yourRole:
      'You stay in charge — accept the AI’s suggestion, or choose differently yourself.',
    whatYouCanControl: [
      'Accept or reject the AI’s suggested policy change',
      'Override any individual train’s next decision yourself',
      'Adjust KPI priorities (time / energy / routing) to shape what the AI considers “best”',
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
    yourRole:
      'You choose freely; every decision is recorded. Afterwards, you reflect on what you did — and get the AI’s perspective on it too.',
    whatYouCanControl: [
      'Choose freely between neutral options — nothing is ranked for you',
      'Override any individual train’s decision yourself',
      'Trigger “Reflect now” at any point during the run',
      'Adjust KPI priorities',
    ],
    watchFor: [
      'No ranking or badges on the options',
      'A “Reflect now” option becomes available as you go, and opens on its own once a decision is resolved',
    ],
    goal:
      'Same task — but the focus here is what you learn about the situation, and about working with the AI.',
  },
  {
    mode: 'director',
    wp: 'WP 3.4',
    title: 'Director',
    tagline: 'You set the goal, the AI acts.',
    whatHappens:
      'Before starting, you set a high-level directive (priorities, policy). The AI then dispatches all trains on its own.',
    yourRole:
      'Supervise via live goal-tracking; step in only if you feel you need to.',
    whatYouCanControl: [
      'Set the initial directive (KPI priorities + policy) before the run starts',
      'Re-weight KPIs or swap the policy while the AI runs',
      'Take over a single train at any time',
      'Pause the autonomous run',
    ],
    watchFor: [
      'A directive card before the run starts',
      'A live “Goal Achievement” panel once it’s running',
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
