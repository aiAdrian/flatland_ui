/**
 * Config-driven survey model. Questionnaires are defined as data (see
 * survey-configs.ts) so they can be swapped/adjusted per interaction mode or
 * study iteration without touching the renderer.
 */
export type SurveyQuestionType = 'likert' | 'scale' | 'radio' | 'text';

export interface SurveyQuestion {
  id: string;
  text: string;
  type: SurveyQuestionType;
  /** radio: choice labels. */
  options?: string[];
  /** likert/scale: numeric range (defaults likert 1..7). */
  min?: number;
  max?: number;
  /** likert/scale: anchor labels for the two ends. */
  minLabel?: string;
  maxLabel?: string;
}

export interface SurveySection {
  id: string;
  title?: string;
  description?: string;
  /** Standard instrument this section is based on, shown as a subtle tag. */
  instrument?: string;
  questions: SurveyQuestion[];
}

export interface SurveyConfig {
  id: string;
  title: string;
  description?: string;
  sections: SurveySection[];
}

export type SurveyAnswers = Record<string, string | number>;
