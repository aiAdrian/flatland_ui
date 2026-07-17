import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { ApiService } from './api.service';
import {
  VISUAL_ENCODING_PRESETS,
  VisualEncoding,
  VisualEncodingPresetId,
  loadVisualEncoding,
  matchingPresetId,
  saveVisualEncoding,
} from './visual-encoding';
import {
  DECISION_LOG_CAP,
  DecisionLogEntry,
  DecisionOwner,
  actionLabelFor,
} from './decision-log';
import {
  AppNotification,
  ImpactItem,
  InteractionMode,
  KpiPriorities,
  KpiWeights,
  LayerVisibility,
  Recommendation,
  ScenarioOption,
  WhatIfTrajById,
} from './events/event-types';
import { WebSocketService } from './websocket.service';
import {
  LearningRecord,
  LearningStore,
  RationaleContext,
  buildPreferenceHypothesis,
  strategyLabelForAction,
} from './learning-store.service';
import { AgentDTO, PolicyInfo, PolicyName, RailTile, SessionInfo, SessionState, StationRef } from './models';

/**
 * One human intervention captured while in Co-Learning mode (WP 3.3).
 * This is the raw material a future feedback/learning loop would consume;
 * for now it powers the in-session intervention count and the reflection panel.
 *
 * The optional rationale fields (Workstream B Tier 1, deck slides 5 & 7) are
 * filled in AFTER the override, when the operator answers the "why?" prompt and
 * confirms the preference hypothesis. They are absent on entries the operator
 * never annotated — hence optional and backward-compatible.
 */
export interface CoLearningEntry {
  /** Simulation step at which the human intervened. */
  step: number;
  /** Agent the human acted on. */
  handle: number;
  /** Action the human chose (Flatland action id). */
  humanAction: number;
  /** Top AI recommendation title at that moment, if any. */
  aiSuggestion: string | null;
  timestamp: number;
  /** Chosen "why" (structured reason chips, joined) + optional note.
   *  Set by the rationale-capture prompt after the override. */
  rationale?: string;
  /** Generated "when {context}, prefer {choice}" hypothesis string. */
  preferenceHypothesis?: string;
  /** Operator's confirmation of the hypothesis. 'once' = a one-off, explicitly
   *  NOT promoted to a persistent preference (overfitting guard). */
  hypothesisResponse?: 'yes' | 'once' | 'no';
}

/**
 * Workstream B Tier 1 — an override awaiting its "why?" (deck slide 7). Set in
 * `setOverride` when a human overrode a recommendation (or any intervention in
 * Co-Learning), consumed by the rationale-capture UI, cleared on submit/dismiss.
 *
 * Carries the handles needed to patch the matching `CoLearningEntry` (by
 * timestamp) and `DecisionLogEntry` (by seq) once the operator answers, so the
 * rationale lands on the exact entry it explains.
 */
export interface PendingRationale {
  handle: number;
  action: number;
  mode: InteractionMode;
  aiSuggestion: string | null;
  simStep: number;
  timestamp: number;
  /** Situation snapshot for the hypothesis template. */
  context: RationaleContext;
  /** DecisionLogEntry seq to patch on submit. */
  decisionSeq: number;
  /** CoLearningEntry timestamp to patch on submit (Co-Learning mode only). */
  coLearningTimestamp: number | null;
}

export interface TrajectoryPoint {
  /** First simulation step at this compressed trajectory cell/run. */
  step: number;
  /** Last simulation step still at this same cell/run. */
  endStep?: number;
  /** Number of raw time steps represented by this compressed point. */
  durationSteps?: number;
  /** Backwards-compatible alias used by some UI code. */
  dwellSteps?: number;
  position: [number, number] | null;
  direction: number | null;
  state: string;
}

@Injectable({ providedIn: 'root' })
export class SessionStore {
  private api = inject(ApiService);
  private ws = inject(WebSocketService);
  private learning = inject(LearningStore);

  readonly session = signal<SessionInfo | null>(null);
  readonly state = signal<SessionState | null>(null);
  // Single-selection: at most one agent at a time.
  readonly selectedHandle = signal<number | null>(null);
  readonly enabledScenarioPolicyIds = signal<string[]>([]);
  readonly enabledControlPolicyIds = signal<string[]>([]);

  /** When user hovers a scenario card, store its id here so the Marey
   *  can swap its forecast preview. null = use the active baseline. */
  readonly previewScenarioId = signal<string | null>(null);

  /** What-if Compare map preview: the two branch forecast paths the map
   *  draws when the operator picks an action. baseline = AI course (yellow),
   *  branch = human "My plan" (blue). Set on choose(); cleared on commit /
   *  leave / destroy (same discipline as previewScenarioId). Distinct from
   *  previewScenarioId so the two overlays never collide. */
  readonly whatIfPreview = signal<{
    baseline: WhatIfTrajById;
    branch: WhatIfTrajById;
    handles: number[];
  } | null>(null);
  // Backwards-compat: components that still call .has(h) on a Set.
  readonly selectedHandles = computed<Set<number>>(() => {
    const h = this.selectedHandle();
    return h == null ? new Set<number>() : new Set([h]);
  });

  /** Agent handles highlighted because the user hovers an agent-related
   *  notification. This is intentionally separate from selection. */
  readonly notificationHoverHandles = signal<Set<number>>(new Set<number>());

  setNotificationHoverAgents(handles: number[]): void {
    const clean = handles
      .map((h) => Number(h))
      .filter((h) => Number.isFinite(h));
    this.notificationHoverHandles.set(new Set(clean));
  }

