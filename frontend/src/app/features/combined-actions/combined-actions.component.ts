import { Component, HostBinding, Input, OnDestroy, computed, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { ACTION_PACKAGES, ActionPackage } from '../../core/combined-actions/action-packages';
import { TrainIdentityService } from '../../core/train-identity.service';
import { predictImpact } from '../../core/combined-actions/impact-prediction';
import { perTrainDeltaMin } from '../../core/combined-actions/combined-actions-preview';
import { ActionCardComponent, ActionFraming, ActivePreview } from './components/action-card/action-card.component';
import { TradeoffPlotComponent, TradeoffPoint } from './components/tradeoff-plot/tradeoff-plot.component';

/** How the widget presents its packages in the active interaction mode. */
interface CombinedActionsBehavior {
  /** Decision-Support framing (spec §3): Recommendation ↔ Assessment ↔ suppressed. */
  framing: ActionFraming;
  /** Whether the human may reorder and apply. */
  editable: boolean;
  /** Whether the AI's pick is sorted to the top. */
  rank: boolean;
  /** One line under the title — the only explanation the widget carries. */
  hint: string;
}

/**
 * Combined Actions (widget E1) — AI-proposed coordinated multi-train actions
 * the dispatcher can reorder in place, with the consequence of their change
 * predicted immediately and shown in the other views.
 *
 * Spec: docs/plans/widget-e1-combined-actions.md.
 *
 * Grounded in T3.4 / `AI4REALNET/Tokener`, where the unit of interaction is a
 * coordinated priority order over several trains rather than a per-train
 * command, and in T2.3 (expected outcome per alternative). Predictions are a
 * deterministic **mock** — `dataSource: 'mock'` in the catalog — pending a real
 * PP/CBS re-solve (see the spec's §8).
 */
@Component({
  selector: 'app-combined-actions',
  standalone: true,
  imports: [ActionCardComponent, TradeoffPlotComponent],
  templateUrl: './combined-actions.component.html',
  styleUrl: './combined-actions.component.scss',
})
export class CombinedActionsComponent implements OnDestroy {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  readonly store = inject(SessionStore);
  private readonly identity = inject(TrainIdentityService);

  /** The version each card is currently showing, by package id. */
  private readonly activeByPackage = signal<Record<string, ActivePreview>>({});

  /** The card whose consequence is pushed to the map and the Marey. Null = none;
   *  only one at a time, on purpose (two overlapping overlays are unreadable). */
  readonly previewedPackage = signal<string | null>(null);

  /** The card the operator opened for editing. Null = all three sit in their
   *  compact form, which is the default: folding two of three hid exactly the
   *  comparison the panel exists to support. */
  private readonly _expandedPackage = signal<string | null>(null);

  /**
   * Which card is expanded. Empty = none, and that is the normal state now.
   *
   * Every card keeps its sequence and its figures in compact form, so all three
   * can be compared at a glance; opening one adds the diff, the version chooser
   * and the buttons. The earlier accordion — one card open, two folded to a
   * headline — bought height by hiding two thirds of the comparison, which was
   * the wrong trade.
   */
  readonly expandedPackage = computed<string>(() => this._expandedPackage() ?? '');

  /** Toggle a card open; opening one closes any other. */
  expand(packageId: string): void {
    this._expandedPackage.update((current) => (current === packageId ? null : packageId));
  }

  /**
   * The trade-off plot is visible by default.
   *
   * Hiding it behind a toggle to save height meant the comparison simply was not
   * there any more — the operator had to know to look for it. It is the answer
   * to "which of these is better", so it stays on screen; the height is paid for
   * by the cards being compact instead.
   */
  readonly plotOpen = signal(true);

  togglePlot(): void {
    this.plotOpen.update((open) => !open);
  }

  /** One line standing in for the folded plot: the trade the operator just made
   *  if there is one, else which option leads on each axis. */
  readonly plotSummary = computed<string>(() => {
    const pts = this.tradeoffPoints();
    if (!pts.length) return '';

    const variant = pts.find((p) => p.origin === 'human');
    if (variant) {
      const ai = pts.find((p) => p.origin === 'ai' && p.packageId === variant.packageId);
      if (ai) {
        const min = variant.delayReductionMin - ai.delayReductionMin;
        const kwh = variant.energyKwh - ai.energyKwh;
        const delay = min === 0 ? 'same delay' : `${Math.abs(min)} min ${min > 0 ? 'more' : 'less'} saved`;
        const energy = kwh === 0 ? 'same energy' : `${Math.abs(kwh)} kWh ${kwh > 0 ? 'more' : 'less'}`;
        return `${variant.label}: ${delay}, ${energy}`;
      }
    }

    const fastest = pts.reduce((a, b) => (b.delayReductionMin > a.delayReductionMin ? b : a));
    const cheapest = pts.reduce((a, b) => (b.energyKwh < a.energyKwh ? b : a));
    // When one version wins on both axes there is no trade-off to summarise —
    // naming it twice read as a bug rather than as "this one simply leads".
    return fastest.label === cheapest.label
      ? `${fastest.label} leads on both`
      : `${fastest.label} saves most · ${cheapest.label} costs least`;
  });

  ngOnDestroy(): void {
    // Same discipline as previewScenarioId / whatIfPreview: the overlay must
    // never outlive the panel that owns it.
    this.store.setCombinedActionPreview(null);
    this.store.clearAgentHoverAgents();
  }

  /**
   * The single place this widget branches on mode.
   *  - recommendation → Recommendation framing: the AI's pick is badged and ranked first.
   *  - co-learning    → Assessment framing: A/B/C neutral, no badge, no ranking.
   *  - director       → suppressed to read-only supervision: dispatch-altitude
   *                     decisions belong to the AI in this mode (the human's
   *                     lever is the objective, in `strategy-options`).
   */
  readonly modeBehavior = computed<CombinedActionsBehavior>(() => {
    switch (this.store.interactionMode()) {
      case 'recommendation':
        return {
          framing: 'recommended',
          editable: true,
          rank: true,
          hint: 'Drag a train to fork a variant — map and ZWL show what it changes.',
        };
      case 'co-learning':
        return {
          framing: 'neutral',
          editable: true,
          rank: false,
          hint: 'Three coordinated actions, presented neutrally. Reorder one and compare your variant with the AI’s.',
        };
      case 'director':
        return {
          framing: 'none',
          editable: false,
          rank: false,
          hint: 'The AI is executing the marked action. Read-only — set the objective in Strategy Options.',
        };
    }
  });

  /** Recommendation mode ranks the AI's pick first; the other modes keep the
   *  authored order, so no framing is implied by position. */
  readonly packages = computed<readonly ActionPackage[]>(() => {
    if (!this.modeBehavior().rank) return ACTION_PACKAGES;
    return [...ACTION_PACKAGES].sort((a, b) => Number(b.recommended) - Number(a.recommended));
  });

  /**
   * Service name → live Flatland handle.
   *
   * Delegated to `TrainIdentityService`, which is what the map, the ZWL and the
   * timetable also read. That shared naming is the point: an action that talks
   * about `IC_703` and a timetable row that says `IC_703` are now provably the
   * same train, instead of two vocabularies that happened to look alike.
   */
  readonly handleByTrain = computed<Record<string, number>>(() => this.identity.handleByName());

  /**
   * Is anything actually wrong?
   *
   * A coordinated re-ordering is an answer to contention — offering three of
   * them while every train is running to plan invites the operator to fix
   * something that is not broken, and trains them to ignore the panel. So the
   * packages appear when the network gives a reason: a malfunction, or a train
   * the impact analysis reports as blocked.
   */
  readonly disrupted = computed(() => {
    if (this.store.impact().length > 0) return true;
    return this.store.agents().some(
      (a) => !!a.is_malfunctioning || (a.malfunction_remaining ?? 0) > 0,
    );
  });

  /** Why the panel is showing what it shows, in one line. */
  readonly disruptionReason = computed(() => {
    const blocked = this.store.impact().length;
    const broken = this.store.agents().filter(
      (a) => !!a.is_malfunctioning || (a.malfunction_remaining ?? 0) > 0,
    ).length;
    const parts: string[] = [];
    if (broken) parts.push(`${broken} Störung${broken === 1 ? '' : 'en'}`);
    if (blocked) parts.push(`${blocked} Zug/Züge blockiert`);
    return parts.join(' · ');
  });

  /** True once the session has enough trains to bind the packages onto. */
  readonly bound = computed(() => Object.keys(this.handleByTrain()).length > 0);

  /** The full provenance wording, shown on hover over the one-line note. */
  readonly provenanceDetail = computed(() =>
    this.bound()
      ? 'Delay and energy figures come from a deterministic model, not from the simulation. The action packages are fixtures whose services are bound to this session\'s trains — point at an action to see it in the map and the ZWL.'
      : 'No session trains to bind the action packages to. Start a session to see an action\'s consequence in the map and the ZWL.',
  );

  handleFor(train: string): number | null {
    return this.handleByTrain()[train] ?? null;
  }

  /**
   * Every version on every card, as points on the energy ↔ delay plane.
   *
   * The plot is the answer to "which of these is actually better?" once a
   * variant exists: a variant that shaves minutes by holding an ICE back moves
   * up-and-left, and no single number on a card would have shown that.
   */
  readonly tradeoffPoints = computed<TradeoffPoint[]>(() => {
    const active = this.activeByPackage();
    const points: TradeoffPoint[] = [];

    for (const pkg of ACTION_PACKAGES) {
      const ai = predictImpact(pkg.aiOrder);
      points.push({
        id: `${pkg.id}:ai`,
        packageId: pkg.id,
        label: pkg.id,
        origin: 'ai',
        recommended: pkg.recommended && this.modeBehavior().framing === 'recommended',
        // Default to active: a card that has not reported yet is showing the
        // AI proposal, and waiting for its first emit left every dot dimmed.
        active: !active[pkg.id]?.modified,
        delayReductionMin: ai.delayReductionMin,
        energyKwh: ai.energyKwh,
      });

      const current = active[pkg.id];
      if (current?.modified) {
        const variant = predictImpact(current.order);
        points.push({
          id: `${pkg.id}:human`,
          packageId: pkg.id,
          label: `${pkg.id}′`,
          origin: 'human',
          recommended: false,
          active: true,
          delayReductionMin: variant.delayReductionMin,
          energyKwh: variant.energyKwh,
        });
      }
    }
    return points;
  });

  /** A card changed which version it is showing. */
  onActiveChanged(preview: ActivePreview): void {
    this.activeByPackage.update((map) => ({ ...map, [preview.packageId]: preview }));
    if (this.previewedPackage() === preview.packageId) this.pushOverlay(preview);
  }

  /** Point at a card → its consequence appears in the map and the Marey. */
  onCardEnter(pkg: ActionPackage): void {
    this.previewedPackage.set(pkg.id);
    const preview = this.activeByPackage()[pkg.id];
    if (preview) this.pushOverlay(preview);
  }

  onCardLeave(): void {
    this.previewedPackage.set(null);
    this.store.setCombinedActionPreview(null);
    this.store.clearAgentHoverAgents();
  }

  /**
   * Translate the previewed version into the per-handle form the other views
   * consume, and light up the shared cross-view hover set so the affected
   * trains stand out in every panel at once.
   */
  private pushOverlay(preview: ActivePreview): void {
    const byTrain = this.handleByTrain();
    const bound = preview.order.filter((t) => byTrain[t] !== undefined);
    if (!bound.length) {
      this.store.setCombinedActionPreview(null);
      return;
    }

    // "No coordinated action" = the trains take their turn in train-number
    // order. That is the baseline each train's gain or loss is measured against.
    const baseline = [...bound].sort((a, b) => byTrain[a] - byTrain[b]);
    const net = predictImpact(preview.order).delayReductionMin;
    const deltaByTrain = perTrainDeltaMin(bound, baseline, net);

    const rankByHandle: Record<number, number> = {};
    const deltaMinByHandle: Record<number, number> = {};
    const trainByHandle: Record<number, string> = {};
    bound.forEach((train, i) => {
      const handle = byTrain[train];
      rankByHandle[handle] = i + 1;
      deltaMinByHandle[handle] = deltaByTrain[train] ?? 0;
      trainByHandle[handle] = train;
    });

    this.store.setCombinedActionPreview({
      packageId: preview.packageId,
      label: preview.label,
      modified: preview.modified,
      rankByHandle,
      deltaMinByHandle,
      trainByHandle,
    });
    this.store.setAgentHoverAgents(bound.map((t) => byTrain[t]));
  }
}
