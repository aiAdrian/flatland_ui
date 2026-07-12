import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, computed, inject } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { AgentColorService } from '../../core/agent-color.service';

/** One schedule row. `from`/`to` are the shared station labels (S{n}) — the same
 *  labels the map stations layer renders, so a stop can be read across both.
 *  `now`/`status`/`tone` are the live progress: where the train is and how it is
 *  doing right now (derived from position/state/delay — no backend change). */
interface TimetableRow {
  handle: number;
  color: string;
  from: string;
  to: string;
  departure: number | null;
  arrival: number | null;
  /** Where it is now: a station label if at a stop, else en route / waiting / arrived. */
  now: string;
  /** How it is going: on time / +N late / dep in N / ⚠ malfunction / arrived. */
  status: string;
  tone: 'ok' | 'late' | 'warn' | 'muted';
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
    this.store.agents().map((a) => {
      const to = this.store.stationLabelForCell(a.target) ?? '—';
      const done = (a.state ?? '').includes('DONE');
      const atStop = this.store.stationLabelForCell(a.position);
      const delay = a.delay ?? 0;

      // Where it is now.
      let now: string;
      if (done) now = `${to} ✓`;
      else if (!a.position) now = 'waiting';           // still off-map before departure
      else now = atStop ?? 'en route';

      // How it is going.
      let status: string;
      let tone: TimetableRow['tone'];
      if (a.is_malfunctioning) {
        status = `⚠ ${a.malfunction_remaining}`;
        tone = 'warn';
      } else if (done) {
        status = 'arrived';
        tone = 'ok';
      } else if (!a.position) {
        status = a.eta_to_depart != null && a.eta_to_depart > 0 ? `dep in ${a.eta_to_depart}` : 'ready';
        tone = 'muted';
      } else if (delay > 0) {
        status = `+${delay} late`;
        tone = 'late';
      } else {
        status = 'on time';
        tone = 'ok';
      }

      return {
        handle: a.handle,
        color: this.colors.getColor(a.handle),
        from: this.store.stationLabelForCell(a.initial_position) ?? '—',
        to,
        departure: a.earliest_departure,
        arrival: a.latest_arrival,
        now,
        status,
        tone,
      };
    }),
  );
}
