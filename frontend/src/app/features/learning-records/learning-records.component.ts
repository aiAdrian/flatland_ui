import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { LearningRecord } from '../../core/learning-store.service';
import { ReasoningItem } from '../../shared/ui/reasoning-list.component';
import { MetricChipComponent } from '../../shared/ui/metric-chip.component';
import { ScoreBadgeComponent } from '../../shared/ui/score-badge.component';
import { ReasoningListComponent } from '../../shared/ui/reasoning-list.component';

type MetricLevel = 'good' | 'fair' | 'low' | 'neutral';

/**
 * Workstream B Tier 1 — the Learning-Record cards (deck slide 5). Reads the
 * confirmed/one-off records from the store (proxied from `LearningStore`) and
 * renders each as a card **reusing the Phase-1 shared/ui primitives**:
 * `score-badge` (confirmation), `metric-chip` (the context trade-off profile),
 * `reasoning-list` (the "why"). No new visual primitives.
 *
 * Presentational wrapper: the primitives themselves take only `@Input`.
 */
@Component({
  selector: 'app-learning-records',
  standalone: true,
  imports: [CommonModule, MetricChipComponent, ScoreBadgeComponent, ReasoningListComponent],
  templateUrl: './learning-records.component.html',
  styleUrl: './learning-records.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class LearningRecordsComponent {
  store = inject(SessionStore);

  readonly records = computed(() => this.store.learningRecords());

  /** Split the joined rationale back into reasoning-list items. */
  reasoningFor(r: LearningRecord): ReasoningItem[] {
    if (!r.rationale) return [];
    return r.rationale
      .split('; ')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((label) => ({ title: label, detail: '' }));
  }

  /** Context trade-off profile as metric chips (only when a scenario backed it). */
  hasContext(r: LearningRecord): boolean {
    return r.context.hasScenario;
  }
  delayMetric(r: LearningRecord): { value: string; level: MetricLevel } {
    return {
      value: r.context.delayValue ?? '—',
      level: r.context.lowDelay ? 'good' : 'fair',
    };
  }
  connectionMetric(r: LearningRecord): { value: string; level: MetricLevel } {
    return {
      value: r.context.connectionValue ?? '—',
      level: r.context.connectionCritical ? 'low' : 'good',
    };
  }
  rippleMetric(r: LearningRecord): { value: string; level: MetricLevel } {
    return {
      value: r.context.rippleValue ?? '—',
      level: r.context.lowRipple ? 'good' : 'fair',
    };
  }

  /** score-badge: confirmed rule → 100/recommended; one-off → 50/active. */
  scoreFor(r: LearningRecord): number {
    return r.once ? 50 : 100;
  }
  stateFor(r: LearningRecord): 'recommended' | 'active' | 'neutral' {
    return r.once ? 'active' : 'recommended';
  }
  labelFor(r: LearningRecord): string {
    return r.once ? 'Einmal' : 'Bestätigt';
  }
}
