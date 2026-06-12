import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { ApiService } from './api.service';
import {
  AppNotification,
  KpiPriorities,
  LayerVisibility,
  Recommendation,
  ScenarioOption,
} from './events/event-types';
import { WebSocketService } from './websocket.service';
import { AgentDTO, PolicyInfo, PolicyName, RailTile, SessionInfo, SessionState } from './models';

export interface TrajectoryPoint {
  step: number;
  position: [number, number] | null;
  direction: number | null;
  state: string;
}

@Injectable({ providedIn: 'root' })
export class SessionStore {
  private api = inject(ApiService);
  private ws = inject(WebSocketService);

  readonly session = signal<SessionInfo | null>(null);
  readonly state = signal<SessionState | null>(null);
  // Single-selection: at most one agent at a time.
  readonly selectedHandle = signal<number | null>(null);

  /** When user hovers a scenario card, store its id here so the Marey
   *  can swap its forecast preview. null = use the active baseline. */
  readonly previewScenarioId = signal<string | null>(null);
  // Backwards-compat: components that still call .has(h) on a Set.
  readonly selectedHandles = computed<Set<number>>(() => {
    const h = this.selectedHandle();
    return h == null ? new Set<number>() : new Set([h]);
  });
  // 'Active' = explicit selection; when Marey is visible, fall back to
  // the first agent so the inspector can show a default context.
  readonly activeHandle = computed<number | null>(() => {
    const selected = this.selectedHandle();
    if (selected != null) return selected;
    if (!this.showMarey()) return null;
    const ags = this.agents();
    return ags.length > 0 ? ags[0].handle : null;
  });
  readonly loading = signal(false);
  /** When a multi-step request is in flight, this holds the elapsed_steps
   *  value the backend should reach. UI can derive 'steps left' as
   *  (targetStep() - state().elapsed_steps). Reset to null on response. */
  readonly targetStep = signal<number | null>(null);
  private _pollHandle: ReturnType<typeof setInterval> | null = null;
  readonly error = signal<string | null>(null);
  readonly message = signal<string | null>(null);

  readonly playing = signal(false);
  readonly playSpeed = signal(5);
  readonly panResetTrigger = signal(0);
  readonly wsConnected = computed(() => this.ws.connected());

  readonly showMap = signal(true);
  readonly showMarey = signal(false);

  readonly trajectories = signal<Map<number, TrajectoryPoint[]>>(new Map());

  readonly agents = computed<AgentDTO[]>(() => this.state()?.agents ?? []);

  // ── Policies (loaded once at app start) ───────────────────────
  private readonly _policies = signal<PolicyInfo[]>([]);
  readonly availablePolicies = computed<PolicyInfo[]>(() => this._policies());
  readonly defaultPolicy = computed<PolicyName>(() => {
    const def = this._policies().find((p) => p.is_default);
    const first = this._policies()[0];
    return (def?.id ?? first?.id ?? 'deadlock_avoidance') as PolicyName;
  });

  loadPolicies(): void {
    this.api.listPolicies().subscribe({
      next: (list) => {
        this._policies.set(list);
        if (list.length === 0) return;
        const current = this._activePolicy();
        if (!list.some((p) => p.id === current)) {
          const def = list.find((p) => p.is_default) ?? list[0];
          this._activePolicy.set(def.id as PolicyName);
        }
      },
      error: (err) => console.warn('Failed to load policies', err),
    });
  }
  readonly elapsedSteps = computed(() => this.state()?.elapsed_steps ?? 0);
  readonly maxSteps = computed(() => this.state()?.max_episode_steps ?? 0);
  readonly width = computed(() => this.state()?.width ?? 0);
  readonly height = computed(() => this.state()?.height ?? 0);
  readonly railGrid = computed<number[][]>(() => this.state()?.rail_grid ?? []);
  readonly railTiles = computed<RailTile[]>(() => this.state()?.rail_tiles ?? []);
  readonly episodeDone = computed(() => this.state()?.episode_done ?? false);


