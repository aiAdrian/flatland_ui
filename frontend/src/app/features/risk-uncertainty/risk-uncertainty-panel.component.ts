import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, computed, effect, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { Recommendation, ScenarioOption } from '../../core/events/event-types';

/**
 * Tile A1 — Risk & Uncertainty (spec: docs/plans/tile-a1-risk-uncertainty.md).
 *
 * Shows **how much to trust each AI output** — a calibrated reliability signal
 * plus *what* is uncertain — so "when do I intervene?" becomes an informed
 * choice. `kind` = Trust; granularity overview → detail.
 *
 * Honest-first-cut scoping (no backend UQ yet):
 *  - Confidence comes from `store.recommendations()[*].confidence` — labelled
 *    **"model-reported confidence"**, NOT "reliability", because it is not yet
 *    calibrated against outcomes (spec §4 backend table; flip the label once
 *    calibration data lands).
 *  - The uncertainty band is derived empirically from dispersion across
 *    `store.scenarios()` (score spread = cheap ensemble proxy). This signal IS
 *    measured, so it gets a strong label ("alternatives disagree: ±N%").
 *  - Epistemic vs. aleatoric split is a flagged backend extension, not faked.
 *
 * Mode behaviour (single mode-aware component, mirrors impact-panel pattern):
 *  - recommendation → reliability shown WITH the ranked recommendation
 *    (confidence + spread band); low/uncertain invites scrutiny.
 *  - co-learning    → uncertainty shown NEUTRALLY per option (Evaluative AI);
 *    no single trust-score winner.
 *  - director       → aggregate policy reliability, read-only; a low-confidence
 *    event surfaces as the adjustable-autonomy exception trigger.
 *
 * Accountability seam (spec §5): the tile instruments the operator's
 * accept/override *in the presence of a shown reliability* and emits
 * `{decision, shownReliability, shownUncertainty, action, decisionTimeMs}`.
 * First cut captures these locally (study instrument only — it does NOT mutate
 * sim state). Wiring the signal to the real decision surfaces
 * (recommendations-panel / impact-panel) is the interaction-logging-plan's job.
 */
