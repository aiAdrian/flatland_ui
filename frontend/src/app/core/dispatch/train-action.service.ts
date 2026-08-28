import { Injectable, inject } from '@angular/core';
import { SessionStore } from '../session.store';
import { DecisionOwner } from '../decision-log';

/**
 * Which surface the operator acted from.
 *
 * The same train action is offered in several places on purpose — clicking the
 * train on the map is direct manipulation at the point of interest, and that is
 * a control-room virtue, not an accident. What was missing is that nothing
 * recorded *which* affordance was used, so "how is the workflow meant to go?"
 * (HMI review, docs/reading/2026-08-22-hmi-review-workshop.md §3) could only be
 * answered by assertion. With an origin on every action it becomes a measurement.
 */
export type ActionOrigin =
  | 'roster'     // Trains list (v1)
  | 'table'      // Trains disposition table (v2)
  | 'map'        // decision pills on the Flatland map
  | 'marey'      // decision pills on the graphic timetable
  | 'inspector'  // Agent Inspector detail overlay
  | 'impact'     // Impact panel option buttons
  | 'whatif';    // What-if Compare "commit my plan"

/**
 * TrainActionService — the single authority for acting on one train.
 *
 * Why a service and not just `SessionStore.setOverride`: every widget injects
 * the store to *read*, so a store method makes the read/write boundary
 * invisible. Acting requires injecting this service, which turns "may this
 * widget change anything?" into a visible import — checkable by eye and by
 * grep, and declared per widget as `writes` in `core/widgets/widget-catalog.ts`.
 *
 * It also removes a real duplication: before this, the toggle handler
 * (`isOverride ? clear : set`) was copied into five components — the Marey
 * chart's own comment said "mirrors left-sidebar.onActionClick". Five copies of
 * a decision rule is five places for it to drift.
 *
 * This service does not re-implement the write. `SessionStore` stays the single
 * implementation (optimistic update → decision log → rationale prompt → API);
 * the service is the doorway to it, and the thing that stamps the origin.
 */
@Injectable({ providedIn: 'root' })
export class TrainActionService {
  private readonly store = inject(SessionStore);

  /**
   * Apply `action` to `handle`, or clear it if that exact action is already the
   * operator's standing override. This toggle is the decision rule the widgets
   * used to each carry their own copy of.
   */
  toggle(handle: number, action: number, origin: ActionOrigin): void {
    if (this.isActive(handle, action)) {
      this.clear(handle, origin);
    } else {
      this.set(handle, action, origin);
    }
  }

  /** Set an override without toggle semantics (the caller already decided). */
  set(handle: number, action: number, origin: ActionOrigin, owner: DecisionOwner = 'human'): void {
    this.store.setOverride(handle, action, owner, origin);
  }

  /** Release the standing override on this train. */
  clear(handle: number, origin: ActionOrigin, owner: DecisionOwner = 'human'): void {
    this.store.clearOverride(handle, owner, origin);
  }

  /** True when `action` is the override currently set on this train — i.e. when
   *  the affordance should render as "already yours, click again to undo". */
  isActive(handle: number, action: number): boolean {
    const agent = this.store.agents().find((a) => a.handle === handle);
    return agent?.override_action === action;
  }
}
