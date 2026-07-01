import { computed, Injectable, signal } from '@angular/core';

export type LayoutViewKey = 'flatland-map' | 'marey';

type LayoutViewState = {
  flatlandMap: boolean;
  marey: boolean;
};

@Injectable({
  providedIn: 'root',
})
export class LayoutViewToggleService {
  private readonly storageKey = 'flatland.layout.viewToggle.v1';

  private readonly state = signal<LayoutViewState>(this.readState());
  private readonly counts = signal<Record<string, number>>({});

  readonly toggleViewAvailable = computed(() => this.countFor('toggle-view') > 0);
  readonly flatlandMapAvailable = computed(() => this.countFor('flatland-map') > 0);
  readonly mareyAvailable = computed(() => this.countFor('marey') > 0);

  readonly flatlandMapEnabled = computed(() => this.state().flatlandMap);
  readonly mareyEnabled = computed(() => this.state().marey);

  registerPanelType(type: string | null | undefined): () => void {
    const normalized = this.normalizeType(type);

    if (!normalized) {
      return () => undefined;
    }

    this.counts.update((current) => ({
      ...current,
      [normalized]: (current[normalized] ?? 0) + 1,
    }));

    return () => {
      this.counts.update((current) => {
        const nextCount = Math.max(0, (current[normalized] ?? 0) - 1);
        const next = { ...current };

        if (nextCount === 0) {
          delete next[normalized];
        } else {
          next[normalized] = nextCount;
        }

        return next;
      });
    };
  }

  isPanelTypeVisible(type: string | null | undefined): boolean {
    const normalized = this.normalizeType(type);

    /*
      Safe default:
      If the current layout has no toggle-view panel, map and marey content must
      stay visible. This keeps predefined/default layouts and old saved layouts
      working even if localStorage contains an old toggle state.
    */
    if (!this.toggleViewAvailable()) {
      return true;
    }

    if (normalized === 'flatland-map') {
      return this.flatlandMapEnabled();
    }

    if (normalized === 'marey') {
      return this.mareyEnabled();
    }

    return true;
  }

  setEnabled(view: LayoutViewKey, enabled: boolean): void {
    this.state.update((current) => {
      const next: LayoutViewState = {
        ...current,
        flatlandMap: view === 'flatland-map' ? enabled : current.flatlandMap,
        marey: view === 'marey' ? enabled : current.marey,
      };

      this.writeState(next);
      return next;
    });
  }

  toggle(view: LayoutViewKey): void {
    if (view === 'flatland-map') {
      this.setEnabled('flatland-map', !this.flatlandMapEnabled());
      return;
    }

    this.setEnabled('marey', !this.mareyEnabled());
  }

  private countFor(type: string): number {
    return this.counts()[type] ?? 0;
  }

  private normalizeType(type: string | null | undefined): string | null {
    if (!type) {
      return null;
    }

    if (type === 'simulation-map') {
      return 'flatland-map';
    }

    if (type === 'marey-chart' || type === 'graphic-timetable') {
      return 'marey';
    }

    return type;
  }

  private readState(): LayoutViewState {
    try {
      const raw = window.localStorage.getItem(this.storageKey);

      if (!raw) {
        return { flatlandMap: true, marey: true };
      }

      const parsed = JSON.parse(raw);

      return {
        flatlandMap: parsed?.flatlandMap !== false,
        marey: parsed?.marey !== false,
      };
    } catch {
      return { flatlandMap: true, marey: true };
    }
  }

  private writeState(state: LayoutViewState): void {
    try {
      window.localStorage.setItem(this.storageKey, JSON.stringify(state));
    } catch {
      // Ignore storage errors.
    }
  }
}
