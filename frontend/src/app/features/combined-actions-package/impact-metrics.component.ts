import { CUSTOM_ELEMENTS_SCHEMA, Component, Input, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import { ActionMetrics, ImpactConfidence } from '../../core/combined-actions-package';

/** Whether the number on screen is current or being recomputed. */
export type PredictionStatus = 'ready' | 'updating';

const CONFIDENCE_LABELS: Record<ImpactConfidence, string> = {
  high: 'Hoch',
  medium: 'Mittel',
  low: 'Niedrig',
};

/**
 * The simulated consequence of the sequence currently in the card.
 *
 * The AI's own number appears beside the current one only once the dispatcher has
 * changed something; before that the two are identical and the comparison would be
 * noise. The pending state is quiet on purpose — it says a number is being
 * recomputed, not that something went wrong.
 */
@Component({
  selector: 'app-ca-pkg-metrics',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './impact-metrics.component.html',
  styleUrl: './impact-metrics.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class CaPkgImpactMetricsComponent {
  @Input({ required: true }) set metrics(value: ActionMetrics) {
    this._metrics.set(value);
  }
  @Input({ required: true }) set aiMetrics(value: ActionMetrics) {
    this._ai.set(value);
  }
  /** Total delay of the do-nothing run, so the reduction has a reference. */
  @Input() baselineDelay = 0;
  @Input() status: PredictionStatus = 'ready';
  @Input() modified = false;
  @Input() set previousMinutes(value: number | null) {
    this._previous.set(value);
  }

  private readonly _metrics = signal<ActionMetrics | null>(null);
  private readonly _ai = signal<ActionMetrics | null>(null);
  private readonly _previous = signal<number | null>(null);

  readonly current = computed(() => this._metrics());
  readonly ai = computed(() => this._ai());

  readonly confidenceLabel = computed(() => {
    const m = this._metrics();
    return m ? CONFIDENCE_LABELS[m.confidence] : '';
  });

  /** "12 → 11", only while the change is fresh and actually a change. */
  readonly delta = computed(() => {
    const previous = this._previous();
    const m = this._metrics();
    if (previous === null || !m || previous === m.totalDelayReduction) return null;
    return `${previous} → ${m.totalDelayReduction}`;
  });
}
