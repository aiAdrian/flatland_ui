export type LayerVisibility = {
  grid: boolean;
  nextDecisions: boolean;
  switches: boolean;
  signals: boolean;
};

export type KpiPriorities = {
  time: number;
  energy: number;
  platformRouting: number;
  trainRouting: number;
};

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
