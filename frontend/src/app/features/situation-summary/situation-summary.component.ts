import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';
import { SessionStore } from '../../core/session.store';
import { AgentDTO } from '../../core/models';

/**
 * Hypervision-style situation summary (left column, top). Synthesises the live
 * operating state into a few headline numbers so the operator grasps "what's the
 * situation" at a glance, instead of reading raw events only. All values are
 * derived from the current agent states — no backend call.
 */
@Component({
  selector: 'app-situation-summary',
  standalone: true,
  imports: [TranslocoPipe],
  templateUrl: './situation-summary.component.html',
  styleUrl: './situation-summary.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class SituationSummaryComponent {
  store = inject(SessionStore);

  private isMalfunctioning(a: AgentDTO): boolean {
    return !!a.is_malfunctioning
      || (a.malfunction_remaining ?? 0) > 0
      || String(a.state ?? '').toUpperCase().includes('MALFUNCTION');
  }

  readonly total = computed(() => this.store.agents().length);
  readonly arrived = computed(() => this.store.agents().filter((a) => String(a.state).toUpperCase() === 'DONE').length);
  readonly active = computed(() => this.store.agents().filter((a) => {
    const s = String(a.state).toUpperCase();
    return s !== 'DONE' && s !== 'WAITING';
  }).length);
  readonly delayedCount = computed(() => this.store.agents().filter((a) => (a.delay ?? 0) > 0).length);
  readonly totalDelay = computed(() => this.store.agents().reduce((sum, a) => sum + Math.max(0, a.delay ?? 0), 0));
  readonly malfunctions = computed(() => this.store.agents().filter((a) => this.isMalfunctioning(a)).length);

  readonly arrivedPct = computed(() => {
    const t = this.total();
    return t === 0 ? 0 : Math.round((this.arrived() / t) * 100);
  });
}