  // === HMI-Architektur (Phase A) ===
  readonly simulationTime = signal<number>(0);
  readonly layerVisibility = signal<LayerVisibility>({
    grid: true,
    nextDecisions: true,
    agentTrajectory: false,
    switches: false,
    signals: false,
  });
  readonly kpiPriorities = signal<KpiPriorities>({
    time: 1,
    energy: 0.5,
    platformRouting: 0.5,
    trainRouting: 0.5,
  });
  readonly notifications = signal<AppNotification[]>([]);
  readonly scenarios = signal<ScenarioOption[]>([]);
  readonly recommendations = signal<Recommendation[]>([]);
  readonly focusedElement = signal<{ kind: 'train' | 'switch' | 'signal'; id: string } | null>(null);

  constructor() {
    effect(() => {
      const msg = this.ws.lastMessage();
      if (!msg) return;

      // untracked() verhindert dass Set-Calls hier eine Loop triggern
      untracked(() => {
        if (msg.type === 'state' && msg.state) {
          this.state.set(msg.state);
          this._recordTrajectory(msg.state);
          this.loading.set(false);
        } else if (msg.type === 'episode_done') {
          this.playing.set(false);
          this.message.set('Episode finished. Use Reset to start again.');
        } else if (msg.type === 'error') {
          this.error.set(msg.message ?? 'Unknown WebSocket error');
          this.playing.set(false);
        }
      });
    });
  }

  private _recordTrajectory(state: SessionState) {
    const map = this.trajectories();
    const newMap = new Map(map);
    let changed = false;

    for (const a of state.agents) {
      const list = newMap.get(a.handle) ?? [];
      const lastPt = list.length > 0 ? list[list.length - 1] : null;
      if (lastPt && lastPt.step === state.elapsed_steps) {
        // Same step can arrive more than once (polling/ws timing). Keep
        // the newer snapshot if it contains a position while the old one
        // did not; otherwise update metadata and leave path intact.
        const shouldReplace = lastPt.position == null && a.position != null;
        if (shouldReplace || lastPt.direction !== a.direction || lastPt.state !== a.state) {
          const updatedLast = {
            step: state.elapsed_steps,
            position: a.position ?? a.initial_position,
            direction: a.direction,
            state: a.state,
          };
          const updated = [...list.slice(0, -1), updatedLast];
          newMap.set(a.handle, updated);
          changed = true;
        }
        continue;
      }
      const updated = [...list, {
        step: state.elapsed_steps,
        position: a.position ?? a.initial_position,
        direction: a.direction,
        state: a.state,
      }];
      newMap.set(a.handle, updated);
      changed = true;
    }

    if (changed) {
      this.trajectories.set(newMap);
    }
  }

  private _resetTrajectories() {
    this.trajectories.set(new Map());
  }

  toggleMap() {
    this.showMap.update((v) => !v);
    if (!this.showMap() && !this.showMarey()) this.showMarey.set(true);
  }

  toggleMarey() {
    this.showMarey.update((v) => !v);
    if (!this.showMap() && !this.showMarey()) this.showMap.set(true);
  }

  private _isAnyAgentMoving(st: SessionState | null): boolean {
    if (!st || st.agents.length === 0) return false;
    return st.agents.some((a) => a.state === 'MOVING');
  }

  private _autoAdvanceUntilFirstAgentReady(maxSteps: number = 300): void {
    const s = this.session();
    if (!s) return;
    const policy = this.activePolicy() || this.defaultPolicy();
    let stepped = 0;

    const run = () => {
      const st = this.state();
      if (!st) {
        this.loading.set(false);
        return;
      }
      if (this._isAnyAgentMoving(st) || st.episode_done || stepped >= maxSteps) {
        this.loading.set(false);
        this.refreshForecasts();
        return;
      }

      this.loading.set(true);
      this.api.step(s.id, policy, 1).subscribe({
        next: () => {
          stepped += 1;
          this.api.getState(s.id).subscribe({
            next: (nextState) => {
              this.state.set(nextState);
              this._recordTrajectory(nextState);
              run();
            },
            error: (e) => {
              this.error.set(`State failed: ${e.message}`);
              this.loading.set(false);
            },
          });
        },
        error: (e) => {
          this.error.set(`Auto-step failed: ${e.message}`);
          this.loading.set(false);
        },
      });
    };

    run();
  }

