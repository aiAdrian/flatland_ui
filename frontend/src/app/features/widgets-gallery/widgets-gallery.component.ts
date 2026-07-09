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
  WIDGET_KIND_ORDER,
  WidgetKind,
  WidgetMeta,
  WidgetStatus,
  widgetAvailableInMode,
  widgetsByKind,
} from '../../core/widgets/widget-catalog';

interface GalleryGroup {
  kind: WidgetKind;
  meta: (typeof KIND_META)[WidgetKind];
  widgets: WidgetMeta[];
}

interface ModeColumn {
  id: InteractionMode;
  label: string;
  wp: string;
}

/**
 * Widget Gallery — an in-app browsable catalog of every HMI widget, grounded in the
 * widget-catalog registry (core/widgets/widget-catalog.ts). It answers three
 * authoring/onboarding questions the layout designer's flat palette cannot:
 *
 *   1. *Which kind do I need?* — widgets are grouped by interaction-framework
 *      `kind`, each with the question it answers and its badge colour.
 *   2. *How does it behave in my mode?* — every card shows the per-mode
 *      behaviour (Recommendation / Co-Learning / Director) side by side.
 *   3. *What does it look like?* — a schematic thumbnail, with an opt-in live
 *      preview of the real component for shipped widgets.
 *
 * Reached at /widgets (mirrors the /designer path toggle in AppComponent).
 */
@Component({
  selector: 'app-widgets-gallery',
  standalone: true,
  imports: [CommonModule, FormsModule, PanelPluginHostComponent, ConfigShellComponent],
  templateUrl: './widgets-gallery.component.html',
  styleUrl: './widgets-gallery.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class WidgetsGalleryComponent {
  readonly store = inject(SessionStore);

  readonly kindOrder = WIDGET_KIND_ORDER;
  readonly kindMeta = KIND_META;

  readonly modeColumns: ModeColumn[] = [
    { id: 'recommendation', label: 'Recommendation', wp: 'WP 3.1' },
    { id: 'co-learning', label: 'Co-Learning', wp: 'WP 3.3' },
    { id: 'director', label: 'Director', wp: 'WP 3.4' },
  ];

  readonly statusColumns: { id: WidgetStatus; label: string }[] = [
    { id: 'shipped', label: 'Shipped' },
    { id: 'first-cut', label: 'First cut' },
    { id: 'planned', label: 'Planned' },
  ];

  /** Filter state. */
  readonly kindFilter = signal<WidgetKind | 'all'>('all');
  readonly modeFilter = signal<InteractionMode | 'all'>('all');
  readonly statusFilter = signal<WidgetStatus | 'all'>('shipped');
  readonly query = signal<string>('');

  /** Widgets whose live preview the user opted into (by panel type). */
  private readonly livePreviews = signal<ReadonlySet<string>>(new Set());

  readonly groups = computed<GalleryGroup[]>(() => {
    const kindF = this.kindFilter();
    const modeF = this.modeFilter();
    const statusF = this.statusFilter();
    const q = this.query().trim().toLowerCase();

    return widgetsByKind()
      .filter((g) => kindF === 'all' || g.kind === kindF)
      .map((g) => ({
        kind: g.kind,
        meta: KIND_META[g.kind],
        widgets: g.widgets.filter((t) => {
          if (statusF !== 'all' && t.status !== statusF) return false;
          if (modeF !== 'all' && !widgetAvailableInMode(t, modeF)) return false;
          if (q && !`${t.title} ${t.description} ${t.grounding}`.toLowerCase().includes(q)) {
            return false;
          }
          return true;
        }),
      }))
      .filter((g) => g.widgets.length > 0);
  });

  readonly totalShown = computed(() =>
    this.groups().reduce((n, g) => n + g.widgets.length, 0),
  );

  // ── Filters ────────────────────────────────────────────────────────────
  setKindFilter(kind: WidgetKind | 'all'): void {
    this.kindFilter.set(kind);
  }

  setModeFilter(mode: InteractionMode | 'all'): void {
    this.modeFilter.set(mode);
  }

  setStatusFilter(status: WidgetStatus | 'all'): void {
    this.statusFilter.set(status);
  }

  resetFilters(): void {
    this.kindFilter.set('all');
    this.modeFilter.set('all');
    this.statusFilter.set('shipped');
    this.query.set('');
  }

  // ── Per-mode presentation ────────────────────────────────────────────────
  behaviourFor(widget: WidgetMeta, mode: InteractionMode): string | null {
    return widget.perMode[mode];
  }

  /** Emphasise the column matching the active session mode, or the mode filter. */
  isEmphasisedMode(mode: InteractionMode): boolean {
    const f = this.modeFilter();
    if (f !== 'all') return f === mode;
    return this.store.interactionMode() === mode;
  }

  availableIn(widget: WidgetMeta, mode: InteractionMode): boolean {
    return widgetAvailableInMode(widget, mode);
  }

  /** Consistency check: registry availability vs the runtime availability map.
   *  Surfaced as a small warning so the two sources cannot drift silently. */
  availabilityMismatch(widget: WidgetMeta): boolean {
    if (!widget.type) return false;
    return this.modeColumns.some(
      (m) => widgetAvailableInMode(widget, m.id) !== isPanelAvailableInMode(widget.type, m.id),
    );
  }

  // ── Live preview ─────────────────────────────────────────────────────────
  canPreviewLive(widget: WidgetMeta): boolean {
    return widget.status !== 'planned' && widget.type !== '';
  }

  isLive(widget: WidgetMeta): boolean {
    return this.livePreviews().has(widget.type);
  }

  toggleLive(widget: WidgetMeta): void {
    if (!this.canPreviewLive(widget)) return;
    const next = new Set(this.livePreviews());
    next.has(widget.type) ? next.delete(widget.type) : next.add(widget.type);
    this.livePreviews.set(next);
  }

  /** Build a throwaway PanelInstance so panel-plugin-host can render the widget. */
  previewPanel(widget: WidgetMeta): PanelInstance {
    return {
      id: `gallery-preview-${widget.type}`,
      type: widget.type,
      title: widget.title,
      zone: widget.defaultZone,
      order: 0,
      collapsed: false,
      hidden: false,
      sizeMode: 'auto',
    };
  }

  // ── Cosmetics ────────────────────────────────────────────────────────────
  kindVar(kind: WidgetKind): string {
    return `var(${KIND_META[kind].token})`;
  }

  statusLabel(status: WidgetStatus): string {
    switch (status) {
      case 'shipped':
        return 'shipped';
      case 'first-cut':
        return 'first cut';
      case 'planned':
        return 'planned';
    }
  }

  trackByType = (_: number, t: WidgetMeta): string => t.type || t.catalogId || t.title;
  trackByKind = (_: number, g: GalleryGroup): string => g.kind;
  trackByMode = (_: number, m: ModeColumn): string => m.id;
}
