import { Injectable, inject } from '@angular/core';

import { SessionStore } from './session.store';
import type { CoLearningEntry } from './session.store';
import {
  LearningRecord,
  LearningStore,
  RationaleContext,
  buildPreferenceHypothesis,
} from './learning-store.service';
import { ActionInt, AgentDTO, SessionInfo, SessionState } from './models';
import {
  AppNotification,
  ImpactItem,
  ImpactOption,
  InteractionMode,
  Recommendation,
  ScenarioKpis,
  ScenarioOption,
} from './events/event-types';
import { DecisionLogEntry, DecisionOwner } from './decision-log';

/**
 * ── Gallery fixture / test data ───────────────────────────────────────────
 * The Widget Gallery (`/widgets`, features/widgets-gallery) is an isolated
 * authoring route with no real Flatland session behind it. Its opt-in live
 * preview renders the *real* panel components via panel-plugin-host, but
 * without a session every data panel renders empty. This service seeds a
 * small, clearly-fake fixture bundle into the SessionStore signals so those
 * previews show populated examples — no static screenshot assets.
 *
 * Lifecycle (driven by WidgetsGalleryComponent):
 *   - `seed()`   in ngOnInit — only when `store.session()` is null (i.e. the
 *                operator is on /widgets with no real run). A real session
 *                always wins: we neither seed nor later clear it.
 *   - `clear()`  in ngOnDestroy — resets *only* the signals we seeded, back to
 *                empty/null, so the fixtures can never leak into a real run.
 *
 * Map / Marey (`flatland-map`, `toggle-view`, `marey`) are deliberately NOT
 * fixture-fed here: they need real grid geometry + trajectories, and a fake
 * one would misrepresent more than it shows. Their schematic fallback stays.
 * The data panels (situation-summary, trains, agent-inspector, impact,
 * scenario, recommendations, notifications, decision-log, co-learning
 * reflection, risk-uncertainty) are what this bundle targets.
 *
 * Provenance: every value below is mock/gallery test data — it is NOT from a
 * Flatland run. data-provenance.md still governs what the badges say per
 * widget; this fixture just stands in for the real payload at preview time.
 */
@Injectable({ providedIn: 'root' })
export class GalleryFixtureService {
  private readonly store = inject(SessionStore);
  private readonly learning = inject(LearningStore);

  /** True only between a successful seed() and the matching clear(). Guards
   *  clear() so a real session (which we did not seed) is never wiped. */
  private _seeded = false;

  /** Wall-clock base for fixture timestamps (set at seed time so entries are
   *  ordered consistently within one gallery visit). */
  private _t0 = 0;

  seed(): void {
    // Guard: a real session is running — leave it untouched, both ways.
    if (this.store.session() !== null) return;

    this._t0 = Date.now();
    this.store.session.set(this._sessionInfo);
    this.store.state.set(this._sessionState);
    this.store.selectedHandle.set(1); // malfunctioning train → inspector shows detail
    this.store.scenarios.set(this._scenarios);
    this.store.recommendations.set(this._recommendations);
    this.store.notifications.set(this._notifications);
    this.store.impact.set(this._impact);
    this.store.decisionLog.set(this._decisionLog);
    this.store.coLearningFeedback.set(this._coLearningFeedback);

    // Learning records: 'once' = in-memory only, NEVER persisted (the
    // overfitting guard). So seeding never writes to localStorage, and
    // clear() removes them via resetToPersisted() without touching real
    // confirmed preferences.
    for (const rec of this._learningRecords()) {
      this.learning.addRecord(rec);
    }

    this._seeded = true;
  }

  clear(): void {
    if (!this._seeded) return; // we did not seed → must not clear a real run
    this.store.session.set(null);
    this.store.state.set(null);
    this.store.selectedHandle.set(null);
    this.store.scenarios.set([]);
    this.store.recommendations.set([]);
    this.store.notifications.set([]);
    this.store.impact.set([]);
    this.store.decisionLog.set([]);
    this.store.coLearningFeedback.set([]);
    // Removes only the in-memory 'once' fixture records; real persisted
    // confirmed preferences are reloaded from localStorage untouched.
    this.learning.resetToPersisted();
    this._seeded = false;
  }

  // ── Fixture payloads ───────────────────────────────────────────────────

  private get _sessionInfo(): SessionInfo {
    return {
      id: 'gallery-fixture-session',
      width: 10,
      height: 5,
      num_agents: 4,
      infrastructure_scene_id: null,
    };
  }

  private get _sessionState(): SessionState {
    return {
      width: 10,
      height: 5,
      num_agents: 4,
      elapsed_steps: 24,
      max_episode_steps: 200,
      agents: this._agents,
      rail_grid: this._railGrid,
      rail_tiles: [], // map not fixture-fed (see header comment)
      episode_done: false,
    };
  }