  newSession(opts: { width?: number; height?: number; agents?: number; maxSteps?: number } = {}) {
    this.loading.set(true);
    this.error.set(null);
    this.message.set(null);
    this.playing.set(false);
    this._resetTrajectories();
    const payload: any = {};
    if (opts.width != null) payload.width = opts.width;
    if (opts.height != null) payload.height = opts.height;
    if (opts.agents != null) payload.number_of_agents = opts.agents;
    this.api.createSession(payload).subscribe({
      next: (s) => {
        this.session.set(s);
        this.ws.connect(s.id);
        this.refreshState(true);
      },
      error: (e) => {
        this.error.set(`Create failed: ${e.message}`);
        this.loading.set(false);
      },
    });
  }

  refreshState(autoAdvanceFirstAgent: boolean = false) {
    const s = this.session();
    if (!s) return;
    this.api.getState(s.id).subscribe({
      next: (st) => {
        this.state.set(st);
        this._recordTrajectory(st);
        if (autoAdvanceFirstAgent) {
          this._autoAdvanceUntilFirstAgentReady();
        } else {
          this.loading.set(false);
        }
      },
      error: (e) => {
        this.error.set(`State failed: ${e.message}`);
        this.loading.set(false);
      },
    });
  }

  step(policy: PolicyName, n_steps: number = 1) {
    this._stepWithPolicy(policy, n_steps, true);
  }

