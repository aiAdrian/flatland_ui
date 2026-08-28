import { CUSTOM_ELEMENTS_SCHEMA, Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

import {
  EvaluatedAction,
  proposeCombinedActions,
  trainFacts,
} from '../../core/combined-actions-package';
import { SessionStore } from '../../core/session.store';
import { CaPkgActionCardComponent } from './action-card.component';

/**
 * Combined Actions (WP 3.2) — the mode's decision surface.
 *
 * Runs the pipeline once for the conflict and offers the strongest answer at each
 * level of intervention, so the dispatcher compares two, three and four controlled
 * trains rather than three variants of the same size. The best candidate overall
 * carries the recommendation, which is often the *smallest* one: when a larger
 * intervention buys only a minute, the ranking prefers touching fewer trains.
 *
 * The container owns the proposal and the confirmation log. Each card owns its own
 * sequence and prediction, so editing one cannot disturb another — a dispatcher
 * comparing the three-train answer against an edited two-train answer has to be
 * able to trust that the other card stayed as they left it.
 */
@Component({
  selector: 'app-combined-actions-package',
  standalone: true,
  imports: [CommonModule, CaPkgActionCardComponent],
  templateUrl: './combined-actions.component.html',
  styleUrl: './combined-actions.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class CombinedActionsPackageComponent {
  private readonly store = inject(SessionStore);

  /** Computed once: the conflict is a fixture, so re-running would change nothing. */
  private readonly _proposal = signal(proposeCombinedActions());

  readonly proposal = computed(() => this._proposal());
  readonly offered = computed(() => this._proposal().offered);
  readonly window = computed(() => this._proposal().window);
  readonly baseline = computed(() => this._proposal().baseline);

  /**
   * The one chosen action, by the id of the card it came from.
   *
   * Held here rather than in the cards because the choice is exclusive: a conflict
   * gets one dispatching decision, and three simultaneously confirmed actions
   * would be three contradictory instructions for the same section. The cards
   * render their own state from this.
   */
  private readonly _chosenId = signal<string | null>(null);
  readonly chosenId = computed(() => this._chosenId());

  private readonly _lastConfirmed = signal<{
    controlled: number;
    modified: boolean;
    reduction: number;
  } | null>(null);
  readonly lastConfirmed = computed(() => this._lastConfirmed());

  isChosen(cardId: string): boolean {
    return this._chosenId() === cardId;
  }

  /** Another card holds the choice, so this one is out of play. */
  isLocked(cardId: string): boolean {
    const chosen = this._chosenId();
    return chosen !== null && chosen !== cardId;
  }

  /** Hand the choice back, so a different action can be taken instead. */
  revoke(): void {
    this._chosenId.set(null);
    this._lastConfirmed.set(null);
    this.clearFocus();
  }

  /** The card the operator is looking at — its trains are lit up on the map. */
  private readonly _focusedId = signal<string | null>(null);
  readonly focusedId = computed(() => this._focusedId());

  isFocused(cardId: string): boolean {
    return this._focusedId() === cardId;
  }

  /**
   * Point the map at an action: highlight the agents it would dispatch.
   *
   * The conflict is a fixture and the map shows a real session, so the trains are
   * tied to agent handles in the scenario file. Highlighting marks *which* trains
   * the action takes hold of; it does not draw a rerouted path, because a fixture
   * has no route on this map to draw.
   */
  focus(cardId: string, evaluated: EvaluatedAction): void {
    this._focusedId.set(cardId);
    const handles = evaluated.metrics.controlled
      .map((train) => trainFacts(this.window(), train).agentHandle)
      .filter((handle) => handle >= 0);
    this.store.combinedActionHandles.set(new Set(handles));
  }

  clearFocus(): void {
    this._focusedId.set(null);
    this.store.combinedActionHandles.set(new Set());
  }

  onConfirmed(
    cardId: string,
    event: { evaluated: EvaluatedAction; modified: boolean },
  ): void {
    const metrics = event.evaluated.metrics;
    this._chosenId.set(cardId);
    this._lastConfirmed.set({
      controlled: metrics.controlledTrains,
      modified: event.modified,
      reduction: metrics.totalDelayReduction,
    });
    // The decision log is the app's audit trail, and a confirmed multi-train
    // action — especially one the dispatcher reordered first — is exactly what it
    // exists to record.
    // Not recorded yet: writing a decision-log entry per confirmed package
    // is a flagged item in the E1 spec (§4) because the store's
    // `_appendDecision` has no public seam. Porting this variant must not
    // open that seam as a side effect — it is a decision of its own, and it
    // would change the other Combined Actions variant too.
  }

  /** The number the AI promised for the card this confirmation came from. */
  private aiReductionFor(evaluated: EvaluatedAction): number {
    const match = this.offered().find(
      (o) => o.action.id === evaluated.action.id.replace(/_human$/, ''),
    );
    return match?.metrics.totalDelayReduction ?? evaluated.metrics.totalDelayReduction;
  }
}
