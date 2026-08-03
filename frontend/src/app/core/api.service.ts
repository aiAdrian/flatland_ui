import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { backendHttpBase } from './backend-origin';
import {
  ActionInt,
  PlayRequest,
  PolicyInfo,
  PolicyName,
  ScenarioPoliciesConfig,
  ScenarioPreset,
  SessionInfo,
  SessionState,
  StepResponse,
} from './models';
import { AppNotification, ImpactItem, KpiPriorities, Recommendation, ScenarioOption, WhatIfResult } from './events/event-types';

/** Build the KPI query params for the scenario/recommendation endpoints. */
function kpiParams(kpi?: KpiPriorities): { [k: string]: string } {
  if (!kpi) return {};
  return {
    kpi_time: String(kpi.time),
    kpi_energy: String(kpi.energy),
    kpi_platform: String(kpi.platformRouting),
    kpi_train: String(kpi.trainRouting),
  };
}

export interface HmiBundle {
  notifications: AppNotification[];
  scenarios: ScenarioOption[];
  recommendations: Recommendation[];
}

/** The Director planner's dials (any non-negative scale; backend normalises). */
export interface DirectorWeights {
  punctuality: number;
  connections: number;
  stability: number;
}

export interface DirectorTraceOption {
  wait: number;
  to_node: number;
  clean: boolean;
  considered: boolean;
  weighted: number;
  utilities: { punctuality: number; connections: number; stability: number };
}

/** One decision of the search: where, when, the options it weighed and
 *  which one it committed. */
export interface DirectorTraceEntry {
  handle: number;
  node_id: number;
  time: number;
  chosen?: number;
  stuck?: boolean;
  options: DirectorTraceOption[];
}

/** One mid-episode re-plan: when, why, and what the residual search
 *  concluded — "research" replaced the plan, "continue" kept it (either
 *  by score or because the paired rollout gate vetoed the switch). */
export interface DirectorReplanEvent {
  step: number;
  reason: string;
  source: 'research' | 'continue';
  weighted: number;
  utilities: { punctuality: number; connections: number; stability: number };
  considered: { research: number; continue: number };
  decisions: number;
  changed: number[];
  gate?: 'rollout-pass' | 'rollout-veto';
}

/** Provenance of the plan the goal_directed policy is driving.
 *  `utilities`/`weighted`/`trace` are present when the learned models
 *  planned it; a model-free fallback carries only `source` + `weights`.
 *  `replans` accumulates the mid-episode re-planning events. */
export interface DirectorPlanInfo {
  source: string;
  weights: number[];
  weighted?: number;
  utilities?: { punctuality: number; connections: number; stability: number };
  decisions?: number;
  trace?: DirectorTraceEntry[];
  replans?: DirectorReplanEvent[];
}

/** One drawable point of a planned train path: the cell and the planned
 *  step of first entry (the map clips to the future with it). */
export interface DirectorPathPoint {
  step: number;
  row: number;
  col: number;
}

/** Per-train planned cell paths of the committed plan, keyed by handle. */
export type DirectorPlanPaths = Record<string, DirectorPathPoint[]>;

export interface DirectorState {
  session_id: string;
  weights: DirectorWeights;
  plan: DirectorPlanInfo | null;
  paths: DirectorPlanPaths | null;
}

/** Response of a weights push; `plan`/`paths` are filled when the push
 *  asked for an immediate (re-)plan. */
export interface DirectorWeightsResult {
  session_id: string;
  weights: DirectorWeights;
  replanned: boolean;
  plan: DirectorPlanInfo | null;
  paths: DirectorPlanPaths | null;
}

/** Ground truth from replaying the committed plan on a pristine fork. */
export interface DirectorVerification {
  session_id: string;
  predicted: {
    weighted: number | null;
    utilities: DirectorPlanInfo['utilities'] | null;
    source: string | null;
  };
  verified: {
    total_delay: number;
    all_arrived: boolean;
    bucket: number;
    connections_total: number;
    connections_kept: number;
    kept_ratio: number;
    safety: number;
    steps: number;
  };
}

/** One simulated branch of a what-if: the episode's remainder played to
 *  the end on a fork. Connection counts start at the fork point. */
export interface DirectorWhatIfBranch {
  total_delay: number;
  arrived: number;
  trains: number;
  all_arrived: boolean;
  steps: number;
  connections_total: number;
  connections_kept: number;
  kept_ratio: number;
}

/** Continue vs re-plan under candidate weights, both simulated from the
 *  live session's current state (the session itself is untouched). */
export interface DirectorWhatIf {
  session_id: string;
  step: number;
  weights: DirectorWeights;
  continue: DirectorWhatIfBranch;
  replan: DirectorWhatIfBranch & {
    source: 'research' | 'continue';
    changed: number[];
    predicted: {
      weighted: number;
      utilities: DirectorPlanInfo['utilities'];
      considered: { research: number; continue: number };
    };
  };
}

/** Result of a manual "re-plan now": the recorded event plus the plan
 *  info and drawable paths as they stand afterwards. */
export interface DirectorReplanResult {
  session_id: string;
  event: DirectorReplanEvent;
  plan: DirectorPlanInfo | null;
  paths: DirectorPlanPaths | null;
}

