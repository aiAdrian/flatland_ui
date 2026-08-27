import { Injectable, computed, inject } from '@angular/core';
import { SessionStore } from './session.store';

/**
 * One name per train, shared by every view.
 *
 * Flatland identifies trains by handle (`0`…`n`), and until now every surface
 * showed exactly that: `#3` on the map, `#3` in the timetable, `3` in the ZWL.
 * Combined Actions instead talks about services (`IC_703`), because a dispatcher
 * argues about *the IC to Bern*, not about agent 3 — and the two vocabularies
 * did not meet anywhere, so the same train read as two different things
 * depending on which panel you looked at.
 *
 * This service is the single place that maps the one onto the other. The
 * assignment is positional and fixed (`SERVICE_ROSTER` in handle order), so it
 * is stable for a session and reproducible across runs of the same scenario —
 * a study can be replayed and the trains keep their names.
 *
 * ⚠ The names are **authored**, not scenario data. Flatland has no concept of a
 * service; nothing downstream may treat `IC_703` as a timetable identity. When
 * real scenarios carry service names (`flatland-scenarios` `trainCategories` /
 * `flatlandTimetable`), this is the seam that reads them instead.
 */

/** Service names in assignment order: the i-th train by handle gets the i-th name. */
export const SERVICE_ROSTER: readonly string[] = [
  'IC_703',
  'ICE_42',
  'RE_18',
  'S8_214',
  'EC_91',
  'RB_51',
  'IR_227',
  'TGV_12',
];

/** Categories a generated name can fall back to, cycled for handles past the roster. */
const OVERFLOW_CATEGORIES = ['RE', 'S', 'IC', 'RB'] as const;

@Injectable({ providedIn: 'root' })
export class TrainIdentityService {
  private readonly store = inject(SessionStore);

  /**
   * handle → service name.
   *
   * Sorted by handle rather than by the agents array's order, so adding or
   * removing a train mid-run cannot silently rename the others.
   */
  readonly nameByHandle = computed<Record<number, string>>(() => {
    const handles = this.store.agents().map((a) => a.handle).sort((a, b) => a - b);
    const out: Record<number, string> = {};
    handles.forEach((handle, i) => {
      out[handle] = i < SERVICE_ROSTER.length ? SERVICE_ROSTER[i] : this.generated(i);
    });
    return out;
  });

  /** The reverse lookup, for surfaces that start from a service name. */
  readonly handleByName = computed<Record<string, number>>(() => {
    const out: Record<string, number> = {};
    for (const [handle, name] of Object.entries(this.nameByHandle())) {
      out[name] = Number(handle);
    }
    return out;
  });

  /** Service name for a handle; falls back to `#handle` before the session loads. */
  nameFor(handle: number): string {
    return this.nameByHandle()[handle] ?? `#${handle}`;
  }

  /** Handle for a service name, or null when this session has no such train. */
  handleFor(name: string): number | null {
    const handle = this.handleByName()[name];
    return handle === undefined ? null : handle;
  }

  /** True once the session has trains to name. */
  readonly ready = computed(() => Object.keys(this.nameByHandle()).length > 0);

  /** Beyond the authored roster, keep the shape (`RE_31`) rather than falling
   *  back to a bare number — a mixed vocabulary is what this service exists to
   *  prevent. */
  private generated(index: number): string {
    const category = OVERFLOW_CATEGORIES[index % OVERFLOW_CATEGORIES.length];
    return `${category}_${index + 1}`;
  }
}
