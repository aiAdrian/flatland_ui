import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { SessionStore } from '../../core/session.store';
import { InteractionMode } from '../../core/events/event-types';
import { PanelInstance } from '../../core/layout';
import { isPanelAvailableInMode } from '../../core/layout/panel-mode-availability';
import { PanelPluginHostComponent } from '../layout/components/panel-plugin-host/panel-plugin-host.component';
import { ConfigShellComponent } from '../config-shell/config-shell.component';
import {
  KIND_META,
  TILE_KIND_ORDER,
  TileKind,
  TileMeta,
  TileStatus,
  tileAvailableInMode,
  tilesByKind,
} from '../../core/tiles/tile-catalog';

interface GalleryGroup {
  kind: TileKind;
  meta: (typeof KIND_META)[TileKind];
  tiles: TileMeta[];
}

interface ModeColumn {
  id: InteractionMode;
  label: string;
  wp: string;
}

/**
 * Tile Gallery — an in-app browsable catalog of every HMI tile, grounded in the
 * tile-catalog registry (core/tiles/tile-catalog.ts). It answers three
 * authoring/onboarding questions the layout designer's flat palette cannot:
 *
 *   1. *Which kind do I need?* — tiles are grouped by interaction-framework
 *      `kind`, each with the question it answers and its badge colour.
 *   2. *How does it behave in my mode?* — every card shows the per-mode
 *      behaviour (Recommendation / Co-Learning / Director) side by side.
 *   3. *What does it look like?* — a schematic thumbnail, with an opt-in live
 *      preview of the real component for shipped tiles.
 *
 * Reached at /gallery (mirrors the /designer path toggle in AppComponent).
 */
@Component({
  selector: 'app-tiles-gallery',
  standalone: true,
  imports: [CommonModule, FormsModule, PanelPluginHostComponent, ConfigShellComponent],
  templateUrl: './tiles-gallery.component.html',
  styleUrl: './tiles-gallery.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class TilesGalleryComponent {
  readonly store = inject(SessionStore);

  readonly kindOrder = TILE_KIND_ORDER;
  readonly kindMeta = KIND_META;

  readonly modeColumns: ModeColumn[] = [
    { id: 'recommendation', label: 'Recommendation', wp: 'WP 3.1' },
    { id: 'co-learning', label: 'Co-Learning', wp: 'WP 3.3' },
    { id: 'director', label: 'Director', wp: 'WP 3.4' },
  ];

  readonly statusColumns: { id: TileStatus; label: string }[] = [
    { id: 'shipped', label: 'Shipped' },
    { id: 'first-cut', label: 'First cut' },
    { id: 'planned', label: 'Planned' },
  ];

  /** Filter state. */
  readonly kindFilter = signal<TileKind | 'all'>('all');
  readonly modeFilter = signal<InteractionMode | 'all'>('all');
  readonly statusFilter = signal<TileStatus | 'all'>('shipped');
  readonly query = signal<string>('');

  /** Tiles whose live preview the user opted into (by panel type). */
  private readonly livePreviews = signal<ReadonlySet<string>>(new Set());

  readonly groups = computed<GalleryGroup[]>(() => {
    const kindF = this.kindFilter();
    const modeF = this.modeFilter();
    const statusF = this.statusFilter();
    const q = this.query().trim().toLowerCase();

    return tilesByKind()
      .filter((g) => kindF === 'all' || g.kind === kindF)
      .map((g) => ({
        kind: g.kind,
        meta: KIND_META[g.kind],
        tiles: g.tiles.filter((t) => {
          if (statusF !== 'all' && t.status !== statusF) return false;
          if (modeF !== 'all' && !tileAvailableInMode(t, modeF)) return false;
          if (q && !`${t.title} ${t.description} ${t.grounding}`.toLowerCase().includes(q)) {
            return false;
          }
          return true;
        }),
      }))
      .filter((g) => g.tiles.length > 0);
  });

  readonly totalShown = computed(() =>
    this.groups().reduce((n, g) => n + g.tiles.length, 0),
  );

  // ── Filters ────────────────────────────────────────────────────────────
  setKindFilter(kind: TileKind | 'all'): void {
    this.kindFilter.set(kind);
  }

  setModeFilter(mode: InteractionMode | 'all'): void {
    this.modeFilter.set(mode);
  }

  setStatusFilter(status: TileStatus | 'all'): void {
    this.statusFilter.set(status);
  }

  resetFilters(): void {
    this.kindFilter.set('all');
    this.modeFilter.set('all');
    this.statusFilter.set('shipped');
    this.query.set('');
  }

  // ── Per-mode presentation ────────────────────────────────────────────────
  behaviourFor(tile: TileMeta, mode: InteractionMode): string | null {
    return tile.perMode[mode];
  }

  /** Emphasise the column matching the active session mode, or the mode filter. */
  isEmphasisedMode(mode: InteractionMode): boolean {
    const f = this.modeFilter();
    if (f !== 'all') return f === mode;
    return this.store.interactionMode() === mode;
  }

  availableIn(tile: TileMeta, mode: InteractionMode): boolean {
    return tileAvailableInMode(tile, mode);
  }

  /** Consistency check: registry availability vs the runtime availability map.
   *  Surfaced as a small warning so the two sources cannot drift silently. */
  availabilityMismatch(tile: TileMeta): boolean {
    if (!tile.type) return false;
    return this.modeColumns.some(
      (m) => tileAvailableInMode(tile, m.id) !== isPanelAvailableInMode(tile.type, m.id),
    );
  }

  // ── Live preview ─────────────────────────────────────────────────────────
  canPreviewLive(tile: TileMeta): boolean {
    return tile.status !== 'planned' && tile.type !== '';
  }

  isLive(tile: TileMeta): boolean {
    return this.livePreviews().has(tile.type);
  }

  toggleLive(tile: TileMeta): void {
    if (!this.canPreviewLive(tile)) return;
    const next = new Set(this.livePreviews());
    next.has(tile.type) ? next.delete(tile.type) : next.add(tile.type);
    this.livePreviews.set(next);
  }

  /** Build a throwaway PanelInstance so panel-plugin-host can render the tile. */
  previewPanel(tile: TileMeta): PanelInstance {
    return {
      id: `gallery-preview-${tile.type}`,
      type: tile.type,
      title: tile.title,
      zone: tile.defaultZone,
      order: 0,
      collapsed: false,
      hidden: false,
      sizeMode: 'auto',
    };
  }

  // ── Cosmetics ────────────────────────────────────────────────────────────
  kindVar(kind: TileKind): string {
    return `var(${KIND_META[kind].token})`;
  }

  statusLabel(status: TileStatus): string {
    switch (status) {
      case 'shipped':
        return 'shipped';
      case 'first-cut':
        return 'first cut';
      case 'planned':
        return 'planned';
    }
  }

  trackByType = (_: number, t: TileMeta): string => t.type || t.catalogId || t.title;
  trackByKind = (_: number, g: GalleryGroup): string => g.kind;
  trackByMode = (_: number, m: ModeColumn): string => m.id;

  /** Leave the configuration area and return to the dispatcher start page. */
  goHome(): void {
    window.location.href = '/';
  }
}
