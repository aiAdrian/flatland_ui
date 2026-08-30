import {
  CUSTOM_ELEMENTS_SCHEMA,
  Component,
  EventEmitter,
  Input,
  Output,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';

import { TrainId } from '../../core/combined-actions-package';
import { CaPkgTrainChipComponent } from './train-chip.component';

/**
 * Move the item at `from` so it ends up at index `to`.
 *
 * Local to the sequence component: reordering is a UI concern, and the algorithm
 * modules deliberately know nothing about how an order was arrived at.
 */
export function moveTrain(
  order: readonly TrainId[],
  from: number,
  to: number,
): TrainId[] {
  const next = [...order];
  if (from < 0 || from >= next.length) return next;
  const target = Math.max(0, Math.min(to, next.length));
  const [moved] = next.splice(from, 1);
  // Removing the item first shifts every later index down by one.
  next.splice(target > from ? target - 1 : target, 0, moved);
  return next;
}

/**
 * The editable train order: drag a chip sideways, drop it where the marker shows.
 *
 * Native HTML5 drag-and-drop rather than a library — the widget needs one axis
 * and one list, and a dependency for that would be the larger cost. The drop
 * target is tracked per chip half (left of the midpoint inserts before it, right
 * inserts after), which avoids measuring the container and works the same at any
 * zoom level.
 *
 * Keyboard is a first-class path, not an afterthought: a chip is focusable and
 * Alt+Arrow moves it. Drag-and-drop alone would make the mode unusable without a
 * mouse, and it also gives the reorder logic a deterministic route for tests.
 */
@Component({
  selector: 'app-ca-pkg-sequence',
  standalone: true,
  imports: [CommonModule, CaPkgTrainChipComponent],
  templateUrl: './train-sequence.component.html',
  styleUrl: './train-sequence.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class CaPkgTrainSequenceComponent {
  @Input({ required: true }) set order(value: readonly TrainId[]) {
    this._order.set([...value]);
  }
  /** The AI's order, to mark which chips the dispatcher moved. */
  @Input() set aiOrder(value: readonly TrainId[]) {
    this._aiOrder.set([...value]);
  }
  /** Locked after the action was applied. */
  @Input() disabled = false;

  @Output() readonly reorder = new EventEmitter<TrainId[]>();

  private readonly _order = signal<TrainId[]>([]);
  private readonly _aiOrder = signal<TrainId[]>([]);

  readonly items = computed(() => this._order());
  readonly dragIndex = signal<number | null>(null);
  /** Index the dragged chip would be inserted at, or null while not dragging. */
  readonly dropIndex = signal<number | null>(null);

  movedFromAi(train: TrainId, index: number): boolean {
    const ai = this._aiOrder();
    if (!ai.length) return false;
    const original = ai.indexOf(train);
    return original >= 0 && original !== index;
  }

  label(train: TrainId, index: number): string {
    return `${train}, Position ${index + 1} von ${this.items().length}. `
      + 'Mit Alt und Pfeiltasten verschieben.';
  }

  // ── drag and drop ────────────────────────────────────────────────────────

  startDrag(index: number, event: DragEvent): void {
    if (this.disabled) return;
    this.dragIndex.set(index);
    this.dropIndex.set(index);
    event.dataTransfer?.setData('text/plain', String(index));
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
  }

  /** Left half of a chip inserts before it, right half after it. */
  hoverChip(index: number, event: DragEvent): void {
    if (this.dragIndex() === null) return;
    event.preventDefault();
    const target = event.currentTarget as HTMLElement | null;
    if (!target) return;
    const box = target.getBoundingClientRect();
    const after = event.clientX > box.left + box.width / 2;
    this.dropIndex.set(after ? index + 1 : index);
  }

  hoverEnd(event: DragEvent): void {
    if (this.dragIndex() === null) return;
    event.preventDefault();
    this.dropIndex.set(this.items().length);
  }

  /** Keeps the browser from rejecting the drop before it reaches us. */
  allowDrop(event: DragEvent): void {
    if (this.dragIndex() === null) return;
    event.preventDefault();
  }

  drop(event: DragEvent): void {
    event.preventDefault();
    const from = this.dragIndex();
    const to = this.dropIndex();
    this.endDrag();
    if (from === null || to === null) return;
    this.commit(moveTrain(this.items(), from, to));
  }

  endDrag(): void {
    this.dragIndex.set(null);
    this.dropIndex.set(null);
  }

  // ── keyboard ─────────────────────────────────────────────────────────────

  onKey(index: number, event: KeyboardEvent): void {
    if (this.disabled || !event.altKey) return;
    const delta =
      event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0;
    if (delta === 0) return;
    event.preventDefault();
    const target = index + delta;
    if (target < 0 || target >= this.items().length) return;
    // moveTrain takes an insertion index; moving right needs one extra step
    // because the item is removed before it is re-inserted.
    this.commit(moveTrain(this.items(), index, delta > 0 ? target + 1 : target));
  }

  private commit(next: TrainId[]): void {
    this._order.set(next);
    this.reorder.emit(next);
  }
}
