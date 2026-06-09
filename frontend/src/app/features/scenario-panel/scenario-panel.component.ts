import { Component, CUSTOM_ELEMENTS_SCHEMA, effect, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { ApiService } from '../../core/api.service';
import { EventBusService } from '../../core/events/event-bus.service';
import { ScenarioOption } from '../../core/events/event-types';
import { PolicyName } from '../../core/models';

@Component({
  selector: 'app-scenario-panel',
  standalone: true,
  templateUrl: './scenario-panel.component.html',
  styleUrl: './scenario-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ScenarioPanelComponent {
  store = inject(SessionStore);
  api = inject(ApiService);
  bus = inject(EventBusService);

  /** Tracks which card is currently being confirmed. */
  confirming = signal<string | null>(null);

  constructor() {
    effect(() => {
      const state = this.store.state();
      const sess = this.store.session();
      if (sess && state) {
        this.api.getScenarios(sess.id).subscribe({
          next: (scenarios) => this.store.scenarios.set(scenarios),
          error: () => {},
        });
      } else {
        this.store.scenarios.set([]);
      }
    });
  }

  /** Switch the session-wide policy via POST /policy. */
  confirm(s: ScenarioOption) {
    const sess = this.store.session();
    if (!sess) return;
    // Derive policy id from "scn_<policy_id>"
    const policyId = s.id.startsWith('scn_') ? s.id.slice(4) : s.id;
    this.confirming.set(s.id);
    this.api.setPolicy(sess.id, policyId as PolicyName).subscribe({
      next: () => {
        this.bus.emit({ type: 'SCENARIO_CONFIRMED', scenarioId: s.id });
        this.store.setActivePolicy(policyId as PolicyName);
        // Backend has cleared the scenario cache; force a reload so the
        // panel + Marey re-render with the NEW baseline (the chosen
        // policy now carries the 'Current' badge).
        this.api.getScenarios(sess.id).subscribe({
          next: (scenarios) => this.store.scenarios.set(scenarios),
          error: () => {},
        });
        // Also clear any hover-preview so the Marey snaps back to baseline.
        this.store.previewScenarioId.set(null);
        this.confirming.set(null);
      },
      error: (err) => {
        console.warn('Failed to switch policy', err);
        this.confirming.set(null);
      },
    });
  }

  formatDelta(n: number | undefined | null): string {
    if (n == null) return '';
    return n > 0 ? `+${n}` : `${n}`;
  }

  /** Total agents from session state, used for KPI denominator. */
  totalAgents(): number {
    return this.store.state()?.agents?.length ?? 0;
  }
}
