import {
  Component,
  ElementRef,
  EventEmitter,
  Injector,
  Input,
  Output,
  afterNextRender,
  computed,
  inject,
  signal,
} from '@angular/core';
import { TrainChipComponent } from '../train-chip/train-chip.component';
import { trainCategory } from '../../../../core/combined-actions/action-packages';

/**
 * The editable dispatch order of one combined action.
 *
 * Owns the reorder *interaction* only — never the order itself. The card above
 * holds the sequence state and re-emits it as `order`, which keeps sequence
 * state and prediction state separate (spec §7).
 *
 * Dragging is built on **pointer events**, not native HTML5 drag-and-drop.
 * HTML5 DnD is what `layout-designer` uses, but it is the wrong tool here: it
 * does not fire for touch at all, and its drag image cannot show the chip
 * sliding between its neighbours. Pointer events cover mouse, touch and pen
 * through one path. `←` / `→` on a focused chip is the keyboard equivalent.
 */
@Component({
  selector: 'app-train-sequence',
  standalone: true,
  imports: [TrainChipComponent],
  templateUrl: './train-sequence.component.html',
  styleUrl: './train-sequence.component.scss',
})
export class TrainSequenceComponent {
  @Input({ required: true }) order: readonly string[] = [];
  /** False in Director, where the widget is a read-only supervision surface. */
  @Input() editable = true;
  /** The AI's order, to mark how far each train has been moved from it.
   *  Empty (or identical to `order`) = nothing to mark. */
  @Input() referenceOrder: readonly string[] = [];
  /** Narrow-column mode: smaller chips and no "→" separators — the position
   *  numbers on the chips already carry the order. */
  @Input() compact = false;

  /** The new order after a human reorder. Only emitted when it actually changed. */
  @Output() reorder = new EventEmitter<string[]>();

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);

  /** Index of the chip being dragged; null when no drag is in flight. */
  readonly dragIndex = signal<number | null>(null);
  /** Gap the dragged chip would be inserted at (0…order.length). */
  readonly dropIndex = signal<number | null>(null);
  /** How far the dragged chip has travelled, so it follows the pointer. */
  readonly dragOffset = signal(0);

  readonly dragging = computed(() => this.dragIndex() !== null);

  /** Pointer travel before a press becomes a drag — below this it is a click,
   *  so tapping a chip still just focuses it. */
  private static readonly DRAG_THRESHOLD_PX = 4;

  private pointerId: number | null = null;
  private pressedIndex: number | null = null;
  private pressX = 0;

  categoryOf(train: string) {
    return trainCategory(train);
  }

  /** True when the insertion marker belongs in the gap before index `gap`. */
  isInsertAt(gap: number): boolean {
    return this.dragging() && this.dropIndex() === gap;
  }

  /** Pixel offset for the chip that is following the pointer. */
  offsetFor(index: number): number {
    return this.dragIndex() === index ? this.dragOffset() : 0;
  }

  /** How far this train sits from where the reference order put it. Negative =
   *  dispatched earlier. 0 when there is no reference or it did not move — this
   *  is what makes a variant's change legible without a side-by-side diff. */
  shiftOf(train: string, index: number): number {
    if (!this.referenceOrder.length) return 0;
    const from = this.referenceOrder.indexOf(train);
    return from < 0 ? 0 : index - from;
  }

  onPointerDown(index: number, event: PointerEvent): void {
    if (!this.editable) return;
    // Primary button / touch / pen only — a right-click must not start a drag.
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    this.pressedIndex = index;
    this.pressX = event.clientX;
    this.pointerId = event.pointerId;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  onPointerMove(event: PointerEvent): void {
    if (this.pointerId !== event.pointerId || this.pressedIndex === null) return;

    if (!this.dragging()) {
      if (Math.abs(event.clientX - this.pressX) < TrainSequenceComponent.DRAG_THRESHOLD_PX) {
        return;
      }
      this.dragIndex.set(this.pressedIndex);
    }

    // Prevents the press from turning into a text selection or a touch scroll.
    event.preventDefault();
    this.dragOffset.set(event.clientX - this.pressX);
    this.dropIndex.set(this.gapAt(event.clientX, event.clientY));
  }

  onPointerUp(event: PointerEvent): void {
    if (this.pointerId !== event.pointerId) return;
    const from = this.dragIndex();
    const gap = this.dropIndex();
    this.endDrag(event);
    if (from !== null && gap !== null) this.emitMove(from, gap);
  }

  onPointerCancel(event: PointerEvent): void {
    if (this.pointerId !== event.pointerId) return;
    this.endDrag(event);
  }

  /**
   * The gap the pointer is currently aiming at.
   *
   * Nearest chip by distance rather than a plain left-to-right scan, because a
   * long sequence wraps onto a second line — the vertical term is weighted so a
   * chip on the pointer's own row always wins over a closer one above it.
   */
  private gapAt(x: number, y: number): number {
    const slots = Array.from(
      this.host.nativeElement.querySelectorAll<HTMLElement>('.ts__slot'),
    );
    if (!slots.length) return 0;

    let nearest = 0;
    let nearestDistance = Infinity;
    slots.forEach((slot, i) => {
      const rect = slot.getBoundingClientRect();
      const dx = x - (rect.left + rect.width / 2);
      const dy = (y - (rect.top + rect.height / 2)) * 3;
      const distance = Math.hypot(dx, dy);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = i;
      }
    });

    const rect = slots[nearest].getBoundingClientRect();
    return x > rect.left + rect.width / 2 ? nearest + 1 : nearest;
  }

  /** `←` / `→` move the focused chip one place. Re-rendering the list detaches
   *  the moved node, so focus is put back on the chip at its new place. */
  onKeydown(index: number, event: KeyboardEvent): void {
    if (!this.editable) return;
    if (event.key === 'ArrowLeft' && index > 0) {
      event.preventDefault();
      if (this.emitMove(index, index - 1)) this.refocus(this.order[index]);
    } else if (event.key === 'ArrowRight' && index < this.order.length - 1) {
      event.preventDefault();
      if (this.emitMove(index, index + 2)) this.refocus(this.order[index]);
    }
  }

  /** Move the train at `from` into the gap at `gap`. Returns whether the order
   *  actually changed — dropping a chip back where it started is not an edit. */
  private emitMove(from: number, gap: number): boolean {
    const next = [...this.order];
    const [train] = next.splice(from, 1);
    // Removing the train shifts every gap after it one to the left.
    const target = gap > from ? gap - 1 : gap;
    if (target === from) return false;
    next.splice(target, 0, train);
    this.reorder.emit(next);
    return true;
  }

  /** Put focus back on `train` once the parent has re-rendered the new order.
   *  By train rather than by index, and after the render rather than on a
   *  timer — a timer fires before change detection has moved the nodes, which
   *  lands focus on whichever chip happens to occupy that slot beforehand. */
  private refocus(train: string): void {
    afterNextRender(
      () => {
        const slots = this.host.nativeElement.querySelectorAll<HTMLElement>('.ts__slot');
        for (const slot of Array.from(slots)) {
          if (slot.dataset['train'] === train) {
            slot.focus();
            return;
          }
        }
      },
      { injector: this.injector },
    );
  }

  private endDrag(event: PointerEvent): void {
    const target = event.currentTarget as HTMLElement | null;
    if (target?.hasPointerCapture?.(event.pointerId)) {
      target.releasePointerCapture(event.pointerId);
    }
    this.pointerId = null;
    this.pressedIndex = null;
    this.dragIndex.set(null);
    this.dropIndex.set(null);
    this.dragOffset.set(0);
  }
}
