import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { AgentDTO } from '../../core/models';

/**
 * The Director bar: one row carrying the aggregate operating state and the
 * run control.
 *
 * It absorbed two surfaces that each cost a lot of screen for little content:
 *
 * - The old 121px directive block, whose prose pointed at a "KPI priorities"
 *   panel that is offered in no mode any more. The objective is set by the
 *   A/B/C strategy tiles below, which show the same three axes with real
 *   planned consequences.
 * - The Situation Summary panel, which held a whole left column for four
 *   numbers. In Director those numbers *are* the supervisory picture — how many
 *   trains run, how many are late, how many are broken — so they belong on the
 *   permanently visible bar, not in a column of their own. Removing that column
 *   is what gives the map and the forecast their width.
 *
 * Deliberately shown while playing too: the state matters most while the AI
 * drives, so this replaces the separate "AI in control" banner instead of
 * alternating with it.
 */
@Component({
  selector: 'app-director-directive',
  standalone: true,
  templateUrl: './director-directive.component.html',
  styleUrl: './director-directive.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class DirectorDirectiveComponent {
  store = inject(SessionStore);

  /** Whether the run has already produced steps (→ "Resume" instead of "Start"). */
  readonly started = computed(() => this.store.elapsedSteps() > 0);

  /** Active policy label for the directive summary. */
  readonly policyLabel = computed(() => {
    const id = this.store.activePolicy();
    return this.store.availablePolicies().find((p) => p.id === id)?.label ?? id;
  });

  // ── Aggregate state (carried over from the Situation Summary) ─────────────
  private isMalfunctioning(a: AgentDTO): boolean {
    return (
      !!a.is_malfunctioning ||
      (a.malfunction_remaining ?? 0) > 0 ||
      String(a.state ?? '')
        .toUpperCase()
        .includes('MALFUNCTION')
    );
  }

  readonly total = computed(() => this.store.agents().length);
  readonly arrived = computed(
    () =>
      this.store.agents().filter((a) => String(a.state).toUpperCase() === 'DONE').length,
  );
  readonly active = computed(
    () =>
      this.store.agents().filter((a) => {
        const s = String(a.state).toUpperCase();
        return s !== 'DONE' && s !== 'WAITING';
      }).length,
  );
  readonly delayedCount = computed(
    () => this.store.agents().filter((a) => (a.delay ?? 0) > 0).length,
  );
  readonly malfunctions = computed(
    () => this.store.agents().filter((a) => this.isMalfunctioning(a)).length,
  );

  start(): void {
    const policy = this.store.activePolicy() || this.store.defaultPolicy();
    this.store.play(policy, this.store.playSpeed());
  }

  /** Declare the shift over — pauses the run and opens the review. */
  endShift(): void {
    this.store.endShift();
  }
}