  clearNotificationHoverAgents(): void {
    this.notificationHoverHandles.set(new Set<number>());
  }

  /** Cross-view agent hover, used by map/panel/Marey agent hover.
   *  It intentionally shares the same highlight set as notification hover:
   *  hover source differs, visual linked-agent highlight is the same.
   */
  setAgentHoverAgents(handles: number[]): void {
    this.setNotificationHoverAgents(handles);
  }

  setAgentHoverAgent(handle: number): void {
    this.setNotificationHoverAgents([handle]);
  }

  clearAgentHoverAgents(): void {
    this.clearNotificationHoverAgents();
  }
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

  /** Shared station registry: one entry per distinct stop cell used by the
   *  trains (each train's origin + target), with a stable "S{n}" label ordered
   *  by position. Single source of truth for BOTH the map station layer and the
   *  timetable tile, so labels line up across the two. Derived frontend-side —
   *  no backend change. (Intermediate stops will join once waypoints are
   *  serialized; a real all-cities layer needs city_positions from the env.) */
  readonly stations = computed<StationRef[]>(() => {
    const cells = new Map<string, { row: number; col: number }>();
    for (const a of this.agents()) {
      // Prefer the full ordered stop list (incl. ECML intermediate stops); fall
      // back to just origin + target when stops are not in the payload.
      const positions = a.stops && a.stops.length
        ? a.stops.map((s) => s.cell)
        : [a.initial_position, a.target];
      for (const pos of positions) {
        if (!pos) continue;
        const row = Number(pos[0]);
        const col = Number(pos[1]);
        cells.set(`${row},${col}`, { row, col });
      }
    }
    return [...cells.values()]
      .sort((a, b) => a.row - b.row || a.col - b.col)
      .map((cell, i) => ({ id: `${cell.row},${cell.col}`, label: `S${i + 1}`, row: cell.row, col: cell.col }));
  });

  /** Shared label lookup used by the map and the timetable so a stop resolves to
   *  the same "S{n}" in both. Returns null for cells that are not a known stop. */
  stationLabelForCell(pos: [number, number] | null | undefined): string | null {
    if (!pos) return null;
    const key = `${Number(pos[0])},${Number(pos[1])}`;
    return this.stations().find((s) => s.id === key)?.label ?? null;
  }

  // ── Policies (loaded once at app start) ───────────────────────
  private readonly _policies = signal<PolicyInfo[]>([]);
  readonly availablePolicies = computed<PolicyInfo[]>(() => this._policies());
  readonly defaultPolicy = computed<PolicyName>(() => {
    const def = this._policies().find((p) => p.is_default);
    const first = this._policies()[0];
    return (def?.id ?? first?.id ?? 'deadlock_avoidance') as PolicyName;
  });

  setEnabledScenarioPolicyIds(ids: string[]): void {
    this.enabledScenarioPolicyIds.set([...ids]);
  }

  setEnabledControlPolicyIds(ids: string[]): void {
    this.enabledControlPolicyIds.set([...ids]);
  }

