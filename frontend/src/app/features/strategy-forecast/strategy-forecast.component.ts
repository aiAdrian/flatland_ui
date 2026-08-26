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
 * - **Director:** the subject is the strategy *focus* published by the A/B/C
 *   tiles, not a policy. Reading the scenario options there was plainly wrong —
 *   the baseline option is not even the plan that drives under the Director
 *   planner — so that fallback is off in Director, and the widget reads the
 *   focus from the store itself. The `signals`/`subject` inputs stay as an
 *   override, but nothing has to pass them: the widget behaves the same whether
 *   it renders from the Director slot in AppComponent or from a panel the
 *   operator dragged in the layout designer.
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
  /** Override: projects these signals instead of the resolved subject. */
  @Input() set signals(value: ForecastSignals | null) {
    this._signals.set(value);
  }
  /** Headline for the subject being projected (e.g. the strategy focus). */
  @Input() subject: string | null = null;
  /** What the projection is derived from, for the honesty note. */
  @Input() derivedFrom: string | null = null;

  private readonly _signals = signal<ForecastSignals | null>(null);

  store = inject(SessionStore);

  private readonly isDirector = computed(() => this.store.interactionMode() === 'director');

  /** The strategy focus published by the A/B/C tiles, in Director only. */
  private readonly focusOutlook = computed(() =>
    this.isDirector() ? this.store.directorFocusOutlook() : null,
  );

  /** The signals actually projected: the input override, else the focus. */
  private readonly activeSignals = computed<ForecastSignals | null>(
    () => this._signals() ?? this.focusOutlook()?.signals ?? null,
  );

  /** The option the forecast describes: the recommended one, else the baseline.
   *  Director has no such fallback — see the class comment. */
  readonly option = computed(() => {
    if (this.isDirector()) return undefined;
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
    // With a signal subject there is no option to read leftover deadlocks
    // from, so system load is the trains actually running late.
    if (this.activeSignals() !== null) return this.delayedTrains();
    return openProblemsFrom(this.option(), this.delayedTrains());
  });

  readonly forecast = computed(() => {
    const signals = this.activeSignals();
    if (signals) return buildForecastFromSignals(signals, this.openProblems());
    return buildStrategyForecast(this.option(), this.openProblems());
  });

  readonly subjectLabel = computed(
    () => this.subject ?? this.focusOutlook()?.subject ?? this.option()?.title ?? '',
  );

  readonly noteText = computed(() => {
    if (this.derivedFrom) return this.derivedFrom;
    return this.activeSignals() !== null
      ? 'Regelbasierte Projektion, keine Neusimulation.'
      : 'Regelbasierte Projektion aus den KPI-Deltas dieser Option — keine Neusimulation der nächsten 30 Minuten.';
  });

  readonly hasData = computed(() => this.activeSignals() !== null || this.option() != null);

  /** Director, but no strategy committed yet. The widget says what it is waiting
   *  for instead of collapsing to an empty box — this used to live in the
   *  AppComponent template, where the panel path could not reach it. */
  readonly awaitingStrategy = computed(() => !this.hasData() && this.isDirector());

  /** Headline for the horizon note — green while we can see 30 min ahead. */
  readonly horizonOk = computed(() => this.forecast().horizonMinutes >= 30);
}
