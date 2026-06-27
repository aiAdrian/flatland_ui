import { Injectable, signal } from '@angular/core';

export type RailCellHoverSource = 'flatland' | 'marey';

@Injectable({ providedIn: 'root' })
export class RailCellHoverService {
  readonly hoveredCellKey = signal<string | null>(null);
  readonly hoveredSource = signal<RailCellHoverSource | null>(null);
  readonly hoveredDebug = signal<any | null>(null);

  /**
   * Default enabled: the trajectory/topology cell layer should be visible
   * as soon as trajectory debug data is available.
   */
  readonly showTopologyDebugLayer = signal<boolean>(true);

  setHoveredCell(
    key: string,
    source: RailCellHoverSource,
    debug: any | null = null,
  ): void {
    this.hoveredCellKey.set(key);
    this.hoveredSource.set(source);
    this.hoveredDebug.set(debug);
  }

  clearHoveredCell(): void {
    this.hoveredCellKey.set(null);
    this.hoveredSource.set(null);
    this.hoveredDebug.set(null);
  }

  setShowTopologyDebugLayer(value: boolean): void {
    this.showTopologyDebugLayer.set(value);
  }

  toggleTopologyDebugLayer(): void {
    this.showTopologyDebugLayer.update((value) => !value);
  }
}
