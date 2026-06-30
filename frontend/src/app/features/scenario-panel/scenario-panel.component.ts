import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, computed, effect, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { ApiService } from '../../core/api.service';
import { EventBusService } from '../../core/events/event-bus.service';
import { KpiWeights, ScenarioOption } from '../../core/events/event-types';
import { PolicyName } from '../../core/models';

@Component({
  selector: 'app-scenario-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './scenario-panel.component.html',
  styleUrl: './scenario-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ScenarioPanelComponent {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  store = inject(SessionStore);
  api = inject(ApiService);
  bus = inject(EventBusService);

  /** Tracks which card is currently being confirmed. */
  confirming = signal<string | null>(null);

  /** Collapsible panel. Default: collapsed in Recommendation/Co-Learning (focus on
   *  the per-train decision), expanded in Director (policy is the directive). */
  readonly collapsed = signal<boolean>(false);
  toggleCollapsed(): void { this.collapsed.update((v) => !v); }
  private _lastDirector: boolean | null = null;

  /**
   * Scenarios ordered by the operator's KPI priorities. The baseline always
   * stays on top; the alternatives are ranked by a KPI-weighted desirability
   * score so that nudging the KPI sliders visibly re-orders the comparison.
   *
   * NOTE: the weight→KPI mapping below is provisional. It exists to make the
   * KPI filter a live, end-to-end wired control; the final scoring semantics
   * (and any backend involvement) are decided in a later step. See
   * SessionStore.kpiWeights for the single source of weights.
   */
  readonly rankedScenarios = computed<ScenarioOption[]>(() => {
    const scenarios = this.store.scenarios();
    const baseline = scenarios.filter((s) => s.isBaseline);
    const alternatives = scenarios.filter((s) => !s.isBaseline);

    // Co-Learning (and Director): present options neutrally — no KPI-score
    // reordering, just a stable order with the baseline pinned on top.
    if (this.store.optionPresentation() !== 'recommended') {
      return [...baseline, ...alternatives];
    }

    // Recommendation: rank alternatives by the operator's KPI priorities.
    const weights = this.store.kpiWeights();
    const ranked = [...alternatives].sort((a, b) => this.kpiScore(b, weights) - this.kpiScore(a, weights));
    return [...baseline, ...ranked];
  });

  /** Whether the panel may surface an AI-preferred option (badges, ranking). */
  readonly showRecommendedFraming = computed(() => this.store.optionPresentation() === 'recommended');

  /**
   * Provisional KPI-weighted score for a scenario: higher is better.
   * - time           → penalise mean delay
   * - energy         → penalise episode length (steps)
   * - platformRouting/trainRouting → reward completions, penalise deadlocks
   */
  private kpiScore(s: ScenarioOption, w: KpiWeights): number {
    const k = s.kpis;
    if (!k) return 0;
    const total = Math.max(1, this.totalAgents());
    const doneRatio = (k.done ?? 0) / total;
    const delayPenalty = (k.meanDelay ?? 0) / 10;
    const stepsPenalty = (k.episodeSteps ?? 0) / 1000;
    const deadlockPenalty = k.deadlocks ?? 0;
    return (
      w.time * -delayPenalty +
      w.energy * -stepsPenalty +
      (w.platformRouting + w.trainRouting) * (doneRatio - deadlockPenalty)
    );
  }

  constructor() {
    // Scenarios are EXPENSIVE: /hmi/scenarios runs the current policy
    // as baseline + every alternative policy from the same env state,
    // computing per-agent trajectories for each. Pulling on every WS
    // state update (5×/sec during Play) makes the simulation unusably
    // slow.
    //
    // Strategy: only refresh scenarios when something STRUCTURAL
    // changes — the session itself, or 'playing' transitions
    // false→true / true→false (start of play, pause/stop). State
    // ticks during Play do NOT trigger a refresh.
    //
    // Trade-off: while Play is running, scenarios shown reflect the
    // baseline at the moment Play started. They re-snap to current
    // state when the user pauses. This matches the typical workflow:
    // 'plan → play → inspect → adjust'.
    // Default collapse state by mode (re-applies on entering/leaving Director;
    // manual toggle persists within a mode).
    effect(() => {
      const director = this.store.aiInControl();
      if (director !== this._lastDirector) {
        this._lastDirector = director;
        this.collapsed.set(!director);
      }
    });

    let lastSessionId: string | null = null;
    let lastPlaying = false;
    effect(() => {
      const sess = this.store.session();
      const playing = this.store.playing();
      const sid = sess?.id ?? null;

      // Clear when session goes away.
      if (!sess) {
        this.store.scenarios.set([]);
        lastSessionId = null;
        lastPlaying = false;
        return;
      }

      const sessionChanged = sid !== lastSessionId;
      const stoppedPlaying = lastPlaying && !playing;

      // Pull scenarios on: new session, or when Play just stopped
      // (= user paused → wants fresh forecast for current state).
      if (sessionChanged || stoppedPlaying) {
        this.api.getScenarios(sess.id, this.store.kpiPriorities()).subscribe({
          next: (scenarios) => this.store.scenarios.set(scenarios),
          error: () => {},
        });
      }

      lastSessionId = sid;
      lastPlaying = playing;
    });
  }

  /** Manually refresh scenarios for the current state. Called by
   *  external triggers (multi-step done, reset, override, …). */
  refreshScenarios(): void {
    const sess = this.store.session();
    if (!sess) return;
    this.api.getScenarios(sess.id, this.store.kpiPriorities()).subscribe({
      next: (scenarios) => this.store.scenarios.set(scenarios),
      error: () => {},
    });
  }

  policyIdForScenario(s: ScenarioOption): string {
    return s.id.startsWith('scn_') ? s.id.slice(4) : s.id;
  }

  isAutoDispatchPolicyEnabled(policyId: string): boolean {
    const enabled = this.store.enabledControlPolicyIds();
    // If config is not loaded yet, keep existing behaviour.
    if (enabled.length === 0) return true;
    return enabled.includes(policyId);
  }

  canSwitchToScenarioPolicy(s: ScenarioOption): boolean {
    return this.isAutoDispatchPolicyEnabled(this.policyIdForScenario(s));
  }

  /** Switch the session-wide policy via POST /policy. */
  confirm(s: ScenarioOption) {
    const sess = this.store.session();
    if (!sess) return;
    // Derive policy id from "scn_<policy_id>"
    const policyId = this.policyIdForScenario(s);
    if (!this.isAutoDispatchPolicyEnabled(policyId)) return;
    this.confirming.set(s.id);
    this.api.setPolicy(sess.id, policyId as PolicyName).subscribe({
      next: () => {
        this.bus.emit({ type: 'SCENARIO_CONFIRMED', scenarioId: s.id });
        this.store.setActivePolicy(policyId as PolicyName);
        // Backend has cleared the scenario cache; force a reload so the
        // panel + Marey re-render with the NEW baseline (the chosen
        // policy now carries the 'Current' badge).
        this.api.getScenarios(sess.id, this.store.kpiPriorities()).subscribe({
          next: (scenarios) => this.store.scenarios.set(scenarios),
          error: () => {},
        });
        // Also clear any hover-preview so the Marey snaps back to baseline.
        this.store.previewScenarioId.set(null);
        this.confirming.set(null);
      },
      error: (err) => {
        console.warn('Failed to switch policy', err);
        this.confirming.set(null);
      },
    });
  }

  formatDelta(n: number | undefined | null): string {
    if (n == null) return '';
    return n > 0 ? `+${n}` : `${n}`;
  }

  /** Total agents from session state, used for KPI denominator. */
  totalAgents(): number {
    return this.store.state()?.agents?.length ?? 0;
  }
}
