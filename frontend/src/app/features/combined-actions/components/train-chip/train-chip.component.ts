import { Component, Input } from '@angular/core';
import { TrainCategory } from '../../../../core/combined-actions/action-packages';

/**
 * One train in a combined action's dispatch order.
 *
 * Purely presentational — it knows nothing about drag-and-drop or prediction.
 * The slot around it (train-sequence) owns the interaction.
 */
@Component({
  selector: 'app-train-chip',
  standalone: true,
  templateUrl: './train-chip.component.html',
  styleUrl: './train-chip.component.scss',
})
export class TrainChipComponent {
  @Input({ required: true }) train!: string;
  @Input() category: TrainCategory = 'regional';
  /** Position in the sequence, 1-based — shown so the order survives wrapping. */
  @Input() position = 0;
  /** The sequence is editable (chip looks grabbable). */
  @Input() interactive = false;
  /** This chip is the one currently being dragged. */
  @Input() dragging = false;
  /** Positions this train moved relative to the AI proposal. Negative = earlier,
   *  0 = unchanged (no marker). */
  @Input() shift = 0;
  /** Tighter chip for a narrow column, so four trains stay on one line. */
  @Input() compact = false;

  get shiftLabel(): string {
    return this.shift < 0 ? `▲${-this.shift}` : `▼${this.shift}`;
  }
}
