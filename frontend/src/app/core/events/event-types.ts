export type LayerVisibility = {
  trains: boolean;
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

export interface ScenarioOption {
  id: string;
  title: string;
  description: string;
  kpiDelta: { time?: number; energy?: number };
  isRecommended?: boolean;
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