  loadPolicies(): void {
    this.api.listPolicies().subscribe({
      next: (list) => {
        this._policies.set(list);
        if (list.length === 0) return;

        if (this.enabledControlPolicyIds().length === 0) {
          this.enabledControlPolicyIds.set(list.filter((p) => p.show_in_ui).map((p) => p.id));
        }
        if (this.enabledScenarioPolicyIds().length === 0) {
          this.enabledScenarioPolicyIds.set(list.filter((p) => p.supports_scenarios).map((p) => p.id));
        }
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
    agentTrajectory: true,
    trajectoryCellInfo: true,
    switches: false,
    signals: false,
    stations: true,
  });
  readonly kpiPriorities = signal<KpiPriorities>({
    time: 1,
    energy: 0.5,
    platformRouting: 0.5,
    trainRouting: 0.5,
  });

  /**
   * Visual-Encoding Registry (v1 — authorship only). Sibling to
   * `layerVisibility`, but persisted to localStorage (pre-session, locked
   * during a run via the Session Settings UI). Seam-first: no tile renders
   * authorship yet (B1 what-if will be the first consumer). See
   * `visual-encoding.ts` + the `visual-encoding-registry` memory.
   */
  readonly visualEncoding = signal<VisualEncoding>(loadVisualEncoding());

  /** Preset id matching the current encoding (for the settings radio). */
  readonly visualEncodingPreset = computed<VisualEncodingPresetId>(() =>
    matchingPresetId(this.visualEncoding()),
  );

  /** Apply a named preset. Callers (Session Settings) gate this to pre-session. */
  setVisualEncodingPreset(presetId: VisualEncodingPresetId): void {
    const preset = VISUAL_ENCODING_PRESETS.find((p) => p.id === presetId);
    if (preset) this.visualEncoding.set(preset.encoding);
  }

  /**
   * Decision Log (Tile A2, Capitalization kind). Owned, timestamped record of
   * every decision in a session — human / ai / system. Reuses existing capture
   * choke-points (setOverride / clearOverride / systemHold) in all modes; the
   * coLearningFeedback signal (Co-Learning only) is left untouched so the
   * reflection panel is unaffected. See `core/decision-log.ts` +
   * `docs/plans/tile-a2-decision-log.md`.
   */
  readonly decisionLog = signal<DecisionLogEntry[]>([]);

  /** Per-handle decision-window open time (ms), for decisionTimeMs. */
  private readonly _decisionWindowStart = signal<Record<number, number>>({});

  /** Open the decision window for a handle (idempotent). Called by the
   *  impact panel when a conflict engages. */
  openDecisionWindow(handle: number): void {
    this._decisionWindowStart.update((m) =>
      m[handle] ? m : { ...m, [handle]: Date.now() },
    );
  }

  /** Close the window for a handle; return dwell ms, or null if none was open. */
  private _closeDecisionWindow(handle: number): number | null {
    const start = this._decisionWindowStart()[handle];
    if (start == null) return null;
    this._decisionWindowStart.update((m) => {
      const next = { ...m };
      delete next[handle];
      return next;
    });
    return Date.now() - start;
  }

  /** Append a decision entry (auto-assigns seq, trims to the rolling cap). */
  /** Returns the assigned sequence number so callers (e.g. setOverride) can
   *  later patch the entry — Workstream B annotates the rationale AFTER the
   *  operator answers the "why?" prompt, not at append time. */
  private _appendDecision(entry: Omit<DecisionLogEntry, 'seq'>): number {
    let seq = 0;
    this.decisionLog.update((list) => {
      seq = list.length ? list[list.length - 1].seq + 1 : 1;
      const next = [...list, { ...entry, seq }];
      return next.length > DECISION_LOG_CAP
        ? next.slice(next.length - DECISION_LOG_CAP)
        : next;
    });
    return seq;
  }

  /** Clear the log (e.g. on session reset). */
  clearDecisionLog(): void {
    this.decisionLog.set([]);
  }

  /**
   * Single consumption surface for the KPI filter. Raw slider values are
   * normalised to weights that sum to 1 (or fall back to an equal split when
   * every slider is at 0). Any view that wants to reflect KPI priorities
   * (scenario ranking, Marey emphasis, recommendation scoring) should read
   * this — NOT kpiPriorities directly. The concrete semantics (how each
   * weight maps onto backend scoring) are intentionally left open for now;
   * this just guarantees the wiring exists and is well-defined.
   */
  readonly kpiWeights = computed<KpiWeights>(() => {
    const p = this.kpiPriorities();
    const keys: (keyof KpiPriorities)[] = ['time', 'energy', 'platformRouting', 'trainRouting'];
    const sum = keys.reduce((acc, k) => acc + Math.max(0, p[k]), 0);
    if (sum <= 0) {
      const equal = 1 / keys.length;
      return { time: equal, energy: equal, platformRouting: equal, trainRouting: equal };
    }
    return {
      time: Math.max(0, p.time) / sum,
      energy: Math.max(0, p.energy) / sum,
      platformRouting: Math.max(0, p.platformRouting) / sum,
      trainRouting: Math.max(0, p.trainRouting) / sum,
    };
  });

  /**
   * Active human-AI collaboration mode (WP 3.1 / 3.3 / 3.4). For now this only
   * holds UI state; mode-specific behaviour is wired up in a later step.
   */
  readonly interactionMode = signal<InteractionMode>('recommendation');

  /** Which post-session survey parts are active (configured in Settings).
   *  Default: all parts (see DEFAULT_SURVEY_PARTS). */
  readonly enabledSurveyParts = signal<string[]>([
    'mode', 'nasa-tlx', 'trust', 'ueq-s', 'open',
  ]);

  setEnabledSurveyParts(ids: string[]): void {
    this.enabledSurveyParts.set([...ids]);
  }

  /**
   * Flatland has no malfunction *type* (a malfunction is just "train stuck for N
   * steps"). When this is off we label it honestly as "Train breakdown". When on
   * (demo/study), we assign a synthetic operational type from the AI4REALNET
   * taxonomy deterministically per train, clearly marked "(demo)". A real backend
   * `malfunction_type` (if added later) always wins over both.
   */
  readonly demoMalfunctionTypes = signal<boolean>(false);

  setDemoMalfunctionTypes(on: boolean): void {
    this.demoMalfunctionTypes.set(on);
  }

  /** How many Co-Learning reflection questions to show per incident.
   *  Samira's storyboard: 2 of 5. Configurable in Settings. */
  readonly reflectionQuestionLimit = signal<number>(2);

  setReflectionQuestionLimit(n: number): void {
    this.reflectionQuestionLimit.set(Math.max(1, Math.min(5, Math.floor(n || 1))));
  }

  /** Decision time budget (seconds) before the system applies the recommended
   *  option itself (Recommendation & Co-Learning). Configurable in Settings. */
  readonly decisionCountdownSeconds = signal<number>(10);

  setDecisionCountdownSeconds(n: number): void {
    this.decisionCountdownSeconds.set(Math.max(3, Math.min(60, Math.floor(n || 10))));
  }

  /** How long an AI recommendation shows a countdown before it reads as
   *  "stale". 0 = no countdown: the recommendation stays as long as it
   *  makes sense (i.e. until the backend stops surfacing it, or the human
   *  acts on it). This countdown is a presentation cue only — it does not
   *  auto-apply anything (that's decisionCountdownSeconds). */
  readonly recommendationDurationSeconds = signal<number>(0);

  setRecommendationDurationSeconds(n: number): void {
    const v = Math.floor(n || 0);
    // 0 means "no countdown"; otherwise clamp to a sane [5, 120] window.
    this.recommendationDurationSeconds.set(v <= 0 ? 0 : Math.max(5, Math.min(120, v)));
  }

  /** Whether a new conflict auto-pauses the run (and starts the decision
   *  countdown) in Recommendation & Co-Learning. When off, conflicts still
   *  surface in the impact panel but the simulation keeps running — the
   *  human acts when they want, without being interrupted. Default on. */
  readonly autoPauseOnConflict = signal<boolean>(true);

  setAutoPauseOnConflict(on: boolean): void {
    this.autoPauseOnConflict.set(!!on);
  }

  /** Synthetic operational malfunction types (AI4REALNET D4.1 taxonomy A). */
  private static readonly DEMO_MALFUNCTION_TYPES = [
    'Track blockage',
    'Switch failure',
    'Signal failure',
    'Overhead-power failure',
  ];

  /** Label for a malfunctioning train's disruption type (see demoMalfunctionTypes). */
  malfunctionTypeLabel(agent: AgentDTO): string {
    const real = (agent as any)?.malfunction_type;
    if (typeof real === 'string' && real) return real;
    if (!this.demoMalfunctionTypes()) return 'Train breakdown';
    const types = SessionStore.DEMO_MALFUNCTION_TYPES;
    const idx = ((agent.handle % types.length) + types.length) % types.length;
    return `${types[idx]} (demo)`;
  }

  /** True while the AI drives the simulation autonomously (Director / WP 3.4). */
  readonly aiInControl = computed(() => this.interactionMode() === 'director');
  /** True in Co-Learning mode (WP 3.3), where human interventions are logged. */
  readonly isCoLearning = computed(() => this.interactionMode() === 'co-learning');

  /**
   * How action/policy options are framed across the whole UI:
   *  - 'recommended' (Recommendation / WP 3.1): AI ranks + badges a best option.
   *  - 'neutral'     (Co-Learning / WP 3.3): options shown as equal choices.
   *  - 'none'        (Director / WP 3.4): the human isn't prompted with options.
   * Every options surface (recommendations-panel, scenario-panel, …) reads THIS
   * — there is no parallel flag.
   */
  readonly optionPresentation = computed<'recommended' | 'neutral' | 'none'>(() => {
    switch (this.interactionMode()) {
      case 'recommendation':
        return 'recommended';
      case 'co-learning':
        return 'neutral';
      case 'director':
        return 'none';
    }
  });

  /** Human interventions recorded during the current Co-Learning session. */
  readonly coLearningFeedback = signal<CoLearningEntry[]>([]);
  readonly interventionCount = computed(() => this.coLearningFeedback().length);

  /** Workstream B Tier 1: an override awaiting its "why?" (deck slide 7).
   *  Non-null right after a human override that overrode a recommendation (or
   *  any Co-Learning intervention); the rationale-capture UI reads this. Cleared
   *  on submit / dismiss / session reset. Mode-agnostic store, mode-specific
   *  capture surface (docs/plans/colearning-across-modes.md §2). */
  readonly pendingRationale = signal<PendingRationale | null>(null);

  /** Confirmed learning records (deck slide 5) — proxied from LearningStore so
   *  panels can read them through the store they already inject. */
  readonly learningRecords = computed(() => this.learning.visibleRecords());
  readonly confirmedPreferenceCount = computed(() => this.learning.confirmedCount());

  /**
   * "Things have calmed down": the lull in which Co-Learning reflection should
   * become available (Hamouche et al., Kolb phase 2). Calm = a started session
   * that is currently paused with no agent in malfunction. A pause counts as
   * calm; the very start (no steps yet) does not.
   */
  readonly isCalm = computed(() => {
    if (!this.session()) return false;
    if (this.playing()) return false;
    if (this.elapsedSteps() === 0) return false;
    const anyMalfunction = this.agents().some(
      (a) => !!a.is_malfunctioning
        || (a.malfunction_remaining ?? 0) > 0
        || String(a.state ?? '').toUpperCase().includes('MALFUNCTION'),
    );
    return !anyMalfunction;
  });

  /** Co-Learning: the human explicitly asked to reflect *now* (also mid-run).
   *  The reflection panel shows when this is set (or at episode end). Reflection
   *  is intentional, not an auto-popup on every calm moment. */
  readonly reflectionRequested = signal<boolean>(false);
  toggleReflectionRequested(): void {
    this.reflectionRequested.update((v) => !v);
  }

  /**
   * Switch collaboration mode and apply its immediate behaviour:
   *  - Director: hand control to the AI by starting auto-play.
   *  - leaving Director: pause so the human regains step-by-step control.
   */
  // ── Guided demo flow (sequential modes on the SAME environment) ──────
  readonly demoActive = signal(false);
  readonly demoSequence: InteractionMode[] = ['recommendation', 'co-learning', 'director'];
  readonly demoStepIndex = signal(0);
  /** Current demo phase (mode) or null when no demo is running. */
  readonly demoPhase = computed<InteractionMode | null>(() =>
    this.demoActive() ? this.demoSequence[this.demoStepIndex()] : null,
  );
  readonly demoIsLast = computed(() => this.demoStepIndex() >= this.demoSequence.length - 1);

  /** True while the intro/explainer screen for the current demo mode is showing,
   *  before the human has chosen to start that mode's scenario. */
  readonly demoIntroPending = signal(false);

  /** Begin the guided demo at the first mode (caller creates the session). */
  startDemo(): void {
    this.demoStepIndex.set(0);
    this.demoActive.set(true);
    this.demoIntroPending.set(true);
    this.setInteractionMode(this.demoSequence[0]);
  }

  /** Advance to the next demo mode; returns false when the demo is finished. */
  advanceDemo(): boolean {
    if (this.demoIsLast()) {
      this.demoActive.set(false);
      return false;
    }
    this.demoStepIndex.update((i) => i + 1);
    this.demoIntroPending.set(true);
    this.setInteractionMode(this.demoSequence[this.demoStepIndex()]);
    return true;
  }

  /** Human clicked "Start scenario" on the mode-intro screen. */
  dismissDemoIntro(): void {
    this.demoIntroPending.set(false);
  }

  stopDemo(): void {
    this.demoActive.set(false);
    this.demoStepIndex.set(0);
    this.demoIntroPending.set(false);
  }

  setInteractionMode(mode: InteractionMode): void {
    const prev = this.interactionMode();
    if (mode === prev) return;
    this.interactionMode.set(mode);

    if (!this.session()) return;

    // Director (WP 3.4) no longer auto-plays on entering: the human first sets
    // a high-level directive (KPI weights + policy) and then explicitly starts
    // the autonomous run via the directive card. Leaving Director hands control
    // back to the human, so a running autonomous loop is paused.
    if (prev === 'director' && this.playing()) {
      this.pause();
    }
  }

  /** Top AI recommendation title right now, used to annotate Co-Learning logs. */
  private _currentTopRecommendation(): string | null {
    const recs = this.recommendations();
    return recs.length > 0 ? recs[0].title : null;
  }

  /** Snapshot the situation at override time for the preference hypothesis
   *  (deck slide 5: "learn the condition, not the option"). Derives the three
   *  Phase-2 trade-off proxies (connection/delay/ripple) from the top
   *  recommendation's backing scenario — the same heuristic the strategy cards
   *  use. `hasScenario` flags whether the booleans are real or defaulted, so the
   *  hypothesis template can stay honest when no scenario is on the table. */
  private _snapshotRationaleContext(handle: number, aiSuggestion: string | null): RationaleContext {
    const recs = this.recommendations();
    const scenarios = this.scenarios();
    const topRec = recs.length > 0 ? recs[0] : null;
    const scenario = topRec?.scenarioId
      ? scenarios.find((s) => s.id === topRec.scenarioId)
      : scenarios.find((s) => s.isBaseline) ?? scenarios[0] ?? null;

    const simStep = this.elapsedSteps();
    if (!scenario) {
      return {
        connectionCritical: false,
        lowDelay: false,
        lowRipple: false,
        aiSuggestion,
        simStep,
        hasScenario: false,
      };
    }

    const d = scenario.kpiDeltas?.meanDelay;
    const done = scenario.kpiDeltas?.done;
    const dl = scenario.kpiDeltas?.deadlocks;

    const delayValue = d == null ? '—' : `${d > 0 ? '+' : ''}${Math.round(d)}`;
    const connectionValue = done == null ? '—' : done > 0 ? 'Better' : done === 0 ? 'Stable' : 'Reduced';
    const rippleValue = dl == null ? '—' : dl <= 0 ? 'Low' : dl <= 1 ? 'Medium' : 'High';

    return {
      connectionCritical: done != null && done < 0,            // 'Reduced' → at risk
      lowDelay: d != null && d <= 0,                            // no added delay
      lowRipple: dl != null && dl <= 0,                         // no added deadlocks
      delayValue,
      connectionValue,
      rippleValue,
      aiSuggestion,
      simStep,
      hasScenario: true,
      scenarioTitle: scenario.title ?? null,
    };
  }

  /** Submit the rationale for the pending override: patch the matching
   *  CoLearningEntry (Co-Learning only) and DecisionLogEntry with the why +
   *  hypothesis + response, add a LearningRecord (confirmed → persisted; one-off
   *  → in-memory only), and clear the prompt. 'no' records nothing. */
  submitRationale(payload: {
    rationale: string;
    response: 'yes' | 'once' | 'no';
  }): void {
    const pending = this.pendingRationale();
    if (!pending) return;

    const hypothesis = buildPreferenceHypothesis(
      pending.context,
      strategyLabelForAction(pending.action),
    );

    // Patch the CoLearningEntry this override produced (Co-Learning mode only).
    if (pending.coLearningTimestamp != null) {
      this.coLearningFeedback.update((list) =>
        list.map((e) =>
          e.timestamp === pending.coLearningTimestamp
            ? {
                ...e,
                rationale: payload.rationale,
                preferenceHypothesis: hypothesis,
                hypothesisResponse: payload.response,
              }
            : e,
        ),
      );
    }

    // Patch the DecisionLogEntry this override produced (all modes).
    this.decisionLog.update((list) =>
      list.map((e) =>
        e.seq === pending.decisionSeq
          ? {
              ...e,
              rationale: payload.rationale,
              preferenceHypothesis: hypothesis,
              hypothesisResponse: payload.response,
            }
          : e,
      ),
    );

    // 'no' = hypothesis rejected → no Learning Record (deck slide 7).
    if (payload.response === 'yes' || payload.response === 'once') {
      const record: LearningRecord = {
        id: `lr_${pending.timestamp}_${pending.handle}`,
        createdAt: pending.timestamp,
        mode: pending.mode,
        handle: pending.handle,
        action: pending.action,
        strategyLabel: strategyLabelForAction(pending.action),
        rationale: payload.rationale,
        hypothesis,
        response: payload.response,
        once: payload.response === 'once',
        context: pending.context,
      };
      this.learning.addRecord(record);
    }

    this.pendingRationale.set(null);
  }

  /** Dismiss the "why?" prompt without recording (e.g. user closes it). The
   *  override itself stays logged; only the rationale is forgone. */
  dismissRationale(): void {
    this.pendingRationale.set(null);
  }

  readonly notifications = signal<AppNotification[]>([]);
  readonly scenarios = signal<ScenarioOption[]>([]);
  readonly recommendations = signal<Recommendation[]>([]);
  /** Phase-1 impact analysis: trains affected by a malfunction. */
  readonly impact = signal<ImpactItem[]>([]);
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

    // Persist the Visual-Encoding registry to localStorage on every change.
    // `loadVisualEncoding()` ran at signal init; this keeps storage in sync.
    effect(() => saveVisualEncoding(this.visualEncoding()));

    // Apply severity/positive as `:root` CSS custom-property overrides so a
    // chosen preset actually re-colours the app (malfunction indicator,
    // impact/left-sidebar severity, scenario/impact "recommended"), not just
    // the Session Settings preview. Session Settings only allows editing this
    // while no session is active (radios disabled via `sessionActive()`), so
    // a change can only happen before the next "New session"/"Restart run" —
    // this effect firing immediately on change already satisfies "takes
    // effect at the next run start" without extra gating. Authorship has no
    // consumer yet (seam-first, unchanged from before).
    effect(() => {
      const ve = this.visualEncoding();
      if (typeof document === 'undefined') return;
      const root = document.documentElement.style;
      root.setProperty('--app-severity-warn', ve.severity.warn);
      root.setProperty('--app-severity-error', ve.severity.error);
      root.setProperty('--app-positive', ve.positive);
    });
  }

  private _trajectoryPosition(a: AgentDTO): [number, number] | null {
    // Actual in-map position wins.
    if (a.position != null) return a.position;

    // READY_TO_DEPART has no position yet, but visually belongs to its
    // initial position. Duplicate suppression records it at most once.
    if (a.state === 'READY_TO_DEPART') return a.initial_position;

    // WAITING/DONE-without-position/etc. must not create artificial
    // repeated cells in the Marey topology.
    return null;
  }

  private _sameTrajectoryPosition(
    a: [number, number] | null,
    b: [number, number] | null,
  ): boolean {
    if (a == null || b == null) return a == null && b == null;
    return a[0] === b[0] && a[1] === b[1];
  }

  private _recordTrajectory(state: SessionState) {
    const map = this.trajectories();
    const newMap = new Map(map);
    let changed = false;

    const normalizeRun = (
      pt: TrajectoryPoint,
      endStep: number,
      direction: number | null,
      agentState: string,
    ): TrajectoryPoint => {
      const safeEnd = Math.max(pt.endStep ?? pt.step, endStep);
      const duration = Math.max(1, safeEnd - pt.step + 1);

      return {
        ...pt,
        endStep: safeEnd,
        durationSteps: duration,
        dwellSteps: duration,
        direction,
        state: agentState,
      };
    };

    for (const a of state.agents) {
      const list = newMap.get(a.handle) ?? [];
      const lastPt = list.length > 0 ? list[list.length - 1] : null;
      const pos = this._trajectoryPosition(a);

      // No meaningful position: do not append synthetic path cells.
      if (pos == null) {
        continue;
      }

      // Same backend step can arrive more than once via polling/ws.
      // Update the last run metadata for this exact step instead of appending.
      if (lastPt && state.elapsed_steps <= (lastPt.endStep ?? lastPt.step)) {
        const updated = normalizeRun(lastPt, state.elapsed_steps, a.direction, a.state);

        if (
          !this._sameTrajectoryPosition(lastPt.position, pos) ||
          lastPt.direction !== updated.direction ||
          lastPt.state !== updated.state ||
          lastPt.endStep !== updated.endStep ||
          lastPt.durationSteps !== updated.durationSteps ||
          lastPt.dwellSteps !== updated.dwellSteps
        ) {
          newMap.set(a.handle, [...list.slice(0, -1), { ...updated, position: pos }]);
          changed = true;
        }
        continue;
      }

      // Consecutive compression:
      // If agent stays in the same cell because of speed < 1, STOPPED,
      // MALFUNCTION, MALFUNCTION_OFF_MAP, etc., keep exactly one trajectory
      // cell and extend its endStep/duration.
      //
      // Important:
      // Later returning to the same cell creates a NEW run because only the
      // immediately previous point is compared.
      if (lastPt && this._sameTrajectoryPosition(lastPt.position, pos)) {
        const updated = normalizeRun(lastPt, state.elapsed_steps, a.direction, a.state);

        if (
          lastPt.direction !== updated.direction ||
          lastPt.state !== updated.state ||
          lastPt.endStep !== updated.endStep ||
          lastPt.durationSteps !== updated.durationSteps ||
          lastPt.dwellSteps !== updated.dwellSteps
        ) {
          newMap.set(a.handle, [...list.slice(0, -1), updated]);
          changed = true;
        }
        continue;
      }

      // New cell/run starts here.
      newMap.set(a.handle, [
        ...list,
        {
          step: state.elapsed_steps,
          endStep: state.elapsed_steps,
          durationSteps: 1,
          dwellSteps: 1,
          position: pos,
          direction: a.direction,
          state: a.state,
        },
      ]);
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

  newSession(opts: { width?: number; height?: number; agents?: number; maxSteps?: number; seed?: number; maxNumCities?: number; maxRailsBetweenCities?: number; maxRailPairsInCity?: number; latestDepartureMax?: number; speedProfile?: string; lineLength?: number; malfunctionRate?: number; malfunctionMinDuration?: number; malfunctionMaxDuration?: number; scenarioPolicyIds?: string[]; policyControlIds?: string[]; infrastructureScene?: unknown; scenarioPresetId?: string } = {}) {
    this.loading.set(true);
    this.error.set(null);
    this.message.set(null);
    this.playing.set(false);
    this._resetTrajectories();
    this.coLearningFeedback.set([]);
    this.pendingRationale.set(null);
    this.impact.set([]);
    this.clearDecisionLog();
    this.reflectionRequested.set(false);
    const payload: any = {};
    if (opts.width != null) payload.width = opts.width;
    if (opts.height != null) payload.height = opts.height;
    if (opts.agents != null) payload.number_of_agents = opts.agents;
    if (opts.maxSteps != null) payload.max_episode_steps = opts.maxSteps;
    if (opts.seed != null) payload.seed = opts.seed;
    if (opts.maxNumCities != null) payload.max_num_cities = opts.maxNumCities;
    if (opts.maxRailsBetweenCities != null) payload.max_rails_between_cities = opts.maxRailsBetweenCities;
    if (opts.maxRailPairsInCity != null) payload.max_rail_pairs_in_city = opts.maxRailPairsInCity;
    if (opts.latestDepartureMax != null) payload.latest_departure_max = opts.latestDepartureMax;
    if (opts.speedProfile != null) payload.speed_profile = opts.speedProfile;
    if (opts.lineLength != null) payload.line_length = opts.lineLength;
    if (opts.malfunctionRate != null) payload.malfunction_rate = opts.malfunctionRate;
    if (opts.malfunctionMinDuration != null) payload.malfunction_min_duration = opts.malfunctionMinDuration;
    if (opts.malfunctionMaxDuration != null) payload.malfunction_max_duration = opts.malfunctionMaxDuration;
    if (opts.scenarioPolicyIds != null) payload.enabled_scenario_policy_ids = opts.scenarioPolicyIds;
    if (opts.policyControlIds != null) payload.enabled_policy_ids = opts.policyControlIds;
    if (opts.infrastructureScene != null) payload.infrastructure_scene = opts.infrastructureScene;
    if (opts.scenarioPresetId != null) payload.scenario_preset_id = opts.scenarioPresetId;
    const requestedScene = payload.infrastructure_scene as { id?: string; name?: string; cells?: unknown[]; agents?: unknown[] } | undefined;
    this.message.set(opts.scenarioPresetId
      ? `Loading prebuilt scenario: ${opts.scenarioPresetId}`
      : requestedScene
      ? `Creating session from infrastructure: ${requestedScene.name || requestedScene.id || 'selected scene'} · sending ${requestedScene.cells?.length ?? 0} cells · ${requestedScene.agents?.length ?? 0} trains`
      : 'Creating session from random infrastructure');
    this.api.createSession(payload).subscribe({
      next: (s) => {
        this.session.set(s);
        this.message.set(s.scenario_preset_id
          ? `Loaded scenario preset: ${s.scenario_preset_id} · ${s.width} × ${s.height} · ${s.num_agents} trains`
          : s.infrastructure_scene_id
          ? `Loaded infrastructure scene: ${s.infrastructure_scene_id}`
          : 'Loaded random infrastructure');
        if (opts.scenarioPolicyIds != null) {
          this.setEnabledScenarioPolicyIds(opts.scenarioPolicyIds);
        }
        if (opts.policyControlIds != null) {
          this.setEnabledControlPolicyIds(opts.policyControlIds);
        }
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
        if (autoAdvanceFirstAgent && st.infrastructure_scene_id && st.infrastructure_scene_diagnostics) {
          this.message.set(this.formatInfrastructureLoadMessage(st));
        }
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

  private formatInfrastructureLoadMessage(st: SessionState): string {
    const diagnostics = st.infrastructure_scene_diagnostics;
    if (!diagnostics) {
      return `Loaded infrastructure scene: ${st.infrastructure_scene_id}`;
    }

    const mismatches = diagnostics.mismatched_cell_count ? ` · mismatches ${diagnostics.mismatched_cell_count}` : '';
    const unknown = diagnostics.unknown_tile_count ? ` · unknown tiles ${diagnostics.unknown_tile_count}` : '';
    return `Loaded infrastructure scene: ${st.infrastructure_scene_id} · cells ${diagnostics.rail_cell_count}/${diagnostics.scene_cell_count} · switches ${diagnostics.rail_switch_tile_count}/${diagnostics.scene_switch_count} · trains ${diagnostics.routable_agent_count}/${diagnostics.scene_agent_count}${mismatches}${unknown}`;
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

  /** End the current session and return to the welcome screen — without a full
   *  page reload. Tears down polling + WebSocket and clears session-derived
   *  state so `session()` becomes null (which shows the welcome view). */
  endSession(): void {
    this._stopPolling();
    this.ws.disconnect();
    this.playing.set(false);
    this.loading.set(false);
    this.error.set(null);
    this.message.set(null);
    this.targetStep.set(null);
    this.session.set(null);
    this.state.set(null);
    this.selectedHandle.set(null);
    this._resetTrajectories();
    this.impact.set([]);
    this.clearDecisionLog();
    this.scenarios.set([]);
    this.recommendations.set([]);
    this.notifications.set([]);
    this.coLearningFeedback.set([]);
    this.reflectionRequested.set(false);
    this.pendingRationale.set(null);
    this.previewScenarioId.set(null);
    this.whatIfPreview.set(null);
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
    this.coLearningFeedback.set([]);
    this.pendingRationale.set(null);
    this.impact.set([]);
    this.clearDecisionLog();
    this.reflectionRequested.set(false);
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

  private _setLocalOverride(handle: number, action: number | null): void {
    this.state.update((st) => {
      if (!st) return st;

      return {
        ...st,
        agents: st.agents.map((a) =>
          a.handle === handle
            ? { ...a, override_action: action as any }
            : a,
        ),
      };
    });
  }

  setOverride(handle: number, action: number, owner: DecisionOwner = 'human') {
    const s = this.session();
    if (!s) return;

    // Optimistic UI update: button reacts immediately.
    this._setLocalOverride(handle, action);

    const aiSuggestion = this._currentTopRecommendation();
    const simStep = this.elapsedSteps();
    const mode = this.interactionMode();
    const now = Date.now();

    // Co-Learning (WP 3.3): capture the human intervention so it can feed
    // the reflection panel (and, later, an actual learning loop).
    let coLearningTimestamp: number | null = null;
    if (this.isCoLearning()) {
      coLearningTimestamp = now;
      this.coLearningFeedback.update((list) => [
        ...list,
        {
          step: simStep,
          handle,
          humanAction: action,
          aiSuggestion,
          timestamp: now,
        },
      ]);
    }

    // Decision Log (Tile A2): capture every override in ALL modes (not just
    // Co-Learning). `owner` distinguishes a human click from the AI auto-decide
    // (countdown expiry). systemHold is logged separately (owner 'system').
    const decisionSeq = this._appendDecision({
      t: now,
      simStep,
      mode,
      handle,
      accountableOwner: owner,
      action: actionLabelFor(action),
      aiSuggestion,
      decisionTimeMs: owner === 'human' ? this._closeDecisionWindow(handle) : null,
    });

    // Workstream B Tier 1 (deck slide 7): after a human override that deviated
    // from an AI suggestion (or any Co-Learning intervention), surface the
    // "why?" prompt. Suppressed for AI/system owners, in Director mode (its
    // sparser signal economy has its own, separate capture — Tier 2), and for
    // bare human clicks with no AI context to deviate from. The capture UI is
    // mode-specific; the pending state here is mode-agnostic.
    if (owner === 'human' && mode !== 'director' && (aiSuggestion != null || this.isCoLearning())) {
      this.pendingRationale.set({
        handle,
        action,
        mode,
        aiSuggestion,
        simStep,
        timestamp: now,
        context: this._snapshotRationaleContext(handle, aiSuggestion),
        decisionSeq,
        coLearningTimestamp,
      });
    }

    this.api.setOverride(s.id, handle, action as any).subscribe({
      next: () => {
        // Backend remains source of truth, but do not wait for it to make
        // the button look active.
        this.refreshState();
        this.refreshForecasts();
      },
      error: (e) => {
        this.error.set(`Set override failed: ${e.message}`);
        // Re-sync from backend if request failed.
        this.refreshState();
      },
    });
  }

  /** Localized blocking: the SYSTEM holds an affected train (STOP) while the
   *  rest of the network keeps running, until the human decides. Unlike
   *  setOverride this is NOT logged as a human intervention — it's the safe
   *  default that creates the decision moment, not the human's choice. */
  systemHold(handle: number) {
    const s = this.session();
    if (!s) return;
    this._setLocalOverride(handle, 4); // STOP_MOVING
    // Decision Log: a system safe-default hold is NOT a human intervention
    // (per the comment above) — tagged 'system' so the strip never lets an
    // operator mistake it for their own decision.
    this._appendDecision({
      t: Date.now(),
      simStep: this.elapsedSteps(),
      mode: this.interactionMode(),
      handle,
      accountableOwner: 'system',
      action: 'hold',
      aiSuggestion: null,
      decisionTimeMs: null,
    });
    this.api.setOverride(s.id, handle, 4 as any).subscribe({
      next: () => this.refreshState(),
      error: () => {},
    });
  }

  clearOverride(handle: number, owner: DecisionOwner = 'human') {
    const s = this.session();
    if (!s) return;

    // Optimistic UI update: release/clear reacts immediately.
    this._setLocalOverride(handle, null);

    // Decision Log (Tile A2): releasing a hold = the human decided to let the
    // train proceed. Logged as 'proceed' (owner 'human' by default).
    this._appendDecision({
      t: Date.now(),
      simStep: this.elapsedSteps(),
      mode: this.interactionMode(),
      handle,
      accountableOwner: owner,
      action: 'proceed',
      aiSuggestion: this._currentTopRecommendation(),
      decisionTimeMs: owner === 'human' ? this._closeDecisionWindow(handle) : null,
    });

    this.api.clearOverride(s.id, handle).subscribe({
      next: () => {
        this.refreshState();
        this.refreshForecasts();
      },
      error: (e) => {
        this.error.set(`Clear override failed: ${e.message}`);
        this.refreshState();
      },
    });
  }

  refreshForecasts(): void {
    const s = this.session();
    if (!s) return;
    const kpi = this.kpiPriorities();
    this.api.getScenarios(s.id, kpi).subscribe({
      next: (scenarios) => this.scenarios.set(scenarios),
      error: () => {},
    });
    this.api.getRecommendations(s.id, kpi).subscribe({
      next: (recs) => this.recommendations.set(recs),
      error: () => {},
    });
    this.api.getImpact(s.id).subscribe({
      next: (items) => this.impact.set(items),
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
