export type LayerVisibility = {
  grid: boolean;
  nextDecisions: boolean;
  agentTrajectory: boolean;
  trajectoryCellInfo: boolean;
  switches: boolean;
  signals: boolean;
  /** Neutral station markers (icon + shared label) at every stop used by the
   *  trains. Same labels are referenced by the timetable tile so map and
   *  schedule can be cross-read. */
  stations: boolean;
};

export type KpiPriorities = {
  time: number;
  energy: number;
  platformRouting: number;
  trainRouting: number;
};

/** Normalised KPI weights (each in [0,1], summing to 1). Derived from the
 *  raw KpiPriorities sliders. This is the value consumers should read so the
 *  KPI filter has a single, well-defined effect surface. */
export type KpiWeights = KpiPriorities;

/**
 * Human-AI collaboration mode the operator is currently working in.
 * Maps to the AI4REALNET work packages:
 *  - 'recommendation' = WP 3.1 (AI suggests, human decides)
 *  - 'co-learning'    = WP 3.3 (human and AI adapt to each other)
 *  - 'director'       = WP 3.4 (AI acts autonomously on high-level directives)
 */
export type InteractionMode = 'recommendation' | 'co-learning' | 'director';

export type NotificationKind = 'info' | 'warning' | 'error';

export interface AppNotification {
  id: string;
  kind: NotificationKind;
  title: string;
  message: string;
  timestamp: number;
  relatedElement?: { kind: 'train' | 'switch' | 'signal'; id: string };
}

export interface ScenarioKpis {
  totalDelay: number;
  deadlocks: number;
  done: number;
  meanDelay: number;
  /** How many steps the branch ran (until all_done or horizon). */
  episodeSteps: number;
  /** True if all agents reached their target; false if horizon hit. */
  episodeFinished: boolean;
}

export interface TrajectoryPoint {
  step: number;
  row: number;
  col: number;
  /** 0=N, 1=E, 2=S, 3=W */
  dir: number;

  /** Optional backend-enriched Marey/topology metadata. */
  handle?: number | null;
  agent_id?: number | null;
  marey_topology?: 'straight' | 'switch' | 'merge' | 'switch_merge' | 'diamond' | 'unknown' | string | null;
  marey_svg?: string | null;
  marey_debug?: Record<string, unknown> | null;
  marey_switch?: {
    taken?: number | null;
    not_taken?: number[];
    possible_exits?: number[];
    [key: string]: unknown;
  } | null;
  marey_merge?: {
    arrived_from?: number | null;
    other_inputs?: number[];
    possible_inputs?: number[];
    [key: string]: unknown;
  } | null;
}

export interface ScenarioOption {
  id: string;
  title: string;
  description: string;
  /** Per-agent trajectories over the simulated horizon. Keys are
   *  string-encoded handle ids (JSON-friendly). Used by the Marey
   *  chart to draw lines per agent per branch. */
  trajectories?: { [handle: string]: TrajectoryPoint[] };
  /** Legacy fields kept for backward compat with mock data. */
  kpiDelta: { time?: number; energy?: number };
  /** Real KPIs (filled by adapter when scenario is real). Optional
   *  because the mock fallback doesn't populate them. */
  kpis?: ScenarioKpis;
  /** Deltas relative to baseline; positive means worse for delay/deadlocks,
   *  positive means better for done. Only meaningful for non-baseline. */
  kpiDeltas?: ScenarioKpis;
  isRecommended?: boolean;
  /** True for the currently active policy's scenario. */
  isBaseline?: boolean;
  /** Score in roughly [-1, 1]; higher is better. */
  score?: number;
  /** "recommended" | "avoid" | undefined */
  tag?: string;
}

export interface Recommendation {
  id: string;
  title: string;
  description: string;
  confidence: number;
  countdownSeconds: number;
  scenarioId?: string;
}

/** One tactical option for an affected train. */
export interface ImpactOption {
  action: 'hold' | 'reroute' | 'proceed';
  label: string;
  available: boolean;
  recommended: boolean;
}

/** Forward-sim feedback on a proposed override (Co-Learning reciprocity). */
export interface WhatIfKpis {
  deadlocks: number;
  done: number;
  total: number;
  delay: number;
}

/** The selected train's own fate on one branch (primary what-if content). */
export interface WhatIfTrainSide {
  arrived: boolean;
  delay: number;
  deadlocked: boolean;
}
export interface WhatIfTrainOutcome {
  handle: number;
  baseline: WhatIfTrainSide; // AI course
  branch: WhatIfTrainSide;   // human-influenced ("My plan")
}

/** One forecast point of a per-agent branch trajectory (scenario shape). */
export interface WhatIfTrajectoryPoint {
  step: number;
  row: number;
  col: number;
}
/** Per-agent trajectories keyed by handle (string) — same shape scenarios use. */
export type WhatIfTrajById = Record<string, WhatIfTrajectoryPoint[]>;

export interface WhatIfResult {
  horizon: number;
  baseline: WhatIfKpis;
  branch: WhatIfKpis;
  delta: { delay: number; deadlocks: number; done: number };
  summary: string;
  /** The operator's selected train: its own outcome on both branches. */
  train?: WhatIfTrainOutcome | null;
  /** Per-agent forecast paths for BOTH branches, so the map can draw
   *  blue (human = branch) vs yellow (AI = baseline). Scenario shape. */
  baseline_trajectories?: WhatIfTrajById;
  branch_trajectories?: WhatIfTrajById;
  /** Handles the override applies to (the affected trains to draw). */
  handles?: number[];
}

/** One affected train from the Phase-1 impact analysis (malfunction fallout). */
export interface ImpactItem {
  handle: number;
  blocked_by: number;
  blocked_cell: [number, number];
  eta_steps: number;
  clears_in_steps: number;
  can_reroute: boolean;
  /** Override action that takes the alternative branch at the next switch
   *  (RailEnvActions: LEFT=1, FORWARD=2, RIGHT=3); null if no reroute exists. */
  reroute_action?: number | null;
  /** Cell of the switch where the reroute override applies, for context. */
  reroute_cell?: [number, number] | null;
  recommended_action: 'reroute' | 'hold';
  options?: ImpactOption[];
  severity: 'high' | 'medium';
}

export type AppEvent =
  | { type: 'SIMULATION_TIME_CHANGED'; time: number }
  | { type: 'FOCUS_INFRASTRUCTURE_ELEMENT'; kind: 'switch' | 'signal' | 'train'; id: string }
  | { type: 'KPI_FILTER_CHANGED'; priorities: KpiPriorities }
  | { type: 'SCENARIO_CONFIRMED'; scenarioId: string }
  | { type: 'SCENARIO_SIMULATED'; scenarioId: string }
  | { type: 'LAYER_VISIBILITY_CHANGED'; layers: LayerVisibility }
  | { type: 'NOTIFICATION_RAISED'; notification: AppNotification }
  | { type: 'NOTIFICATION_DISMISSED'; notificationId: string }
  | { type: 'RECOMMENDATION_FEEDBACK'; recId: string; thumbsUp: boolean }
  | { type: 'RECOMMENDATION_ACCEPTED'; recId: string };

export type AppEventType = AppEvent['type'];
