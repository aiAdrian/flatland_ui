import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, OnDestroy, computed, effect, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { ApiService } from '../../core/api.service';
import { EventBusService } from '../../core/events/event-bus.service';
import { Recommendation, ScenarioOption } from '../../core/events/event-types';
import { PolicyName } from '../../core/models';
import { ScoreBadgeComponent } from '../../shared/ui/score-badge.component';
import { MetricChipComponent } from '../../shared/ui/metric-chip.component';
import { ReasoningListComponent, ReasoningItem } from '../../shared/ui/reasoning-list.component';
import { RationaleCaptureComponent } from '../rationale-capture/rationale-capture.component';
import { LearningRecordsComponent } from '../learning-records/learning-records.component';
import { CoLearningEffectComponent } from '../co-learning-effect/co-learning-effect.component';

type MetricLevel = 'good' | 'fair' | 'low' | 'neutral';
interface CardMetric {
  value: string;
  level: MetricLevel;
}

/** View-model for one scored strategy card (deck slides 1–2). Joins a
 *  Recommendation with its backing Scenario (via `scenarioId`). */
export interface StrategyCard {
  rec: Recommendation;
  /** A / B / C … positional identifier. */
  ident: string;
  title: string;
  /** 0–100. From scenario.score, else recommendation confidence. */
  score: number;
  isActive: boolean;
  isRecommended: boolean;
  metrics: { delay: CardMetric; connection: CardMetric; ripple: CardMetric };
  reasons: ReasoningItem[];
}