  private _stepWithPolicy(policy: PolicyName, n_steps: number, canRecover: boolean) {
    const s = this.session();
    if (!s) return;
    if (this.episodeDone()) {
      this.message.set('Episode finished. Use Reset to start again.');
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    // Multi-step: remember the target so the toolbar can show 'N left'.
    const currentElapsed = this.state()?.elapsed_steps ?? 0;
    this.targetStep.set(currentElapsed + n_steps);
    this._stopPolling();
    this._stepSequential(s.id, policy, n_steps, canRecover);
  }

  private _stepSequential(sessionId: string, policy: PolicyName, remaining: number, canRecover: boolean): void {
    if (remaining <= 0) {
      this.targetStep.set(null);
      this.loading.set(false);
      this.refreshForecasts();
      return;
    }

    this.api.step(sessionId, policy, 1).subscribe({
      next: (res) => {
        if (res.message) this.message.set(res.message);
        this.api.getState(sessionId).subscribe({
          next: (st) => {
            this.state.set(st);
            this._recordTrajectory(st);
            if (st.episode_done) {
              this.targetStep.set(null);
              this.loading.set(false);
              this.refreshForecasts();
              return;
            }
            this._stepSequential(sessionId, policy, remaining - 1, false);
          },
          error: (e) => {
            this.error.set(`State failed: ${e.message}`);
            this.targetStep.set(null);
            this.loading.set(false);
          },
        });
      },
      error: (e) => {
        if (canRecover && this._isPolicyNotEnabledError(e)) {
          this._recoverPolicyAndRetryStep(sessionId, remaining);
          return;
        }
        this.error.set(`Step failed: ${e.message}`);
        this.targetStep.set(null);
        this.loading.set(false);
      },
    });
  }

  private _stopPolling(): void {
    if (this._pollHandle !== null) {
      clearInterval(this._pollHandle);
      this._pollHandle = null;
    }
  }

  reset() {
    const s = this.session();
    if (!s) return;
    this.panResetTrigger.update((v) => v + 1);
    this.loading.set(true);
    this.error.set(null);
    this.message.set(null);
    this.playing.set(false);
    this._resetTrajectories();
    this.api.reset(s.id).subscribe({
      next: () => this.refreshState(true),
      error: (e) => {
        this.error.set(`Reset failed: ${e.message}`);
        this.loading.set(false);
      },
    });
  }

  play(policy: PolicyName, speed: number = 5) {
    this._playWithPolicy(policy, speed, true);
  }

  private _playWithPolicy(policy: PolicyName, speed: number, canRecover: boolean) {
    const s = this.session();
    if (!s) return;
    if (this.episodeDone()) {
      this.message.set('Episode finished. Use Reset before Play.');
      return;
    }
    this.playSpeed.set(speed);
    this.api.play(s.id, { speed, policy }).subscribe({
      next: () => {
        this.playing.set(true);
        this.error.set(null);
      },
      error: (e) => {
        if (canRecover && this._isPolicyNotEnabledError(e)) {
          this._recoverPolicyAndRetryPlay(s.id, speed);
          return;
        }
        this.error.set(`Play failed: ${e.message}`);
      },
    });
  }

  pause() {
    const s = this.session();
    if (!s) return;
    this.api.pause(s.id).subscribe({
      next: () => this.playing.set(false),
      error: (e) => this.error.set(`Pause failed: ${e.message}`),
    });
  }

  togglePlay(policy: PolicyName, speed: number = 5) {
    if (this.playing()) this.pause();
    else this.play(policy, speed);
  }

  toggleAgentSelection(handle: number) {
    // Single-select: clicking the same agent again deselects it,
    // clicking another swaps the selection.
    this.selectedHandle.set(
      this.selectedHandle() === handle ? null : handle,
    );
  }

  clearSelection() {
    this.selectedHandle.set(null);
  }

  // ========== Decision Override (T6) ==========

  readonly showDecisions = signal(true);
  readonly decisionVisible = signal<Set<number>>(new Set());

  isDecisionVisibleFor(handle: number): boolean {
    const perAgent = this.decisionVisible();
    if (perAgent.size === 0) return this.showDecisions();
    return perAgent.has(handle);
  }

  toggleDecisionFor(handle: number) {
    const cur = new Set(this.decisionVisible());
    if (cur.has(handle)) cur.delete(handle);
    else cur.add(handle);
    this.decisionVisible.set(cur);
  }

  toggleAllDecisions() {
    this.showDecisions.update((v) => !v);
    this.decisionVisible.set(new Set());
  }

  setOverride(handle: number, action: number) {
    const s = this.session();
    if (!s) return;
    this.api.setOverride(s.id, handle, action as any).subscribe({
      next: () => {
        this.refreshState();
        this.refreshForecasts();
      },
      error: (e: any) => this.error.set('Override failed: ' + e.message),
    });
  }

  clearOverride(handle: number) {
    const s = this.session();
    if (!s) return;
    this.api.clearOverride(s.id, handle).subscribe({
      next: () => {
        this.refreshState();
        this.refreshForecasts();
      },
      error: (e: any) => this.error.set('Clear override failed: ' + e.message),
    });
  }

  refreshForecasts(): void {
    const s = this.session();
    if (!s) return;
    this.api.getScenarios(s.id).subscribe({
      next: (scenarios) => this.scenarios.set(scenarios),
      error: () => {},
    });
    this.api.getRecommendations(s.id).subscribe({
      next: (recs) => this.recommendations.set(recs),
      error: () => {},
    });
  }

  // ── Active policy (synced with backend session.policy) ────────
  private readonly _activePolicy = signal<PolicyName>('deadlock_avoidance');
  readonly activePolicy = computed<PolicyName>(() => this._activePolicy());

  setActivePolicy(policy: PolicyName): void {
    this._activePolicy.set(policy);
  }

  private _isPolicyNotEnabledError(err: any): boolean {
    const msg = String(err?.error?.detail ?? err?.message ?? '').toLowerCase();
    return msg.includes('not enabled');
  }

  private _recoverPolicyAndRetryStep(sessionId: string, n_steps: number): void {
    this.api.getScenarioPolicies(sessionId).subscribe({
      next: (cfg) => {
        const fallback = cfg.enabled_ids?.[0] as PolicyName | undefined;
        if (!fallback) {
          this.error.set('Step failed: no enabled policy available');
          this._stopPolling();
          this.targetStep.set(null);
          this.loading.set(false);
          return;
        }
        this.setActivePolicy(fallback);
        this._stepWithPolicy(fallback, n_steps, false);
      },
      error: () => {
        this.error.set('Step failed: unable to resolve enabled policies');
        this._stopPolling();
        this.targetStep.set(null);
        this.loading.set(false);
      },
    });
  }

  private _recoverPolicyAndRetryPlay(sessionId: string, speed: number): void {
    this.api.getScenarioPolicies(sessionId).subscribe({
      next: (cfg) => {
        const fallback = cfg.enabled_ids?.[0] as PolicyName | undefined;
        if (!fallback) {
          this.error.set('Play failed: no enabled policy available');
          return;
        }
        this.setActivePolicy(fallback);
        this._playWithPolicy(fallback, speed, false);
      },
      error: () => {
        this.error.set('Play failed: unable to resolve enabled policies');
      },
    });
  }

}
