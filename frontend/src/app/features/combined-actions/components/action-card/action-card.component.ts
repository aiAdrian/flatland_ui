import { Component, EventEmitter, Input, OnDestroy, OnInit, Output, computed, inject, signal } from '@angular/core';
import { ActionPackage } from '../../../../core/combined-actions/action-packages';
import { ImpactPrediction } from '../../../../core/combined-actions/impact-prediction';
import { ImpactPredictionService } from '../../../../core/combined-actions/impact-prediction.service';
import { TrainSequenceComponent } from '../train-sequence/train-sequence.component';
import { ImpactDelta, ImpactMetricsComponent } from '../impact-metrics/impact-metrics.component';

/** How the card frames its package — the mode's Decision-Support framing
 *  (spec §3), passed down from the panel's `modeBehavior`. */
export type ActionFraming = 'recommended' | 'neutral' | 'none';

/**
 * One version of a package's dispatch order: the AI's proposal, or a variant
 * the dispatcher built from it.
 *
 * Versions are kept side by side rather than overwritten. A dispatcher who
 * drags a train wants to see what their change *did*, and to be able to go back
 * — an in-place edit with a Reset button answers neither question once a second
 * change lands on top of the first.
 */
export interface ActionVersion {
  id: string;
  label: string;
  order: string[];
  origin: 'ai' | 'human';
  prediction: ImpactPrediction | null;
  updating: boolean;
  delta: ImpactDelta | null;
}

/** What the panel needs to preview this card's active version in the other views. */
export interface ActivePreview {
  packageId: string;
  label: string;
  order: readonly string[];
  modified: boolean;
}

/**
 * One combined action: an AI-proposed multi-train dispatch order, editable in
 * place, with the consequence of the current order beside it.
 *
 * Sequence state (each version's `order`) and prediction state (`prediction` /
 * `updating` / `delta`) stay separate, so "your order, prediction pending" is
 * representable — that is the exact moment the widget exists to show.
 *
 * `pkg.aiOrder` is never mutated; it lives on as the `ai` version.
 */
@Component({
  selector: 'app-action-card',
  standalone: true,
  imports: [TrainSequenceComponent, ImpactMetricsComponent],
  templateUrl: './action-card.component.html',
  styleUrl: './action-card.component.scss',
})
export class ActionCardComponent implements OnInit, OnDestroy {
  @Input({ required: true }) pkg!: ActionPackage;
  @Input() framing: ActionFraming = 'recommended';
  /** False in Director: read-only supervision, no reorder and no Apply. */
  @Input() editable = true;
  /**
   * Collapsed cards show only their headline.
   *
   * Three open cards plus the plot ran to 1220 px in a 509 px column — nothing
   * was fully visible and the operator scrolled to compare two things that
   * should sit side by side. One card open at a time is the control-room
   * answer: the whole set stays on screen, the one being worked on is whole.
   */
  @Input() expanded = true;

  /** Raised whenever the version on screen changes, so the panel can push the
   *  consequence overlay to the map and the Marey. */
  @Output() activeChanged = new EventEmitter<ActivePreview>();

  /** The operator wants this card open. */
  @Output() expandRequested = new EventEmitter<string>();

  private readonly predictor = inject(ImpactPredictionService);

  readonly versions = signal<ActionVersion[]>([]);
  readonly activeId = signal<string>('ai');

  /** The Apply confirmation, shown briefly in place of the button. */
  readonly applied = signal<string | null>(null);

  /** Discards a prediction that resolves after a newer one was requested. */
  private token = 0;
  private deltaTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private appliedTimer: ReturnType<typeof setTimeout> | null = null;

  private static readonly DELTA_MS = 2400;
  private static readonly APPLIED_MS = 2600;

  readonly active = computed<ActionVersion | null>(
    () => this.versions().find((v) => v.id === this.activeId()) ?? null,
  );

  readonly aiVersion = computed<ActionVersion | null>(
    () => this.versions().find((v) => v.id === 'ai') ?? null,
  );

  readonly variants = computed(() => this.versions().filter((v) => v.origin === 'human'));

  /** True once the operator is looking at something other than the AI proposal. */
  readonly modified = computed(() => this.activeId() !== 'ai');

  /** Shown once a variant exists: the card now carries competing answers and
   *  the operator has to say which one they are keeping. */
  readonly hasChoice = computed(() => this.variants().length > 0);

  /** The card was the AI's pick — kept after a human edit, because "this is the
   *  one the AI recommended" stays true even when the sequence no longer is.
   *  A getter, not a `computed`: `framing` is a plain input, so a computed would
   *  never invalidate when the interaction mode changes under it. */
  get wasRecommended(): boolean {
    return this.framing === 'recommended' && this.pkg.recommended;
  }

  /** Director marks the package the AI is executing instead of recommending one. */
  get aiExecuting(): boolean {
    return this.framing === 'none' && this.pkg.recommended;
  }

  ngOnInit(): void {
    const baseline = this.predictor.predictNow(this.pkg.aiOrder);
    this.versions.set([
      {
        id: 'ai',
        label: 'AI proposal',
        order: [...this.pkg.aiOrder],
        origin: 'ai',
        prediction: baseline,
        updating: false,
        delta: null,
      },
    ]);
    this.emitActive();
  }

