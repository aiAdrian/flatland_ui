import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, Input, computed, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import {
  ForecastSignals,
  buildForecastFromSignals,
  buildStrategyForecast,
  openProblemsFrom,
} from '../../core/strategy-forecast';

/**
 * Strategy Impact Forecast — the "was passiert in der nächsten halben Stunde?"
 * table from the Director-Mode prototype: Now / +10 / +20 / +30 min for the
 * conflict, the connections and the delay side effect.
 *
 * Two subjects, one visual:
 *
 * - **Default (Recommendation / Co-Learning):** it projects the recommended
 *   (or baseline) scenario option from that option's KPI deltas.
 * - **Explicit (Director):** the caller passes `signals` and a `subject` label,
 *   because there the thing being decided is a strategy *focus*, not a policy.
 *   Reading the scenario options there was plainly wrong — the baseline option
 *   is a policy that is not even the one driving under the Director planner.
 *
 * It stays explicit about its own limits: a rule-based projection, whose
 * reliable horizon shrinks as more problems pile up.
 */
@Component({
  selector: 'app-strategy-forecast',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './strategy-forecast.component.html',
  styleUrl: './strategy-forecast.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class StrategyForecastComponent {
  /** Explicit subject: projects these signals instead of a scenario option. */
  @Input() set signals(value: ForecastSignals | null) {
    this._signals.set(value);
  }
  /** Headline for the subject being projected (e.g. the strategy focus). */
  @Input() subject: string | null = null;
  /** What the projection is derived from, for the honesty note. */
  @Input() derivedFrom: string | null = null;

  private readonly _signals = signal<ForecastSignals | null>(null);

  store = inject(SessionStore);

  /** The option the forecast describes: the recommended one, else the baseline. */
  readonly option = computed(() => {
    const scenarios = this.store.scenarios();
    return (
      scenarios.find((s) => s.isRecommended) ??
      scenarios.find((s) => s.isBaseline) ??
      scenarios[0]
    );
  });

  /** Trains currently late — part of the "how loaded is the system" measure. */
  private readonly delayedTrains = computed(
    () => this.store.agents().filter((a) => (a.delay ?? 0) > 0).length,
  );

  readonly openProblems = computed(() => {
    // With an explicit subject there is no option to read leftover deadlocks
    // from, so system load is the trains actually running late.
    if (this._signals() !== null) return this.delayedTrains();
    return openProblemsFrom(this.option(), this.delayedTrains());
  });

  readonly forecast = computed(() => {
    const explicit = this._signals();
    if (explicit) return buildForecastFromSignals(explicit, this.openProblems());
    return buildStrategyForecast(this.option(), this.openProblems());
  });

  readonly subjectLabel = computed(() => this.subject ?? this.option()?.title ?? '');

  readonly noteText = computed(
    () =>
      this.derivedFrom ??
      'Regelbasierte Projektion aus den KPI-Deltas dieser Option — keine Neusimulation der nächsten 30 Minuten.',
  );

  readonly hasData = computed(() => this._signals() !== null || this.option() != null);

  /** Headline for the horizon note — green while we can see 30 min ahead. */
  readonly horizonOk = computed(() => this.forecast().horizonMinutes >= 30);
}
