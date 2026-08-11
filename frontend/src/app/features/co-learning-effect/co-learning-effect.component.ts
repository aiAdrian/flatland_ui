import { CommonModule } from '@angular/common';
import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { ApiService, DirectorWeights } from '../../core/api.service';
import { OperatorModelBridge } from '../../core/operator-model-bridge.service';
import {
  OperatorAdjustment,
  OperatorContext,
  OperatorModelService,
  ValueAxis,
} from '../../core/operator-model.service';
import { SessionStore } from '../../core/session.store';

/** German axis labels for the callout (the panel copy is German). */
const AXIS_LABEL: Record<ValueAxis, string> = {
  punctuality: 'Pünktlichkeit',
  connection: 'Anschluss',
  stability: 'Netzstabilität',
  throughput: 'Durchsatz',
};

/**
 * Co-Learning **effect** — the visible half of Level B
 * (`docs/plans/co-learning-direction.md`): it makes the *consequence* of the
 * operator's confirmed preferences explicit, instead of only counting them.
 *
 * Two things:
 *  1. **"Weil du mir das beigebracht hast …"** — when the operator model's
 *     re-ranking hint comes from a confirmed learning, name the learning and
 *     which trade-off it now favours.
 *  2. **Dial proposal** — the reward weights inferred from the operator's own
 *     deliberate decisions, offered for the Director's `punctuality /
 *     connections / stability` sliders. Explicitly opt-in: the operator applies
 *     it, the AI never moves the sliders on its own.
 *
 * Ranking nudge, not a hard rule — same framing as the existing panel hint.
 */
@Component({
  selector: 'app-co-learning-effect',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './co-learning-effect.component.html',
  styleUrl: './co-learning-effect.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class CoLearningEffectComponent {
  private api = inject(ApiService);
  private store = inject(SessionStore);
  model = inject(OperatorModelService);
  /** Injected so the (root-scoped) bridge is instantiated and starts reporting
   *  the operator's decisions once a session runs. */
  private bridge = inject(OperatorModelBridge);

  /** The active re-ranking hint, if the model proposes one. */
  readonly adjustment = signal<OperatorAdjustment | null>(null);
  readonly applying = signal(false);
  readonly applied = signal(false);

  readonly profile = computed(() => this.model.profile());
  readonly isWarm = computed(() => this.model.isWarm());

  /** Only a hint that came from a *confirmed* learning gets the callout. */
  readonly confirmedCallout = computed(() => {
    const adj = this.adjustment();
    return adj?.appliedLearning ? adj : null;
  });

  readonly suggestedWeights = computed(() => this.model.suggestedWeights());

  /**
   * True once the inferred weights actually carry a preference, i.e. they differ
   * from the planner's neutral default (1, 1, 1). The Director's live dials live
   * in `director-weights`' own state, so we compare against the default rather
   * than inventing shared state for them.
   */
  readonly weightsDiffer = computed(() => {
    const s = this.suggestedWeights();
    if (!s) return false;
    return (
      Math.abs(s.punctuality - 1) > 0.05 ||
      Math.abs(s.connections - 1) > 0.05 ||
      Math.abs(s.stability - 1) > 0.05
    );
  });

  axisLabel(axis: ValueAxis | null | undefined): string {
    return axis ? AXIS_LABEL[axis] : '—';
  }

  constructor() {
    // Re-ask the model whenever the situation on screen changes: the hint is
    // context-dependent ("does a confirmed preference apply *here*?").
    effect(() => {
      const scenarios = this.store.scenarios();
      const recs = this.store.recommendations();
      if (scenarios.length === 0 && recs.length === 0) return;
      untracked(() => this.refresh(this.contextFromScenarios()));
    });
  }

  /** Situation proxies in the backend model's vocabulary (same derivation the
   *  strategy cards and the rationale snapshot use). */
  private contextFromScenarios(): OperatorContext {
    const s = this.store.scenarios().find((x) => x.isBaseline) ?? this.store.scenarios()[0];
    if (!s) return {};
    const meanDelay = s.kpiDeltas?.meanDelay;
    const done = s.kpiDeltas?.done;
    const deadlocks = s.kpiDeltas?.deadlocks;
    return {
      connection_critical: done != null && done < 0,
      low_delay: meanDelay != null && meanDelay <= 0,
      low_ripple: deadlocks != null && deadlocks <= 0,
    };
  }

  /** Ask the model whether a preference applies to the situation on screen. */
  refresh(context: OperatorContext = {}): void {
    this.model.adjustment(context).subscribe({
      next: (adj) => this.adjustment.set(adj),
      error: () => this.adjustment.set(null),
    });
  }

  /** Hand the inferred reward weights to the Director's dials (opt-in). */
  applySuggestedWeights(): void {
    const weights: DirectorWeights | null = this.suggestedWeights();
    const session = this.store.session();
    if (!weights || !session || this.applying()) return;

    this.applying.set(true);
    this.api.setDirectorWeights(session.id, weights, true).subscribe({
      next: () => {
        this.applying.set(false);
        this.applied.set(true);
      },
      error: () => this.applying.set(false),
    });
  }
}
