/**
 * Precomputed sandbox outcomes for step 8 (Event Simulation) of the
 * Co-learning Monte Carlo Interviews tour. The values live in
 * `sandbox-outcomes.generated.ts`, written by
 * `backend/scripts/generate_sandbox_outcomes.py` with the real simulator.
 *
 * Texts name trains as `{T<handle>}`; the HMI fills in the shared train name.
 */

export interface SandboxTrainOutcome {
  handle: number;
  arrived: boolean;
  arrivalStep: number | null;
  /** Steps later than in the undisturbed run of the same plan; null when the train did not arrive. */
  delayVsPlan: number | null;
}

export interface SandboxVariant {
  id: string;
  label: string;
  description: string;
  /** The Impact option this variant corresponds to, to mark the interviewee's own choice. */
  matchesAction: 'hold' | 'proceed' | 'reroute' | null;
  arrived: number;
  total: number;
  /** Summed delay against the undisturbed run, over the trains that arrived. */
  totalDelayVsPlan: number;
  trains: SandboxTrainOutcome[];
}

export interface SandboxCase {
  id: string;
  kind: 'experienced' | 'novel';
  title: string;
  situation: string;
  /** Train the decision is about, as named by the impact analysis. */
  decisionHandle: number;
  /** Step at which the impact analysis first lists that train. */
  decisionStep: number;
  variants: SandboxVariant[];
}

export interface SandboxOutcomes {
  scenario: string;
  generator: string;
  generatedOn: string;
  /** Arrival step per train handle in the undisturbed run — the reference for `delayVsPlan`. */
  planArrivalSteps: Record<string, number>;
  cases: SandboxCase[];
}
