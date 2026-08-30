import { Injectable } from '@angular/core';
import { ImpactPrediction, ImpactPredictor, MOCK_IMPACT_PREDICTOR } from './impact-prediction';

/**
 * The seam between the Combined Actions widget and whatever computes impact.
 *
 * Today it wraps the deterministic mock (`impact-prediction.ts`) and adds the
 * short latency a real re-solve would have, so the UI is already written against
 * an asynchronous predictor. Swapping in the real thing — a PP/CBS re-solve on
 * the human's priority order, per `AI4REALNET/flatland-blackbox` — means
 * providing a different `ImpactPredictor` (or overriding `predict()` to call the
 * backend); no component changes.
 */
@Injectable({ providedIn: 'root' })
export class ImpactPredictionService {
  /** Swap this to change where predictions come from. */
  private predictor: ImpactPredictor = MOCK_IMPACT_PREDICTOR;

  /** Simulated re-solve latency (ms) — the window the card shows
   *  "Updating prediction…". Deterministic per order so the demo is repeatable. */
  private static readonly MIN_LATENCY_MS = 300;
  private static readonly MAX_LATENCY_MS = 600;

  /** Install a different predictor (real solver, HTTP client, test double). */
  use(predictor: ImpactPredictor): void {
    this.predictor = predictor;
  }

  /** Synchronous prediction — used for the AI baseline, which needs no
   *  "updating" state because the operator did not just change anything. */
  predictNow(trainOrder: readonly string[]): ImpactPrediction {
    return this.predictor.predict(trainOrder);
  }

  /** Prediction as the real thing would arrive: after a short delay. */
  predict(trainOrder: readonly string[]): Promise<ImpactPrediction> {
    const result = this.predictor.predict(trainOrder);
    return new Promise((resolve) =>
      setTimeout(() => resolve(result), this.latencyFor(trainOrder)),
    );
  }

  /** Stable per-order latency inside the 300–600 ms band. */
  private latencyFor(trainOrder: readonly string[]): number {
    const key = trainOrder.join('>');
    let h = 0x811c9dc5;
    for (let i = 0; i < key.length; i++) {
      h ^= key.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    const span = ImpactPredictionService.MAX_LATENCY_MS - ImpactPredictionService.MIN_LATENCY_MS;
    return ImpactPredictionService.MIN_LATENCY_MS + ((h >>> 0) % (span + 1));
  }
}
