import { InteractionMode } from '../events/event-types';
import { SurveyConfig, SurveySection } from './survey.types';

/**
 * Post-session survey building blocks. These are editable presets — adjust the
 * questions/scales here (or add mode-specific sections) without touching the
 * renderer. Standard instruments are included in a compact, study-credible form;
 * swap in the validated AI4REALNET/hmisurveys versions later if needed.
 */

// NASA-TLX (workload), 0..100 scales.
const NASA_TLX: SurveySection = {
  id: 'nasa-tlx',
  title: 'Workload',
  instrument: 'NASA-TLX',
  questions: [
    { id: 'tlx_mental', text: 'Mental demand — how mentally demanding was the task?', type: 'scale', min: 0, max: 100, minLabel: 'Very low', maxLabel: 'Very high' },
    { id: 'tlx_temporal', text: 'Temporal demand — how hurried or rushed was the pace?', type: 'scale', min: 0, max: 100, minLabel: 'Very low', maxLabel: 'Very high' },
    { id: 'tlx_performance', text: 'Performance — how successful were you?', type: 'scale', min: 0, max: 100, minLabel: 'Perfect', maxLabel: 'Failure' },
    { id: 'tlx_effort', text: 'Effort — how hard did you have to work?', type: 'scale', min: 0, max: 100, minLabel: 'Very low', maxLabel: 'Very high' },
    { id: 'tlx_frustration', text: 'Frustration — how stressed or annoyed were you?', type: 'scale', min: 0, max: 100, minLabel: 'Very low', maxLabel: 'Very high' },
  ],
};

// Trust in Automation (Jian et al.), 7-point Likert.
const TRUST: SurveySection = {
  id: 'trust',
  title: 'Trust in the AI',
  instrument: 'Trust in Automation',
  questions: [
    { id: 'trust_reliable', text: 'The AI was reliable.', type: 'likert', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree' },
    { id: 'trust_predictable', text: 'The AI behaved predictably.', type: 'likert', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree' },
    { id: 'trust_confident', text: 'I was confident relying on the AI.', type: 'likert', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree' },
  ],
};

// UEQ-S (user experience short), 7-point semantic differential.
const UEQ_S: SurveySection = {
  id: 'ueq-s',
  title: 'User experience',
  instrument: 'UEQ-S',
  questions: [
    { id: 'ueq_support', text: 'Overall, the interface was…', type: 'likert', min: 1, max: 7, minLabel: 'Obstructive', maxLabel: 'Supportive' },
    { id: 'ueq_easy', text: 'Overall, the interface was…', type: 'likert', min: 1, max: 7, minLabel: 'Complicated', maxLabel: 'Easy' },
    { id: 'ueq_clear', text: 'Overall, the interface was…', type: 'likert', min: 1, max: 7, minLabel: 'Confusing', maxLabel: 'Clear' },
  ],
};

const OPEN: SurveySection = {
  id: 'open',
  title: 'Open feedback',
  questions: [
    { id: 'open_best', text: 'What worked best in this mode?', type: 'text' },
    { id: 'open_worst', text: 'What was hardest or most frustrating?', type: 'text' },
  ],
};

// Mode-specific extra section.
function modeSection(mode: InteractionMode): SurveySection {
  switch (mode) {
    case 'recommendation':
      return {
        id: 'mode-rec',
        title: 'Recommendations',
        questions: [
          { id: 'rec_useful', text: 'The AI recommendations were useful.', type: 'likert', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree' },
          { id: 'rec_followed', text: 'I tended to follow the AI recommendation.', type: 'likert', min: 1, max: 7, minLabel: 'Never', maxLabel: 'Always' },
        ],
      };
    case 'co-learning':
      return {
        id: 'mode-col',
        title: 'Co-Learning',
        questions: [
          { id: 'col_learned', text: 'Working with the AI helped me understand the situation better.', type: 'likert', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree' },
          { id: 'col_reflect', text: 'The reflection prompts were valuable.', type: 'likert', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree' },
        ],
      };
    case 'director':
      return {
        id: 'mode-dir',
        title: 'Director',
        questions: [
          { id: 'dir_control', text: 'I felt in control even though the AI ran autonomously.', type: 'likert', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree' },
          { id: 'dir_aware', text: 'I always knew what the system was doing and why.', type: 'likert', min: 1, max: 7, minLabel: 'Strongly disagree', maxLabel: 'Strongly agree' },
        ],
      };
  }
}

const MODE_LABEL: Record<InteractionMode, string> = {
  recommendation: 'Recommendation',
  'co-learning': 'Co-Learning',
  director: 'Director',
};

/**
 * Toggleable survey building blocks, selectable in Settings. The order here is
 * the order they appear in the questionnaire.
 */
export interface SurveyPart {
  id: string;
  label: string;
}
export const SURVEY_PARTS: SurveyPart[] = [
  { id: 'mode', label: 'Mode-specific questions' },
  { id: 'nasa-tlx', label: 'Workload (NASA-TLX)' },
  { id: 'trust', label: 'Trust in the AI' },
  { id: 'ueq-s', label: 'User experience (UEQ-S)' },
  { id: 'open', label: 'Open feedback' },
];
export const DEFAULT_SURVEY_PARTS = SURVEY_PARTS.map((p) => p.id);

/**
 * Post-session survey for a given interaction mode, including only the survey
 * parts enabled in Settings (defaults to all).
 */
export function postSessionSurvey(
  mode: InteractionMode,
  enabledParts: string[] = DEFAULT_SURVEY_PARTS,
): SurveyConfig {
  const byPart: { part: string; section: SurveySection }[] = [
    { part: 'mode', section: modeSection(mode) },
    { part: 'nasa-tlx', section: NASA_TLX },
    { part: 'trust', section: TRUST },
    { part: 'ueq-s', section: UEQ_S },
    { part: 'open', section: OPEN },
  ];
  return {
    id: `post-session-${mode}`,
    title: `Post-session survey — ${MODE_LABEL[mode]}`,
    description: 'Please answer based on the run you just completed.',
    sections: byPart.filter((x) => enabledParts.includes(x.part)).map((x) => x.section),
  };
}