@Component({
  selector: 'app-recommendations-panel',
  standalone: true,
  imports: [CommonModule, ScoreBadgeComponent, MetricChipComponent, ReasoningListComponent, RationaleCaptureComponent, LearningRecordsComponent, CoLearningEffectComponent],
  templateUrl: './recommendations-panel.component.html',
  styleUrl: './recommendations-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class RecommendationsPanelComponent implements OnDestroy {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  store = inject(SessionStore);
  api = inject(ApiService);
  bus = inject(EventBusService);

  /** Collapsible panel (default expanded). */
  readonly collapsed = signal<boolean>(false);
  toggleCollapsed(): void { this.collapsed.update((v) => !v); }

  // Countdown ticker (1Hz). `now` drives a re-render every second so the
  // per-recommendation countdowns tick down.
  private tickHandle: any;
  private now = signal(Date.now());

  // Per-recommendation "first seen" timestamp (epoch ms), keyed by rec id.
  // The countdown is computed relative to *this* — so each recommendation
  // counts down independently, and the 2s background refetch no longer
  // resets everyone's timer (that was the old shared-counter bug).
  private firstSeen = new Map<string, number>();

  private _recPollHandle: any = null;
  private _recLastSession: string | null = null;

  constructor() {
    // Same rationale as notifications-panel: don't refetch on every WS
    // state update — that blocks /pause during Play. Throttle to 2s,
    // plus immediate refetch when session changes or Play stops.
    let lastPlaying = false;
    effect(() => {
      const sess = this.store.session();
      const playing = this.store.playing();

      if (!sess) {
        this.store.recommendations.set([]);
        this._stopRecPolling();
        this._recLastSession = null;
        this.firstSeen.clear();
        lastPlaying = false;
        return;
      }

      // New session → forget the previous run's countdown anchors.
      if (sess.id !== this._recLastSession) {
        this.firstSeen.clear();
      }

      const sessionChanged = sess.id !== this._recLastSession;
      const stoppedPlaying = lastPlaying && !playing;

      // Fetch on session change and when Play stops (= a decision moment).
      // Deliberately NO live 2s poll during Play: policy-switch recommendations
      // are marginal and would flip in/out each tick, making cards "disappear"
      // mid-hover (the flicker). They only matter when the run is paused.
      if (sessionChanged || stoppedPlaying) {
        this._fetchRecommendations(sess.id);
      }

      this._recLastSession = sess.id;
      lastPlaying = playing;
    });

    // Tick every second so the countdowns re-render.
    this.tickHandle = setInterval(() => {
      this.now.set(Date.now());
    }, 1000);
  }

  private _fetchRecommendations(sessionId: string): void {
    // In the guided demo, guarantee a recommendation surfaces (never an empty
    // panel for a whole run). Normal sessions keep the honest "empty = current
    // policy is fine" behaviour.
    const guarantee = this.store.demoActive();
    this.api.getRecommendations(sessionId, this.store.kpiPriorities(), guarantee).subscribe({
      next: (recs) => {
        this.store.recommendations.set(recs);

        // Anchor each *new* recommendation's countdown to "now"; keep the
        // anchor for recommendations that are still present (so a refetch
        // does not reset their timer); drop anchors for ones that vanished.
        const seen = Date.now();
        const liveIds = new Set(recs.map((r) => r.id));
        for (const r of recs) {
          if (!this.firstSeen.has(r.id)) this.firstSeen.set(r.id, seen);
        }
        for (const id of [...this.firstSeen.keys()]) {
          if (!liveIds.has(id)) this.firstSeen.delete(id);
        }
      },
      error: () => {},
    });
  }

  private _stopRecPolling(): void {
    if (this._recPollHandle !== null) {
      clearInterval(this._recPollHandle);
      this._recPollHandle = null;
    }
  }

  ngOnDestroy() {
    if (this.tickHandle) clearInterval(this.tickHandle);
    this._stopRecPolling();
    // Drop any hover-preview this panel still owns so it doesn't linger
    // on the map after the panel is gone.
    const preview = this.store.previewScenarioId();
    if (preview && this.store.recommendations().some((r) => r.scenarioId === preview)) {
      this.store.previewScenarioId.set(null);
    }
  }

  /** Seconds left for this recommendation, or null when no countdown is
   *  configured (duration = 0 → "stays as long as it makes sense").
   *  The configured duration overrides the backend's per-rec value; when
   *  unset (0) we treat the recommendation as non-expiring. */
  /** Hovering a recommendation previews its alternative branch on the map
   *  and Marey — the recommendation's scenarioId ('scn_<policy>') is the
   *  same id the scenario panel uses, so the existing preview overlay just
   *  works. Only branches we actually have a trajectory for are previewable. */
  previewable(r: Recommendation): boolean {
    if (!r.scenarioId) return false;
    return this.store.scenarios().some((s) => s.id === r.scenarioId);
  }

  /** A pinned option keeps its look-ahead on the map after the mouse leaves. */
  readonly pinnedScenarioId = signal<string | null>(null);

  previewOn(r: Recommendation): void {
    if (this.previewable(r)) this.store.previewScenarioId.set(r.scenarioId!);
  }

  previewOff(r: Recommendation): void {
    // A pinned option stays on the map; otherwise clear — but only if we're the
    // ones who set it (avoid stomping another source).
    const pinned = this.pinnedScenarioId();
    if (pinned) {
      this.store.previewScenarioId.set(pinned);
      return;
    }
    if (this.store.previewScenarioId() === r.scenarioId) {
      this.store.previewScenarioId.set(null);
    }
  }

  isPinned(r: Recommendation): boolean {
    return this.pinnedScenarioId() === r.scenarioId;
  }

  /**
   * Pin / unpin an option's look-ahead. Hover is fine for a quick glance, but to
   * *study* how an option reroutes the trains the overlay has to survive the
   * mouse leaving the card — especially in Director mode, where the options sit
   * above the map and comparing them is the whole job.
   */
  togglePin(r: Recommendation): void {
    if (!this.previewable(r)) return;
    if (this.isPinned(r)) {
      this.pinnedScenarioId.set(null);
      this.store.previewScenarioId.set(null);
      return;
    }
    this.pinnedScenarioId.set(r.scenarioId!);
    this.store.previewScenarioId.set(r.scenarioId!);
  }

  remaining(r: Recommendation): number | null {
    const duration = this.store.recommendationDurationSeconds();
    if (duration <= 0) return null; // no countdown
    const anchor = this.firstSeen.get(r.id) ?? this.now();
    const elapsed = Math.floor((this.now() - anchor) / 1000);
    return Math.max(0, duration - elapsed);
  }

  /** True while a countdown is active and getting close to zero. */
  isUrgent(r: Recommendation): boolean {
    const rem = this.remaining(r);
    return rem !== null && rem < 10;
  }

  // ── Confidence (NOT the score) ────────────────────────────────────────────
  // `confidence` answers "does this option really beat the current course?".
  // The backend estimates it from the margin over the baseline measured against
  // how far apart the policy branches lie (recommendation_generator.py). It is
  // model-reported, not calibrated against observed outcomes — the note below
  // says so, because the HMI review showed an unexplained % gets over-read.

  confidencePct(r: Recommendation): number {
    return Math.round(r.confidence * 100);
  }

  /** Traffic-light band for the chip. A near-coin-flip must not look confident. */
  confidenceLevel(r: Recommendation): 'high' | 'medium' | 'low' {
    if (r.confidence >= 0.75) return 'high';
    if (r.confidence >= 0.55) return 'medium';
    return 'low';
  }

  /** One line of evidence for the number, phrased for an operator. */
  confidenceNote(r: Recommendation): string {
    if (r.confidenceBasis === 'mock') {
      return 'Demo-Daten — kein echter Vergleichslauf dahinter.';
    }

    const margin = r.margin;
    if (margin == null) {
      return 'Modellwert der KI, nicht an beobachteten Ergebnissen kalibriert.';
    }

    const lead =
      margin > 0.01 ? `${margin.toFixed(2)} besser als der aktuelle Kurs`
      : margin < -0.01 ? `${Math.abs(margin).toFixed(2)} schlechter als der aktuelle Kurs`
      : 'gleichauf mit dem aktuellen Kurs';

    if (r.confidenceBasis === 'prior-only') {
      return `${this._capitalize(lead)} — keine Vergleichsvarianten, daher schwache Evidenz.`;
    }

    const spread = r.dispersion ?? 0;
    const agreement = spread > 0.5 ? 'die Varianten liegen weit auseinander'
      : spread > 0.2 ? 'die Varianten liegen mittelweit auseinander'
      : 'die Varianten liegen eng beieinander';

    return `${this._capitalize(lead)}, ${agreement} (Streuung ${spread.toFixed(2)}). `
      + 'Modellwert, nicht kalibriert.';
  }

  private _capitalize(text: string): string {
    return text.charAt(0).toUpperCase() + text.slice(1);
  }


  // ── Scored strategy cards (deck slides 1–2) ───────────────────────────────
  // Join each live recommendation with its backing scenario and derive the
  // score + sub-metrics the card shows. Recomputes when recommendations or
  // scenarios change (both are signals).
  readonly strategyCards = computed<StrategyCard[]>(() => {
    const recs = this.store.recommendations();
    const scenarios = this.store.scenarios();

    return recs.map((rec, i) => {
      const s = scenarios.find((sc) => sc.id === rec.scenarioId);
      return {
        rec,
        ident: String.fromCharCode(65 + i), // A, B, C, …
        title: rec.title,
        score: this._scoreFor(rec, s),
        isActive: !!s?.isBaseline,
        isRecommended: !!s?.isRecommended,
        metrics: {
          delay: this._delayMetric(s),
          connection: this._connectionMetric(s),
          ripple: this._rippleMetric(s),
        },
        reasons: this._reasonsFor(rec, s),
      };
    });
  });

  /** Scenario score is roughly [-1, 1]; map to 0–100. Falls back to the
   *  recommendation's own utility score when no scenario backs the card —
   *  never to `confidence`, which measures something else entirely. Both
   *  inputs are the same branch score (the fallback is just clamped at 0), so
   *  they go through the same mapping and the badge stays comparable. */
  private _scoreFor(rec: Recommendation, s?: ScenarioOption): number {
    const score = s?.score ?? rec.utilityScore ?? 0;
    return Math.round(((score + 1) / 2) * 100);
  }

  /** Δ mean delay vs. the active plan (positive = worse). */
  private _delayMetric(s?: ScenarioOption): CardMetric {
    const d = s?.kpiDeltas?.meanDelay;
    if (d == null) return { value: '—', level: 'neutral' };
    const sign = d > 0 ? '+' : '';
    const value = `${sign}${Math.round(d)}`;
    // Heuristic thresholds — refine once a real delay unit is confirmed.
    const level: MetricLevel = d <= 0 ? 'good' : d <= 5 ? 'fair' : 'low';
    return { value, level };
  }

  /** PROXY: connection quality derived from the `done` delta (more trains
   *  completing ≈ more connections preserved). Replace with a real
   *  connection-protection KPI when the backend exposes one (see
   *  docs/plans/colearning-across-modes.md — open points). */
  private _connectionMetric(s?: ScenarioOption): CardMetric {
    const d = s?.kpiDeltas?.done;
    if (d == null) return { value: '—', level: 'neutral' };
    if (d > 0) return { value: 'Better', level: 'good' };
    if (d === 0) return { value: 'Stable', level: 'neutral' };
    return { value: 'Reduced', level: 'low' };
  }

  /** PROXY: ripple risk derived from the `deadlocks` delta. Replace with a
   *  real ripple/propagation KPI when available. */
  private _rippleMetric(s?: ScenarioOption): CardMetric {
    const d = s?.kpiDeltas?.deadlocks;
    if (d == null) return { value: '—', level: 'neutral' };
    if (d <= 0) return { value: 'Low', level: 'good' };
    if (d <= 1) return { value: 'Medium', level: 'fair' };
    return { value: 'High', level: 'low' };
  }

  /** Structured "why" reasons for the WHY column — derived from scenario
   *  deltas plus the recommendation's own description. No LLM dependency. */
  private _reasonsFor(rec: Recommendation, s?: ScenarioOption): ReasoningItem[] {
    const out: ReasoningItem[] = [];
    const conn = this._connectionMetric(s);
    const ripple = this._rippleMetric(s);
    const delay = this._delayMetric(s);
    if (conn.level === 'good') {
      out.push({ title: 'Protects connections', detail: 'More trains complete than under the current plan.' });
    }
    if (ripple.level === 'good') {
      out.push({ title: 'Low ripple risk', detail: 'No added deadlocks expected downstream.' });
    }
    if (delay.level === 'good') {
      out.push({ title: 'Limited delay impact', detail: 'Mean delay stays at or below the current plan.' });
    }
    if (rec.description) {
      out.push({ title: 'Rationale', detail: rec.description });
    }
    return out;
  }

  policyIdForRecommendation(r: Recommendation): PolicyName | null {
    if (!r.scenarioId || !r.scenarioId.startsWith('scn_')) return null;
    return r.scenarioId.slice(4) as PolicyName;
  }

  isAutoDispatchPolicyEnabled(policyId: string): boolean {
    const enabled = this.store.enabledControlPolicyIds();
    // If config is not loaded yet, keep existing behaviour.
    if (enabled.length === 0) return true;
    return enabled.includes(policyId);
  }

  canAcceptRecommendation(r: Recommendation): boolean {
    const policyId = this.policyIdForRecommendation(r);
    if (!policyId) return true;
    return this.isAutoDispatchPolicyEnabled(policyId);
  }

  /** Decline the recommendation: the policy change is NOT applied, the card
   *  is dismissed. We still record the decision (accepted vs. rejected) as a
   *  signal for the co-learning / calibrated-trust loop — but it's framed as
   *  a decision, not a like/dislike. */
  reject(r: Recommendation) {
    this.bus.emit({ type: 'RECOMMENDATION_FEEDBACK', recId: r.id, thumbsUp: false });
    this.dismiss(r);
  }

  accept(r: Recommendation) {
    const sess = this.store.session();
    if (!sess) return;
    // Recommendation.scenarioId follows the format 'scn_<policy_id>' so
    // we can derive the policy id directly. If for some reason it's
    // missing, we just emit the bus events without a server call.
    this.bus.emit({ type: 'RECOMMENDATION_ACCEPTED', recId: r.id });

    if (!r.scenarioId || !r.scenarioId.startsWith('scn_')) {
      // Legacy / mock recommendation: keep bus event for compatibility.
      if (r.scenarioId) {
        this.bus.emit({ type: 'SCENARIO_CONFIRMED', scenarioId: r.scenarioId });
      }
      this.dismiss(r);
      return;
    }

    const policyId = r.scenarioId.slice(4) as PolicyName;
    if (!this.isAutoDispatchPolicyEnabled(policyId)) return;

    this.api.setPolicy(sess.id, policyId).subscribe({
      next: () => {
        this.store.setActivePolicy(policyId);
        // Inform the rest of the app (scenario panel listens, etc.)
        this.bus.emit({ type: 'SCENARIO_CONFIRMED', scenarioId: r.scenarioId! });
        this.dismiss(r);
      },
      error: (err) => {
        console.warn('Failed to apply recommendation', err);
      },
    });
  }

  /** Remove a recommendation from the local list (visual cue). Also clears
   *  any hover-preview it owns, since the card's mouseleave won't fire once
   *  it's gone, and drops its countdown anchor. */
  private dismiss(r: Recommendation) {
    this.previewOff(r);
    this.firstSeen.delete(r.id);
    const cur = this.store.recommendations();
    this.store.recommendations.set(cur.filter((x) => x.id !== r.id));
  }
}