  ngOnDestroy(): void {
    for (const timer of this.deltaTimers.values()) clearTimeout(timer);
    if (this.appliedTimer) clearTimeout(this.appliedTimer);
  }

  /**
   * A human reorder.
   *
   * Editing the AI proposal **forks a new variant** rather than overwriting it,
   * so both answers stay on the card and the operator can compare them before
   * committing. Editing a variant refines that variant — otherwise every single
   * drag inside one idea would spawn another version and the comparison would
   * drown in near-duplicates.
   */
  onReorder(next: string[]): void {
    if (!this.editable) return;
    this.clearApplied();
    // Dragging is an edit, and an edit has a "what changed" to show — so the
    // card opens itself rather than making the operator find the chevron.
    if (!this.expanded) this.expandRequested.emit(this.pkg.id);

    if (this.activeId() === 'ai') {
      const id = `v${this.variants().length + 1}`;
      const forked: ActionVersion = {
        id,
        label: `Variant ${this.variants().length + 1}`,
        order: next,
        origin: 'human',
        prediction: this.aiVersion()?.prediction ?? null,
        updating: false,
        delta: null,
      };
      this.versions.update((list) => [...list, forked]);
      this.activeId.set(id);
    } else {
      this.patch(this.activeId(), { order: next });
    }

    this.recalculate(this.activeId());
    this.emitActive();
  }

  /** Switch which version the card is showing (and would apply). */
  select(id: string): void {
    if (this.activeId() === id) return;
    this.activeId.set(id);
    this.clearApplied();
    this.emitActive();
  }

  /** Throw a variant away. The AI proposal can never be discarded. */
  discard(id: string): void {
    if (!this.editable || id === 'ai') return;
    this.versions.update((list) => list.filter((v) => v.id !== id));
    if (this.activeId() === id) this.activeId.set('ai');
    this.clearApplied();
    this.emitActive();
  }

  /** Go back to the AI proposal without losing the variants built so far. */
  reset(): void {
    this.select('ai');
  }

  /** The header toggles the card's detail. */
  onHeaderClick(): void {
    this.expandRequested.emit(this.pkg.id);
  }

  apply(): void {
    if (!this.editable) return;
    this.applied.set(this.active()?.label ?? null);
    if (this.appliedTimer) clearTimeout(this.appliedTimer);
    this.appliedTimer = setTimeout(() => this.applied.set(null), ActionCardComponent.APPLIED_MS);
  }

  /** How far each train moved relative to the AI proposal — the "what changed"
   *  a variant has to answer. Negative = dispatched earlier. */
  shiftFromAi(train: string): number {
    const ai = this.aiVersion();
    const current = this.active();
    if (!ai || !current || current.origin === 'ai') return 0;
    const from = ai.order.indexOf(train);
    const to = current.order.indexOf(train);
    if (from < 0 || to < 0) return 0;
    return to - from;
  }

  /**
   * The change, in words.
   *
   * Markers on the chips say *that* a train moved; a reader still has to
   * reconstruct the edit from four little arrows. One sentence naming the trains
   * and the direction is what makes the modification legible at a glance — and
   * it is the thing a study participant can read back to you.
   */
  readonly changeSummary = computed<string>(() => {
    const ai = this.aiVersion();
    const current = this.active();
    if (!ai || !current || current.origin === 'ai') return '';

    const moves: string[] = [];
    for (const train of current.order) {
      const shift = current.order.indexOf(train) - ai.order.indexOf(train);
      if (shift === 0) continue;
      const places = Math.abs(shift) === 1 ? 'place' : 'places';
      moves.push(`${train} ${Math.abs(shift)} ${places} ${shift < 0 ? 'earlier' : 'later'}`);
    }
    return moves.length ? `You moved ${moves.join(', ')}.` : '';
  });

  /** Ask the predictor about the order now on version `id`. */
  private recalculate(id: string): void {
    const token = ++this.token;
    const version = this.versions().find((v) => v.id === id);
    if (!version) return;
    const before = version.prediction?.delayReductionMin ?? null;

    this.patch(id, { updating: true, delta: null });
    const timer = this.deltaTimers.get(id);
    if (timer) clearTimeout(timer);

    void this.predictor.predict(version.order).then((next) => {
      if (token !== this.token) return; // superseded by a newer reorder
      const changed = before !== null && before !== next.delayReductionMin;
      this.patch(id, {
        updating: false,
        prediction: next,
        delta: changed ? { from: before as number, to: next.delayReductionMin } : null,
      });
      if (changed) {
        this.deltaTimers.set(
          id,
          setTimeout(() => {
            if (token === this.token) this.patch(id, { delta: null });
          }, ActionCardComponent.DELTA_MS),
        );
      }
    });
  }

  private patch(id: string, change: Partial<ActionVersion>): void {
    this.versions.update((list) => list.map((v) => (v.id === id ? { ...v, ...change } : v)));
  }

  private emitActive(): void {
    const current = this.active();
    if (!current) return;
    this.activeChanged.emit({
      packageId: this.pkg.id,
      label: current.origin === 'ai' ? this.pkg.label : `${this.pkg.label} · ${current.label}`,
      order: current.order,
      modified: current.origin === 'human',
    });
  }

  private clearApplied(): void {
    this.applied.set(null);
    if (this.appliedTimer) clearTimeout(this.appliedTimer);
  }
}
