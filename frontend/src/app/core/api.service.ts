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

/** One line of the autonomous planner's activity feed. */
export interface DirectorActivityEntry {
  kind: 'decision' | 'replan';
  /** Simulation step. For a decision this is the *planned* moment. */
  step: number;
  // decision
  handle?: number;
  stuck?: boolean;
  wait?: number | null;
  toNode?: number | null;
  optionCount?: number;
  score?: number | null;
  // replan
  reason?: string | null;
  /** 'research' = the plan was replaced, 'continue' = it was kept. */
  verdict?: string | null;
  gate?: string | null;
  changed?: number;
  scoreResearch?: number | null;
  scoreContinue?: number | null;
}

/** What the planner did and what it is about to do. Split deliberately: the
 *  plan trace holds *planned* decision times, so entries beyond the current step
 *  have not happened yet. */
export interface DirectorActivity {
  session_id: string;
  step: number;
  source: string | null;
  totalDecisions: number;
  totalReplans: number;
  /** Own channel: re-plans are rare and are the most informative events of a
   *  run, so they must not compete for slots with routine decisions. */
  replans: DirectorActivityEntry[];
  recent: DirectorActivityEntry[];
  upcoming: DirectorActivityEntry[];
}

/** The axis a strategy focus optimises for. */
export type DirectorFocus = 'punctuality' | 'connections' | 'stability';

/** One strategy focus offered as an A/B/C tile: the dial preset, plus — when
 *  the planner could answer — the plan it would commit under those dials and
 *  the drawable reroute that plan produces. `plan`/`paths` are null when the
 *  session has not planned yet or no models are installed. */
export interface DirectorStrategy {
  id: string;
  ident: string;
  focus: DirectorFocus;
  weights: DirectorWeights;
  plan: {
    source: string;
    weighted: number;
    utilities: { punctuality: number; connections: number; stability: number };
    /** Display figures. `utilities.connections` is a geometric mean with veto
     *  semantics and `utilities.stability` a product of four sub-scores, so both
     *  sit near 0 in any busy scenario — correct for ranking, unreadable on a
     *  card. The backend calls these "the number to report". */
    reported?: DirectorReportedFigures | null;
    changed: number[];
    /** The planner's own comparison behind `source`: at step 0 the portfolio
     *  (`search` / `lines` / `avoidance`), mid-episode `research` / `continue`.
     *  Lets the UI say when a focus's plan is really the conflict-blind
     *  baseline, instead of presenting it as a searched answer. */
    considered?: Record<string, number> | null;
  } | null;
  paths: DirectorPlanPaths | null;
  /** Only what this option changes — what the map actually draws. */
  divergence?: DirectorDivergence | null;
}

/**
 * What an option changes against the plan that is driving — the minimal overlay.
 *
 * Drawing full planned routes was unusable: nearly every train gets re-planned,
 * and the deviating stretches measured 19–96 cells, so the map filled with long
 * near-identical dashed lines. This carries only the difference: one branch point
 * per rerouted train (what the map marks by default), its deviating stretch (drawn
 * only on demand), and the places where a train waits instead of rerouting.
 */
export interface DirectorDivergence {
  reroutes: Record<
    string,
    { branch: { row: number; col: number; step: number }; points: DirectorPathPoint[] }
  >;
  holds: Array<{ handle: number; row: number; col: number; steps: number }>;
}

/** Operator-readable counterparts of the raw utilities. */
export interface DirectorReportedFigures {
  /** Plain share of planned transfers that hold (0..1). */
  keptRatio: number | null;
  /** How many transfers the scenario has at all. */
  connectionCount: number;
  /** The four factors whose product is the stability utility. */
  safety: {
    slack: number | null;
    deadlock: number | null;
    track: number | null;
    cascade: number | null;
  };
}

/** Response of the strategy-tiles endpoint. `available: false` carries a
 *  `reason` and preset-only tiles — the UI then offers the focuses as pure
 *  directives instead of pretending to have numbers. */
export interface DirectorStrategies {
  session_id: string;
  step: number;
  available: boolean;
  reason: string | null;
  /** The plan currently driving, so a focus can be read as a difference to it. */
  current: {
    source: string | null;
    weighted: number | null;
    utilities: { punctuality: number; connections: number; stability: number };
    reported?: DirectorReportedFigures | null;
  } | null;
  strategies: DirectorStrategy[];
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

  /** The planner's activity feed. Cheap by design (~1 KB) so it can be polled;
   *  reading `/director` for the same information transfers the full trace with
   *  every weighed option, measured at 172 KB for a 64-decision episode. */
  getDirectorActivity(id: string, limit = 6): Observable<DirectorActivity> {
    return this.http.get<DirectorActivity>(
      `${API_BASE}/session/${id}/director/activity`,
      { params: { limit } },
    );
  }

  /** Plan the remainder under each strategy focus (A/B/C tiles). Slow by
   *  nature — three residual plans — so callers trigger it explicitly and
   *  cache the answer per step rather than polling it. */
  getDirectorStrategies(id: string): Observable<DirectorStrategies> {
    return this.http.get<DirectorStrategies>(
      `${API_BASE}/session/${id}/director/strategies`,
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
