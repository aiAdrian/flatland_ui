import { CUSTOM_ELEMENTS_SCHEMA, Component, Input, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import { CONFLICT_WINDOW, TrainId, trainFacts } from '../../core/combined-actions-package';

/**
 * One train in a sequence, as a compact chip.
 *
 * Presentational only: it neither drags itself nor knows its position. The
 * sequence owns the interaction, because an insertion point is a property of the
 * list and not of any single chip.
 */
@Component({
  selector: 'app-ca-pkg-chip',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './train-chip.component.html',
  styleUrl: './train-chip.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class CaPkgTrainChipComponent {
  @Input({ required: true }) set train(value: TrainId) {
    this._train.set(value);
  }
  /** Dimmed while it is the one being dragged. */
  @Input() dragging = false;
  /** Marked when the dispatcher moved this train away from the AI's position. */
  @Input() moved = false;

  private readonly _train = signal<TrainId>('');

  readonly id = computed(() => this._train());
  readonly title = computed(() => {
    const train = this._train();
    if (!train) return '';
    const f = trainFacts(CONFLICT_WINDOW, train);
    return `${train} · ${f.service} · ${f.entryDelay} min Verspätung · belegt den Abschnitt ${f.headway} min`;
  });
}
