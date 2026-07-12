import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, computed, inject } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { AgentColorService } from '../../core/agent-color.service';

/** One schedule row. `from`/`to` are the shared station labels (S{n}) — the same
 *  labels the map stations layer renders, so a stop can be read across both. */
interface TimetableRow {
  handle: number;
  color: string;
  from: string;
  to: string;
  departure: number | null;
  arrival: number | null;
  delay: number;
  state: string;
}

/**
 * Timetable (Fahrplan) — Context widget. Tabular departure/arrival board keyed
 * to the shared station registry. Mode-invariant (same in all three modes); see
 * docs/plans/widget-timetable.md. Basic variant uses only data the store already
 * exposes — no backend change. Source: from-scratch, deliberately.
 */
@Component({
  selector: 'app-timetable',
  standalone: true,
  imports: [],
  templateUrl: './timetable.component.html',
  styleUrl: './timetable.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class TimetableComponent {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  private store = inject(SessionStore);
  private colors = inject(AgentColorService);

  readonly rows = computed<TimetableRow[]>(() =>
    this.store.agents().map((a) => ({
      handle: a.handle,
      color: this.colors.getColor(a.handle),
      from: this.store.stationLabelForCell(a.initial_position) ?? '—',
      to: this.store.stationLabelForCell(a.target) ?? '—',
      departure: a.earliest_departure,
      arrival: a.latest_arrival,
      delay: a.delay ?? 0,
      state: a.state,
    })),
  );
}