@Component({
  selector: 'app-risk-uncertainty-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './risk-uncertainty-panel.component.html',
  styleUrl: './risk-uncertainty-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class RiskUncertaintyPanelComponent {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  readonly store = inject(SessionStore);

  /** Expanded detail (the "what is uncertain and why" drill-down). */
  readonly expanded = signal<boolean>(false);

  /**
   * Mode behaviour — the single place mode is branched on inside this tile.
   * Framing that is already a store-level projection stays in the template via
   * `store.optionPresentation()`. See docs/reference/panel-mode-matrix.md.
   */
  readonly modeBehavior = computed<{ framing: 'recommendation' | 'assessment' | 'supervisory'; interactive: boolean }>(() => {
    switch (this.store.interactionMode()) {
      case 'recommendation': return { framing: 'recommendation', interactive: true };
      case 'co-learning':    return { framing: 'assessment', interactive: true };
      case 'director':       return { framing: 'supervisory', interactive: false };
    }
  });

  // ── Reliability derivation (frontend-honest first cut) ────────────────
  // Confidence: from the (first) recommendation. Band: dispersion across
  // non-baseline scenarios' scores. Both are real signals the backend already
  // exposes — no UQ endpoint needed for this cut (spec §4).

  /** Non-baseline scenario alternatives with a score, used as the ensemble. */
  private readonly alternatives = computed<ScenarioOption[]>(() =>
    this.store
      .scenarios()
      .filter((s) => !s.isBaseline && typeof s.score === 'number'),
  );

  /** Spread of scores across alternatives (0..~2, since score is roughly -1..1). */
  private readonly scoreSpread = computed<number | null>(() => {
    const alts = this.alternatives();
    if (alts.length < 2) return null;
    const scores = alts.map((s) => s.score as number);
    return Math.max(...scores) - Math.min(...scores);
  });

  /** The recommendation the tile is currently anchored to (highest confidence). */
  readonly primaryRecommendation = computed<Recommendation | null>(() => {
    const recs = this.store.recommendations();
    if (!recs.length) return null;
    return [...recs].sort((a, b) => b.confidence - a.confidence)[0];
  });

  /** Aggregate confidence across all current recommendations (Director mode). */
  readonly aggregateConfidence = computed<number | null>(() => {
    const recs = this.store.recommendations();
    if (!recs.length) return null;
    return recs.reduce((sum, r) => sum + r.confidence, 0) / recs.length;
  });

  /** Band width from alternative-score dispersion. null = no ensemble. */
  readonly bandWidth = computed<'tight' | 'medium' | 'wide' | null>(() => {
    const spread = this.scoreSpread();
    if (spread === null) return null;
    if (spread > 0.5) return 'wide';
    if (spread > 0.2) return 'medium';
    return 'tight';
  });

  /** Half-spread as a percentage, for the "alternatives disagree: ±N%" label. */
  readonly dispersionPct = computed<number | null>(() => {
    const spread = this.scoreSpread();
    return spread === null ? null : Math.round((spread / 2) * 100);
  });

  /** Combined reliability level for colouring (high / medium / low). */
  readonly level = computed<'high' | 'medium' | 'low'>(() => {
    const conf = this.primaryRecommendation()?.confidence ?? this.aggregateConfidence();
    const band = this.bandWidth();
    if (band === 'wide') return 'low';
    if (conf !== null && conf >= 0.75 && band !== 'medium') return 'high';
    if ((conf !== null && conf < 0.5) || band === 'medium') return 'low';
    return 'medium';
  });

  /** Human-readable reasons for *what* is uncertain (the detail drill-down). */
  readonly reasons = computed<string[]>(() => {
    const out: string[] = [];
    const pct = this.dispersionPct();
    const band = this.bandWidth();
    if (pct !== null && band) {
      out.push(`Alternatives disagree on outcome (±${pct}%) — ${band} spread across ${this.alternatives().length} option(s).`);
    }
    const conf = this.primaryRecommendation()?.confidence ?? this.aggregateConfidence();
    if (conf !== null && conf < 0.5) {
      out.push('Model-reported confidence is below 0.5 — scrutinise before accepting.');
    }
    if (out.length === 0) {
      out.push('No dispersion signal available (fewer than 2 alternatives).');
    }
    return out;
  });

  readonly hasData = computed<boolean>(() =>
    this.primaryRecommendation() !== null || this.alternatives().length > 0,
  );

  /** Per-option neutral reliability view (Co-Learning). */
  readonly optionReliabilities = computed<Array<{
    id: string;
    title: string;
    score: number | null;
    evidence: string;
    isBaseline: boolean;
  }>>(() => {
    const scenarios = this.store.scenarios();
    if (!scenarios.length) return [];
    const spread = this.scoreSpread();
    const max = scenarios.reduce((m, s) => Math.max(m, s.score ?? -Infinity), -Infinity);
    const min = scenarios.reduce((m, s) => Math.min(m, s.score ?? Infinity), Infinity);
    return scenarios.map((s) => {
      const score = s.score ?? null;
      let evidence = 'no score';
      if (score !== null && isFinite(max) && isFinite(min)) {
        if (spread !== null && spread > 0) {
          const norm = (score - min) / spread; // 0..1
          evidence = norm > 0.66 ? 'evidence for' : norm < 0.33 ? 'evidence against' : 'mixed';
        } else {
          evidence = 'no dispersion';
        }
      }
      return { id: s.id, title: s.title, score, evidence, isBaseline: !!s.isBaseline };
    });
  });

  /** Director: a low-confidence aggregate is the exception trigger. */
  readonly directorException = computed<boolean>(() => {
    if (this.store.interactionMode() !== 'director') return false;
    const conf = this.aggregateConfidence();
    const band = this.bandWidth();
    return (conf !== null && conf < 0.5) || band === 'wide';
  });

  // ── Accountability instrumentation (spec §5) ──────────────────────────
  // First cut: local capture only. The operator states accept/override given
  // the shown reliability; we record the event + decision dwell time. This
  // makes the acceptance scenario (§6) demonstrable without a backend.

  private readonly _shownAt = signal<number | null>(null);

  /** Start the decision-dwell clock when reliability first becomes visible. */
  constructor() {
    effect(() => {
      const has = this.hasData() && this.modeBehavior().interactive;
      this._shownAt.set(has ? Date.now() : null);
    });
  }

  readonly relianceEvents = signal<RelianceEvent[]>([]);

  /** Overtrust proxy readout: override rate split by reliability level. */
  readonly overtrustProxy = computed(() => {
    const ev = this.relianceEvents();
    if (!ev.length) return null;
    const low = ev.filter((e) => e.shownLevel === 'low' && e.shownBand === 'wide');
    const high = ev.filter((e) => e.shownLevel === 'high' && e.shownBand === 'tight');
    const rate = (rows: RelianceEvent[]) =>
      rows.length ? Math.round((rows.filter((r) => r.action === 'override').length / rows.length) * 100) : null;
    return {
      lowWide: { n: low.length, overrideRate: rate(low) },
      highTight: { n: high.length, overrideRate: rate(high) },
      total: ev.length,
    };
  });

  toggleExpanded(): void {
    this.expanded.update((v) => !v);
  }

  /** Record an accept/override stated *in the presence of the shown reliability*. */
  recordReliance(action: 'accept' | 'override'): void {
    if (!this.modeBehavior().interactive) return;
    const shownAt = this._shownAt();
    const decision = this.primaryRecommendation()?.title
      ?? this.alternatives()[0]?.title
      ?? 'active policy';
    const event: RelianceEvent = {
      decision,
      shownReliability: this.primaryRecommendation()?.confidence ?? this.aggregateConfidence(),
      shownUncertainty: this.bandWidth(),
      shownLevel: this.level(),
      shownBand: this.bandWidth(),
      action,
      decisionTimeMs: shownAt !== null ? Date.now() - shownAt : 0,
      at: Date.now(),
    };
    this.relianceEvents.update((list) => [...list, event]);
    // eslint-disable-next-line no-console
    console.info('[A1 risk-uncertainty] reliance event', event);
  }

  clearRelianceEvents(): void {
    this.relianceEvents.set([]);
  }
}

interface RelianceEvent {
  decision: string;
  shownReliability: number | null;
  shownUncertainty: 'tight' | 'medium' | 'wide' | null;
  shownLevel: 'high' | 'medium' | 'low';
  shownBand: 'tight' | 'medium' | 'wide' | null;
  action: 'accept' | 'override';
  decisionTimeMs: number;
  at: number;
}