// Same-origin in production, localhost:8000 during local dev — see backend-origin.
const API_BASE = backendHttpBase();

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  createSession(opts: any = {}): Observable<SessionInfo> {
    return this.http.post<SessionInfo>(`${API_BASE}/session`, opts);
  }

  listScenarioPresets(): Observable<ScenarioPreset[]> {
    return this.http.get<ScenarioPreset[]>(`${API_BASE}/session/scenario-presets`);
  }

  getState(id: string): Observable<SessionState> {
    return this.http.get<SessionState>(`${API_BASE}/session/${id}/state`);
  }

  step(id: string, policy: PolicyName, n_steps: number = 1): Observable<StepResponse> {
    return this.http.post<StepResponse>(`${API_BASE}/session/${id}/step`, {
      policy,
      n_steps,
    });
  }

  reset(id: string): Observable<{ session_id: string; reset: boolean }> {
    return this.http.post<{ session_id: string; reset: boolean }>(
      `${API_BASE}/session/${id}/reset`,
      {},
    );
  }

  play(id: string, req: PlayRequest = {}): Observable<any> {
    return this.http.post(`${API_BASE}/session/${id}/play`, req);
  }

  pause(id: string): Observable<any> {
    return this.http.post(`${API_BASE}/session/${id}/pause`, {});
  }

  playStatus(id: string): Observable<{ session_id: string; playing: boolean }> {
    return this.http.get<any>(`${API_BASE}/session/${id}/play_status`);
  }

  setOverride(id: string, handle: number, action: ActionInt): Observable<any> {
    return this.http.post(`${API_BASE}/session/${id}/agent/${handle}/override`, {
      action,
    });
  }

  clearOverride(id: string, handle: number): Observable<any> {
    return this.http.delete(`${API_BASE}/session/${id}/agent/${handle}/override`);
  }

  // === HMI Mock-API ===

  getNotifications(id: string) {
    return this.http.get<AppNotification[]>(`${API_BASE}/session/${id}/hmi/notifications`);
  }

  getScenarios(id: string, kpi?: KpiPriorities) {
    return this.http.get<ScenarioOption[]>(`${API_BASE}/session/${id}/hmi/scenarios`, { params: kpiParams(kpi) });
  }

  getRecommendations(id: string, kpi?: KpiPriorities, guarantee = false) {
    const params = guarantee ? { ...kpiParams(kpi), guarantee: 'true' } : kpiParams(kpi);
    return this.http.get<Recommendation[]>(`${API_BASE}/session/${id}/hmi/recommendations`, { params });
  }

  getImpact(id: string) {
    return this.http.get<ImpactItem[]>(`${API_BASE}/session/${id}/hmi/impact`);
  }

  getHmiBundle(id: string) {
    return this.http.get<HmiBundle>(`${API_BASE}/session/${id}/hmi`);
  }

  listPolicies(): Observable<PolicyInfo[]> {
    return this.http.get<PolicyInfo[]>(`${API_BASE}/policies`);
  }

  setPolicy(id: string, policy: PolicyName): Observable<{ session_id: string; policy: string }> {
    return this.http.post<{ session_id: string; policy: string }>(
      `${API_BASE}/session/${id}/policy`,
      { policy },
    );
  }

  getDirectorState(id: string): Observable<DirectorState> {
    return this.http.get<DirectorState>(`${API_BASE}/session/${id}/director`);
  }

  setDirectorWeights(
    id: string,
    weights: DirectorWeights,
    plan = false,
  ): Observable<DirectorWeightsResult> {
    return this.http.post<DirectorWeightsResult>(
      `${API_BASE}/session/${id}/director/weights`,
      { ...weights, plan },
    );
  }

  verifyDirectorPlan(id: string): Observable<DirectorVerification> {
    return this.http.post<DirectorVerification>(
      `${API_BASE}/session/${id}/director/verify`,
      {},
    );
  }

  replanDirectorNow(id: string): Observable<DirectorReplanResult> {
    return this.http.post<DirectorReplanResult>(
      `${API_BASE}/session/${id}/director/replan`,
      {},
    );
  }

  whatIfDirector(id: string, weights: DirectorWeights): Observable<DirectorWhatIf> {
    return this.http.post<DirectorWhatIf>(
      `${API_BASE}/session/${id}/director/whatif`,
      weights,
    );
  }

  getScenarioPolicies(id: string): Observable<ScenarioPoliciesConfig> {
    return this.http.get<ScenarioPoliciesConfig>(`${API_BASE}/session/${id}/scenario-policies`);
  }

  setScenarioPolicies(
    id: string,
    enabled_ids: string[],
    enabled_policy_ids?: string[],
  ): Observable<ScenarioPoliciesConfig> {
    return this.http.post<ScenarioPoliciesConfig>(`${API_BASE}/session/${id}/scenario-policies`, {
      enabled_ids,
      enabled_policy_ids,
    });
  }
  getMareyData(sessionId: string) {
    return this.http.get<any>(`${API_BASE}/session/${sessionId}/hmi/marey-data`);
  }

  /** Read-only Co-Learning feedback: forward-simulate a proposed override
   *  (handle → action int) against the current course, without committing. */
  whatIfOverride(id: string, overrides: Record<number, ActionInt>) {
    return this.http.post<WhatIfResult>(
      `${API_BASE}/session/${id}/what-if-override`,
      { overrides },
    );
  }

}
