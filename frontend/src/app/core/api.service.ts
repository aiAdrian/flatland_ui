import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { backendHttpBase } from './backend-origin';
import {
  ActionInt,
  PlayRequest,
  PolicyGraph,
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

  /** Policy-divergence event graph: where the available policies would
   *  produce different futures, from the current state to the end of the
   *  run. CPU-heavy on the backend — cached there per (session, step). */
  policyGraph(
    id: string,
    opts: { maxNodes?: number; maxWallS?: number; horizon?: number; policies?: string[]; decisionCellsOnly?: boolean; refresh?: boolean } = {},
  ) {
    let params = new HttpParams();
    if (opts.maxNodes != null) params = params.set('max_nodes', String(opts.maxNodes));
    if (opts.maxWallS != null) params = params.set('max_wall_s', String(opts.maxWallS));
    if (opts.horizon != null) params = params.set('horizon', String(opts.horizon));
    if (opts.policies?.length) params = params.set('policies', opts.policies.join(','));
    if (opts.decisionCellsOnly != null)
      params = params.set('decision_cells_only', String(opts.decisionCellsOnly));
    if (opts.refresh) params = params.set('refresh', 'true');
    return this.http.get<PolicyGraph>(`${API_BASE}/session/${id}/hmi/policy-graph`, { params });
  }

}
