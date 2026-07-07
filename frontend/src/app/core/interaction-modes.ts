import { InteractionMode } from './events/event-types';

export interface InteractionModeInfo {
  id: InteractionMode;
  label: string;
  /** Work package the mode maps to (AI4REALNET). */
  wp: string;
  /** One-line description, shown in the mode switcher and Help/About. */
  description: string;
}

/**
 * Single source of truth for the three human-AI collaboration modes. Consumed by
 * the header mode switcher (app.component) and the Help/About overlay so their
 * wording can never drift apart. Keep the descriptions short — they render as a
 * dropdown subtitle and as a help bullet.
 */
export const INTERACTION_MODES: InteractionModeInfo[] = [
  { id: 'recommendation', label: 'Recommendation', wp: 'WP 3.1', description: 'The AI suggests a ranked option; you decide.' },
  { id: 'co-learning', label: 'Co-Learning', wp: 'WP 3.3', description: 'The AI offers neutral options; you decide and reflect.' },
  { id: 'director', label: 'Director', wp: 'WP 3.4', description: 'The AI runs autonomously on your directives; you supervise.' },
];
