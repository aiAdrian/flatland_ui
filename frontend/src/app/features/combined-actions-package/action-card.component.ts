import {
  CUSTOM_ELEMENTS_SCHEMA,
  Component,
  DestroyRef,
  EventEmitter,
  Input,
  Output,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';

import {
  ConflictWindow,
  EvaluatedAction,
  PREDICTION_LATENCY_MS,
  PlanStep,
  SimulationResult,
  TrainId,
  evaluateModifiedAction,
  planSteps,
} from '../../core/combined-actions-package';
import { CaPkgImpactMetricsComponent, PredictionStatus } from './impact-metrics.component';
import { CaPkgTrainSequenceComponent } from './train-sequence.component';

/**
 * One Combined Action: the sequence, its simulated consequence, the impact detail,
 * and the confirmation.
 *
 * Three states in order — propose, review, confirm. The middle one is not
 * decoration: an action that reorders six trains has effects on trains nobody
 * dispatched, and confirming without having been able to look at those would be
 * the opposite of human-in-the-loop. Review is therefore a step the operator opens
 * on the card, not a dialog that interrupts them.
 *
 * Sequence state and prediction state are separate signals. The order changes the
 * instant a chip is dropped — the dispatcher must never wait to see what they did
 * — while the re-simulation goes through a pending state and lands afterwards.
 * A confirmed action that is edited afterwards loses its confirmation, because it
 * is no longer the action that was confirmed.
 */
@Component({
  selector: 'app-ca-pkg-card',
  standalone: true,
  imports: [CommonModule, CaPkgTrainSequenceComponent, CaPkgImpactMetricsComponent],
  templateUrl: './action-card.component.html',
  styleUrl: './action-card.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class CaPkgActionCardComponent {
  private readonly destroyRef = inject(DestroyRef);

  @Input({ required: true }) set proposal(value: EvaluatedAction) {
    this._ai.set(value);
    this._current.set(value);
    this._order.set([...value.action.sequence]);
    this._status.set('ready');
    this._previousMinutes.set(null);
    this._armed.set(false);
    this._reviewOpen.set(false);
    this._planOpen.set(false);
  }
  @Input({ required: true }) set window(value: ConflictWindow) {
    this._window.set(value);
  }
  @Input({ required: true }) set baseline(value: SimulationResult) {
    this._baseline.set(value);
  }

  /**
   * Confirmation is owned by the container, not the card: exactly one action may
   * be chosen, so no card can decide its own state without knowing about the
   * others.
   */
  @Input() set chosen(value: boolean) {
    this._chosen.set(value);
    if (value) this._armed.set(false);
  }
  /** Another action was chosen, so this one is out of play. */
  @Input() set locked(value: boolean) {
    this._locked.set(value);
    if (value) this._armed.set(false);
  }

  @Output() readonly confirmed = new EventEmitter<{
    evaluated: EvaluatedAction;
    modified: boolean;
  }>();
  @Output() readonly revoked = new EventEmitter<void>();
  /** Raised when the operator turns their attention to this action. */
  @Output() readonly focused = new EventEmitter<EvaluatedAction>();

  /** This card is the one the map is currently showing. */
  @Input() showingOnMap = false;

  private readonly _ai = signal<EvaluatedAction | null>(null);
  private readonly _current = signal<EvaluatedAction | null>(null);
  private readonly _window = signal<ConflictWindow | null>(null);
  private readonly _baseline = signal<SimulationResult | null>(null);
  private readonly _order = signal<TrainId[]>([]);
  private readonly _status = signal<PredictionStatus>('ready');
  private readonly _previousMinutes = signal<number | null>(null);
  private readonly _chosen = signal(false);
  private readonly _locked = signal(false);
  /** Armed = the operator pressed Confirm and the final question is showing. */
  private readonly _armed = signal(false);
  private readonly _reviewOpen = signal(false);
  private readonly _planOpen = signal(false);

  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    this.destroyRef.onDestroy(() => this.clearTimer());
  }

  readonly ai = computed(() => this._ai());
  readonly current = computed(() => this._current());
  readonly order = computed(() => this._order());
  readonly status = computed(() => this._status());
  readonly previousMinutes = computed(() => this._previousMinutes());
  readonly isConfirmed = computed(() => this._chosen());
  readonly isLocked = computed(() => this._locked());
  readonly isArmed = computed(() => this._armed());
  readonly reviewOpen = computed(() => this._reviewOpen());
  readonly planOpen = computed(() => this._planOpen());
  readonly baselineDelay = computed(() => this._baseline()?.totalDelay ?? 0);
  /** Nothing can be edited once this action is chosen or another one is. */
  readonly readOnly = computed(() => this._chosen() || this._locked());

  /**
   * The plan, train by train: who goes first, who waits behind whom, and what it
   * costs each of them. Covers the whole passing order, because the trains that
   * were never dispatched are the ones the operator most needs to see.
   */
  readonly plan = computed<PlanStep[]>(() => {
    const window = this._window();
    const current = this._current();
    const baseline = this._baseline();
    if (!window || !current || !baseline) return [];
    return planSteps(window, current.action, current.result, baseline);
  });

  readonly modified = computed(() => {
    const ai = this._ai();
    if (!ai) return false;
    const order = this._order();
    return (
      order.length !== ai.action.sequence.length ||
      order.some((train, i) => train !== ai.action.sequence[i])
    );
  });

  readonly badges = computed<string[]>(() => {
    const ai = this._ai();
    if (!ai) return [];
    const out: string[] = [];
    if (ai.recommended) out.push('Empfohlen von KI');
    if (this.modified()) out.push('Vom Dispatcher geändert');
    return out;
  });

  /** Trains that lose time although nobody dispatched them. */
  readonly sideEffects = computed(() => {
    const current = this._current();
    if (!current) return [];
    const controlled = new Set(current.metrics.controlled);
    return current.metrics.affected
      .filter((train) => !controlled.has(train))
      .map((train) => ({ train, impact: current.metrics.trainImpacts[train] ?? 0 }))
      .sort((a, b) => b.impact - a.impact);
  });

  readonly controlledImpacts = computed(() => {
    const current = this._current();
    if (!current) return [];
    return current.metrics.controlled.map((train) => ({
      train,
      impact: current.metrics.trainImpacts[train] ?? 0,
    }));
  });

  /**
   * Any interaction with the card counts as turning attention to it, so the map
   * follows without the operator having to aim at a separate "show on map" control.
   */
  takeFocus(): void {
    const current = this._current();
    if (current) this.focused.emit(current);
  }

  toggleReview(): void {
    this._reviewOpen.update((open) => !open);
    this.takeFocus();
  }

  togglePlan(): void {
    this._planOpen.update((open) => !open);
    this.takeFocus();
  }

  onReorder(next: TrainId[]): void {
    this._order.set(next);
    // An edit invalidates a pending confirmation: the question was about the old
    // sequence.
    this._armed.set(false);
    this.resimulate();
  }

  reset(): void {
    const ai = this._ai();
    if (!ai) return;
    this._order.set([...ai.action.sequence]);
    this._armed.set(false);
    this.resimulate();
  }

  /** First press: ask. The action is not chosen yet. */
  arm(): void {
    if (this.readOnly() || this._status() === 'updating') return;
    this._armed.set(true);
  }

  cancelArm(): void {
    this._armed.set(false);
  }

  /** Second press: commit. Only now does the container hear about it. */
  confirmFinal(): void {
    const current = this._current();
    if (!current || !this._armed()) return;
    this._armed.set(false);
    this.confirmed.emit({ evaluated: current, modified: this.modified() });
  }

  /** Give the choice back, so another action can be taken instead. */
  revoke(): void {
    this.revoked.emit();
  }

  /**
   * Re-simulate the dispatcher's sequence against the same state.
   *
   * Deliberately not a new candidate generation: they edited *this* action, and
   * regenerating would answer a question nobody asked. The short pending state
   * makes the causal chain readable — I changed it, the system evaluated it.
   */
  private resimulate(): void {
    const window = this._window();
    const ai = this._ai();
    if (!window || !ai) return;
    this.clearTimer();
    this._previousMinutes.set(this._current()?.metrics.totalDelayReduction ?? null);
    this._status.set('updating');
    const order = this._order();
    this.timer = setTimeout(() => {
      this._current.set(evaluateModifiedAction(window, ai.action, order));
      this._status.set('ready');
      this.timer = null;
    }, PREDICTION_LATENCY_MS);
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}
