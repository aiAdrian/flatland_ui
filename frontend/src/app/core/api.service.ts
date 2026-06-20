import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  ActionInt,
  PlayRequest,
  PolicyInfo,
  PolicyName,
  ScenarioPoliciesConfig,
  SessionInfo,
  SessionState,
  StepResponse,
} from './models';
import { AppNotification, Recommendation, ScenarioOption } from './events/event-types';

export interface HmiBundle {
  notifications: AppNotification[];
  scenarios: ScenarioOption[];
  recommendations: Recommendation[];
}

const API_BASE = 'http://localhost:8000';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  createSession(opts: any = {}): Observable<SessionInfo> {
    return this.http.post<SessionInfo>(`${API_BASE}/session`, opts);
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

  getScenarios(id: string) {
    return this.http.get<ScenarioOption[]>(`${API_BASE}/session/${id}/hmi/scenarios`);
  }

  getRecommendations(id: string) {
    return this.http.get<Recommendation[]>(`${API_BASE}/session/${id}/hmi/recommendations`);
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

}
