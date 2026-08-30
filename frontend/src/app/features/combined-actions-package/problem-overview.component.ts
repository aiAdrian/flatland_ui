import { CUSTOM_ELEMENTS_SCHEMA, Component, computed } from '@angular/core';
import { CommonModule } from '@angular/common';

import { detectConflict, simulateBaseline } from '../../core/combined-actions-package';

/**
 * What is wrong right now, before any action is considered.
 *
 * The cards below answer "what should I do"; this answers "what am I looking at".
 * Without it the dispatcher is asked to pick between three interventions against a
 * situation they have to reconstruct from a single line of text — and the minutes
 * a card promises to save mean nothing without knowing who is currently late and
 * by how much.
 *
 * Read-only and derived: the same conflict fixture and the same baseline run the
 * candidates are measured against, so the numbers here and on the cards cannot
 * disagree.
 */
@Component({
  selector: 'app-problem-overview',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './problem-overview.component.html',
  styleUrl: './problem-overview.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ProblemOverviewComponent {
  readonly window = computed(() => detectConflict());
  readonly baseline = computed(() => simulateBaseline(this.window()));

  /** Trains in the order the timetable sends them, with what it costs them. */
  readonly rows = computed(() => {
    const w = this.window();
    const b = this.baseline();
    return w.baselineOrder.map((train, index) => {
      const facts = w.trains.find((t) => t.id === train)!;
      return {
        train,
        service: facts.service,
        position: index + 1,
        entryDelay: facts.entryDelay,
        headway: facts.headway,
        delay: b.outcomes[train]?.delay ?? 0,
      };
    });
  });

  /** The worst-off train — the one the conflict is really about. */
  readonly worst = computed(() =>
    [...this.rows()].sort((a, b) => b.delay - a.delay)[0],
  );

  readonly trainsLate = computed(() => this.rows().filter((r) => r.delay > 0).length);
}