  /** A minimal valid grid of 1s (passable rail). Only the data panels read
   *  counts/agents; the map itself is left schematic. */
  private get _railGrid(): number[][] {
    return Array.from({ length: 5 }, () => Array.from({ length: 10 }, () => 1));
  }

  private get _agents(): AgentDTO[] {
    const base = (handle: number, over: Partial<AgentDTO>): AgentDTO => ({
      handle,
      position: null,
      direction: null,
      initial_position: null,
      initial_direction: null,
      target: [0, 0],
      state: 'MOVING',
      speed: 1,
      earliest_departure: null,
      latest_arrival: null,
      eta_to_depart: null,
      time_to_deadline: null,
      delay: 0,
      is_visible: true,
      delay_color_intensity: 0,
      cell_type: 'FORWARD_ONLY',
      next_decision: null,
      override_action: null,
      malfunction_remaining: 0,
      is_malfunctioning: false,
      ...over,
    });

    return [
      base(0, {
        position: [1, 2],
        direction: 1,
        initial_position: [0, 0],
        initial_direction: 1,
        target: [3, 8],
        state: 'MOVING',
        speed: 1,
        delay: 0,
        cell_type: 'SWITCH',
      }),
      base(1, {
        position: [2, 5],
        direction: 1,
        initial_position: [0, 2],
        initial_direction: 1,
        target: [4, 9],
        state: 'MALFUNCTION',
        speed: 0,
        delay: 4,
        delay_color_intensity: 0.6,
        malfunction_remaining: 12,
        is_malfunctioning: true,
        cell_type: 'FORWARD_ONLY',
      }),
      base(2, {
        position: null,
        direction: null,
        initial_position: [0, 4],
        initial_direction: 1,
        target: [4, 6],
        state: 'READY_TO_DEPART',
        speed: 1,
        earliest_departure: 18,
        eta_to_depart: 0,
        cell_type: 'FORWARD_ONLY',
      }),
      base(3, {
        position: [4, 9],
        direction: 1,
        initial_position: [0, 6],
        initial_direction: 1,
        target: [4, 9],
        state: 'DONE',
        speed: 0,
        delay: 0,
        cell_type: 'DONE',
      }),
    ];
  }

  private get _scenarios(): ScenarioOption[] {
    const kpi = (over: Partial<ScenarioKpis>): ScenarioKpis => ({
      totalDelay: 120,
      deadlocks: 1,
      done: 2,
      meanDelay: 30,
      episodeSteps: 200,
      episodeFinished: false,
      ...over,
    });
    return [
      {
        id: 'gallery-scenario-baseline',
        title: 'Basis: laufende Planung',
        description: 'Aktuelle Route ohne Eingriff (Baseline).',
        kpiDelta: { time: 0, energy: 0 },
        kpis: kpi({}),
        kpiDeltas: kpi({ totalDelay: 0, deadlocks: 0, done: 0, meanDelay: 0 }),
        isBaseline: true,
        score: 0,
      },
      {
        id: 'gallery-scenario-reroute',
        title: 'Umleiten über Weiche 5',
        description: 'Zug 2 auf Nebengleis umleiten, Anschluss halten.',
        kpiDelta: { time: -0.2, energy: 0.1 },
        kpis: kpi({ totalDelay: 90, deadlocks: 0, done: 3, meanDelay: 22 }),
        kpiDeltas: kpi({ totalDelay: -30, deadlocks: -1, done: 1, meanDelay: -8 }),
        isRecommended: true,
        score: 0.6,
        tag: 'recommended',
      },
      {
        id: 'gallery-scenario-hold',
        title: 'Anhalten vor Blockabschnitt',
        description: 'Betroffenen Zug halten bis Störung behoben.',
        kpiDelta: { time: 0.2, energy: -0.1 },
        kpis: kpi({ totalDelay: 140, deadlocks: 1, done: 2, meanDelay: 35 }),
        kpiDeltas: kpi({ totalDelay: 20, deadlocks: 0, done: 0, meanDelay: 5 }),
        score: -0.3,
        tag: 'avoid',
      },
    ];
  }

  private get _recommendations(): Recommendation[] {
    return [
      {
        id: 'gallery-rec-reroute',
        title: 'Umleiten über Weiche 5',
        description: 'Niedrigere Zusatzverspätung, kein Folgewrangleitung.',
        confidence: 0.78,
        countdownSeconds: 10,
        scenarioId: 'gallery-scenario-reroute',
      },
      {
        id: 'gallery-rec-hold',
        title: 'Anhalten vor Blockabschnitt',
        description: 'Sicherer Halt bis zur Störungsbehebung, höherer Verzug.',
        confidence: 0.41,
        countdownSeconds: 10,
        scenarioId: 'gallery-scenario-hold',
      },
    ];
  }

