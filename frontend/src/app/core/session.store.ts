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
  state: string;
}

const MAX_TRAJECTORY_POINTS = 500;

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
  // 'Active' = explicitly selected, OR first agent in list (Marey default).
  readonly activeHandle = computed<number | null>(() => {
    const sel = this.selectedHandle();
    if (sel != null) return sel;
    const ags = this.agents();
    return ags.length > 0 ? ags[0].handle : null;
  });
  readonly loading = signal(false);
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
    return (def?.id ?? 'deadlock_avoidance') as PolicyName;
  });

  loadPolicies(): void {
    this.api.listPolicies().subscribe({
      next: (list) => this._policies.set(list),
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
      if (lastPt && lastPt.step === state.elapsed_steps) continue;
      const updated = [...list, {
        step: state.elapsed_steps,
        position: a.position,
        state: a.state,
      }];
      // Cap to prevent memory blowup
      if (updated.length > MAX_TRAJECTORY_POINTS) {
        updated.splice(0, updated.length - MAX_TRAJECTORY_POINTS);
      }
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
        this.refreshState();
      },
      error: (e) => {
        this.error.set(`Create failed: ${e.message}`);
        this.loading.set(false);
      },
    });
  }

  refreshState() {
    const s = this.session();
    if (!s) return;
    this.api.getState(s.id).subscribe({
      next: (st) => {
        this.state.set(st);
        this._recordTrajectory(st);
        this.loading.set(false);
      },
      error: (e) => {
        this.error.set(`State failed: ${e.message}`);
        this.loading.set(false);
      },
    });
  }

  step(policy: PolicyName, n_steps: number = 1) {
    const s = this.session();
    if (!s) return;
    if (this.episodeDone()) {
      this.message.set('Episode finished. Use Reset to start again.');
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.api.step(s.id, policy, n_steps).subscribe({
      next: (res) => {
        if (res.message) this.message.set(res.message);
        this.refreshState();
      },
      error: (e) => {
        this.error.set(`Step failed: ${e.message}`);
        this.loading.set(false);
      },
    });
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
      next: () => this.refreshState(),
      error: (e) => {
        this.error.set(`Reset failed: ${e.message}`);
        this.loading.set(false);
      },
    });
  }

  play(policy: PolicyName, speed: number = 5) {
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
      next: () => this.refreshState(),
      error: (e: any) => this.error.set('Override failed: ' + e.message),
    });
  }

  clearOverride(handle: number) {
    const s = this.session();
    if (!s) return;
    this.api.clearOverride(s.id, handle).subscribe({
      next: () => this.refreshState(),
      error: (e: any) => this.error.set('Clear override failed: ' + e.message),
    });
  }

  // ── Active policy (synced with backend session.policy) ────────
  private readonly _activePolicy = signal<PolicyName>('deadlock_avoidance');
  readonly activePolicy = computed<PolicyName>(() => this._activePolicy());

  setActivePolicy(policy: PolicyName): void {
    this._activePolicy.set(policy);
  }

}
