import { Component, Input } from '@angular/core';
import { ImpactConfidence, ImpactPrediction } from '../../../../core/combined-actions/impact-prediction';

/** The transient "14 → 9 min" readout shown right after a recalculation. */
export interface ImpactDelta {
  from: number;
  to: number;
}

/**
 * The predicted consequence of one dispatch order.
 *
 * Presentational: it renders whatever prediction it is handed and never
 * computes one. The recalculation lifecycle (updating → settled → delta) is the
 * card's, so this component stays reusable for any predicted impact.
 */
@Component({
  selector: 'app-impact-metrics',
  standalone: true,
  templateUrl: './impact-metrics.component.html',
  styleUrl: './impact-metrics.component.scss',
})
export class ImpactMetricsComponent {
  /** Impact of the order currently on the card (AI's or human-modified). */
  @Input() prediction: ImpactPrediction | null = null;
  /** Impact of the untouched AI order. Only rendered once `modified` is true —
   *  an unmodified card would just show the same number twice. */
  @Input() aiBaseline: ImpactPrediction | null = null;
  /** A recalculation is in flight. */
  @Input() updating = false;
  /** The human has changed the AI's order. */
  @Input() modified = false;
  /** Brief before → after readout; null once it has faded. */
  @Input() delta: ImpactDelta | null = null;

  /** Planned transfers the shown order keeps, of the ones it can affect.
   *  `total` 0 means the scenario has no transfers among these trains — the
   *  figure is then hidden rather than shown as a meaningless 0/0. */
  @Input() transfersKept = 0;

  @Input() transfersTotal = 0;

  /** The AI order's kept count, for the comparison line once modified. */
  @Input() aiTransfersKept: number | null = null;

  readonly confidenceLabel: Record<ImpactConfidence, string> = {
    high: 'High',
    medium: 'Medium',
    low: 'Low',
  };
}
