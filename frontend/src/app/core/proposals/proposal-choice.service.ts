import { Injectable, computed, inject, signal } from '@angular/core';
import { SessionStore } from '../session.store';
import { ProposalOption } from '../events/event-types';

/**
 * The option the operator is looking at for one train, shared by the surfaces
 * that let them pick it: the Plan / KI / Mensch panel and the option strip at the
 * selected train on the map.
 *
 * Picking is a question ("what would this do?"), not a decision: the panel
 * simulates it, and committing stays in the panel, where the comparison is.
 *
 * Keyed by handle, so selecting another train drops the choice without either
 * surface having to clear it.
 */
@Injectable({ providedIn: 'root' })
export class ProposalChoiceService {
  private readonly store = inject(SessionStore);
  private readonly choice = signal<{ handle: number; option: ProposalOption } | null>(null);

  /** The option picked for the currently selected train, if any. */
  readonly current = computed(() => {
    const handle = this.store.selectedHandle();
    const choice = this.choice();
    return choice && choice.handle === handle ? choice.option : null;
  });

  /** Pick `option` for `handle`, selecting the train if it is not yet. */
  choose(handle: number, option: ProposalOption): void {
    if (option === 'reroute' && !this.rerouteAvailable(handle)) return;
    if (this.store.selectedHandle() !== handle) this.store.selectedHandle.set(handle);
    this.choice.set({ handle, option });
  }

  /**
   * While the impact analysis lists the train it also says whether a reroute
   * exists. Without an entry the backend decides, and explains a refusal.
   */
  rerouteAvailable(handle: number | null): boolean {
    const item = this.store.impact().find((i) => i.handle === handle);
    return item ? item.can_reroute : true;
  }
}