  private get _notifications(): AppNotification[] {
    return [
      {
        id: 'gallery-notif-malfunction',
        kind: 'warning',
        title: 'Störung Zug 1',
        message: 'Zug 1 steht seit 4 Schritten — anhaltende Blockierung.',
        timestamp: this._t0 - 60_000,
        relatedElement: { kind: 'train', id: '1' },
      },
      {
        id: 'gallery-notif-conflict',
        kind: 'error',
        title: 'Konflikt Zug 2',
        message: 'Vorausfahrt auf Zug 1 — Eingriff nötig.',
        timestamp: this._t0 - 30_000,
        relatedElement: { kind: 'train', id: '2' },
      },
      {
        id: 'gallery-notif-arrival',
        kind: 'info',
        title: 'Ankunft Zug 3',
        message: 'Zug 3 hat sein Ziel erreicht.',
        timestamp: this._t0 - 10_000,
        relatedElement: { kind: 'train', id: '3' },
      },
    ];
  }

  private get _impact(): ImpactItem[] {
    const opts = (recommended: 'reroute' | 'hold'): ImpactOption[] => [
      { action: 'hold', label: 'Halten', available: true, recommended: recommended === 'hold' },
      { action: 'reroute', label: 'Umleiten', available: true, recommended: recommended === 'reroute' },
      { action: 'proceed', label: 'Weiterfahren', available: false, recommended: false },
    ];
    return [
      {
        handle: 2,
        blocked_by: 1,
        blocked_cell: [2, 5],
        eta_steps: 8,
        clears_in_steps: 12,
        can_reroute: true,
        reroute_action: 1, // LEFT
        reroute_cell: [2, 4],
        recommended_action: 'reroute',
        options: opts('reroute'),
        severity: 'high',
      },
      {
        handle: 0,
        blocked_by: 1,
        blocked_cell: [2, 6],
        eta_steps: 14,
        clears_in_steps: 12,
        can_reroute: false,
        reroute_action: null,
        reroute_cell: null,
        recommended_action: 'hold',
        options: opts('hold'),
        severity: 'medium',
      },
    ];
  }

  private get _decisionLog(): DecisionLogEntry[] {
    const e = (
      seq: number,
      handle: number,
      owner: DecisionOwner,
      action: DecisionLogEntry['action'],
      mode: InteractionMode,
      aiSuggestion: string | null,
      decisionTimeMs: number | null,
      over: Partial<DecisionLogEntry> = {},
    ): DecisionLogEntry => ({
      seq,
      t: this._t0 - (4 - seq) * 30_000,
      simStep: 18 + seq,
      mode,
      handle,
      accountableOwner: owner,
      action,
      aiSuggestion,
      decisionTimeMs,
      ...over,
    });

    return [
      e(1, 1, 'human', 'hold', 'co-learning', 'Umleiten über Weiche 5', 4200, {
        rationale: 'Anschlusszug abwarten — Sicherheit vor Tempo.',
        preferenceHypothesis:
          'Bei kritischem Anschluss, geringer Zusatzverspätung und niedrigem Ripple-Risiko bevorzugst du Halten.',
        hypothesisResponse: 'yes',
      }),
      e(2, 0, 'ai', 'accept', 'recommendation', 'Umleiten über Weiche 5', null),
      e(3, 2, 'system', 'hold', 'recommendation', null, null),
    ];
  }

  private get _coLearningFeedback(): CoLearningEntry[] {
    return [
      {
        step: 18,
        handle: 1,
        humanAction: 4, // STOP_MOVING
        aiSuggestion: 'Umleiten über Weiche 5',
        timestamp: this._t0 - 90_000,
        rationale: 'Anschlusszug abwarten — Sicherheit vor Tempo.',
        preferenceHypothesis:
          'Bei kritischem Anschluss, geringer Zusatzverspätung und niedrigem Ripple-Risiko bevorzugst du Halten.',
        hypothesisResponse: 'yes',
      },
    ];
  }

  private _learningRecords(): LearningRecord[] {
    const ctx: RationaleContext = {
      connectionCritical: true,
      lowDelay: true,
      lowRipple: true,
      delayValue: '-8',
      connectionValue: 'Reduced',
      rippleValue: 'Low',
      aiSuggestion: 'Umleiten über Weiche 5',
      simStep: 18,
      hasScenario: true,
      scenarioTitle: 'Umleiten über Weiche 5',
    };
    const hypothesis = buildPreferenceHypothesis(ctx, 'Halten');
    return [
      {
        id: 'gallery-lr-1',
        createdAt: this._t0 - 90_000,
        mode: 'co-learning' as InteractionMode,
        handle: 1,
        action: 4 as ActionInt,
        strategyLabel: 'Halten',
        rationale: 'Anschlusszug abwarten — Sicherheit vor Tempo.',
        hypothesis,
        response: 'once' as const,
        once: true,
        context: ctx,
      },
    ];
  }
}
