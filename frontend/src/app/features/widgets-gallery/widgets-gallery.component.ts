import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal, OnInit, OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { SessionStore } from '../../core/session.store';
import { GalleryFixtureService } from '../../core/gallery-fixture.service';
import { InteractionMode } from '../../core/events/event-types';
import { PanelInstance } from '../../core/layout';
import { isPanelAvailableInMode } from '../../core/layout/panel-mode-availability';
import { PanelPluginHostComponent } from '../layout/components/panel-plugin-host/panel-plugin-host.component';
import { ConfigShellComponent } from '../config-shell/config-shell.component';
import {
  KIND_META,
  PROVENANCE_META,
  WIDGET_CATALOG,
  WIDGET_KIND_ORDER,
  WidgetDataSource,
  WidgetKind,
  WidgetMeta,
  WidgetStatus,
  widgetAvailableInMode,
  WidgetWrites,
} from '../../core/widgets/widget-catalog';
import { MODE_ORDER, MODE_PRESETS, ModeRow, modeRowsFor, sameInAllModes } from '../../core/widgets/widget-mode-axes';

/** One catalog entry as the list renders it. A `role` group collapses into a
 *  single entry whose `variants` carries the alternatives. */
interface GalleryEntry {
  /** The widget currently shown for this entry (the selected variant). */
  widget: WidgetMeta;
  /** Stable key — the role when this is a variant group, else the widget key. */
  key: string;
  /** All variants sharing a `role`; length 1 for a standalone widget. */
  variants: WidgetMeta[];
}

interface GalleryGroup {
  kind: WidgetKind;
  meta: (typeof KIND_META)[WidgetKind];
  entries: GalleryEntry[];
}

/** A facet chip in the filter rail. `amount` feeds `sbb-tag`'s built-in count. */
interface Facet<T> {
  id: T;
  label: string;
  /** Dot colour (a CSS var reference), or null for the neutral "all" chip. */
  colorVar: string | null;
  amount: number | null;
}

const widgetKey = (w: WidgetMeta): string => w.type || w.catalogId || w.title;

/**
 * Widget Gallery — the in-app catalog of every HMI widget, grounded in the
 * widget-catalog registry (core/widgets/widget-catalog.ts).
 *
 * ## v2 — a catalog, not a card wall
 *
 * The first version rendered every widget as a card that always showed
 * everything (title + status + 3 meta badges + description + promise + preview +
 * 3 mode rows + grounding ≈ 420px, times 33). This version is a **row list**:
 * ~40px at rest, expanded on click, with nothing removed — it just arrives on
 * demand. See `docs/plans/` and the design proposal for the reasoning.
 *
 * This is deliberately shaped as the **first instance of a catalog pattern**
 * (rows + facet rail + expand + governance bar), not as a bespoke page: further
 * catalogs (scenarios, agents, methods, benchmarks, infrastructures) are
 * intended to reuse it. The generic parts are not extracted yet — one example is
 * not enough to know where the seams belong.
 *
 * Three things it answers that the layout designer's flat palette cannot:
 *   1. *Which kind do I need?* — grouped by interaction-framework `kind`.
 *   2. *How does it behave in my mode?* — per-mode behaviour (via
 *      `widget-mode-axes`, the seam for the planned autonomy/goal split).
 *   3. *What does it look like?* — inline preview, plus a full-size overlay for
 *      center widgets that are unreadable at 300px.
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
export class WidgetsGalleryComponent implements OnInit, OnDestroy {
  readonly store = inject(SessionStore);
  private readonly fixture = inject(GalleryFixtureService);

  readonly kindOrder = WIDGET_KIND_ORDER;
  readonly kindMeta = KIND_META;
  readonly provMeta = PROVENANCE_META;

  /** Capability axis, shown as a pill so "may this widget change anything?" is
   *  answerable from the gallery instead of from the source. */
  readonly writesLabel: Record<WidgetWrites, string> = {
    none: 'read-only',
    view: 'writes view',
    record: 'writes record',
    simulation: 'writes sim',
  };
  readonly writesBlurb: Record<WidgetWrites, string> = {
    none: 'Reads only — changes nothing.',
    view: 'Changes presentation state only (layers, tabs, selection). The simulation never sees it.',
    record: 'Writes the session record (decision log, reflection, rationale).',
    simulation: 'Can change what the simulation or the AI does — train overrides, policy, run control, KPI weights, mode.',
  };
  readonly modeOrder = MODE_ORDER;
  readonly modePresets = MODE_PRESETS;

  // ── Filter state ─────────────────────────────────────────────────────────
  /** Kinds are multi-select (empty = no kind filter). */
  readonly kindFilter = signal<ReadonlySet<WidgetKind>>(new Set());
  readonly modeFilter = signal<InteractionMode | 'all'>('all');
  /** v1 defaulted to 'shipped', which silently hid 8 of 33 widgets and made the
   *  search look broken. v2 shows everything and surfaces the distribution. */
  readonly statusFilter = signal<WidgetStatus | 'all'>('all');
  readonly provFilter = signal<WidgetDataSource | 'all'>('all');
  readonly query = signal<string>('');
  /** Show only widgets whose registry availability disagrees with the runtime map. */
  readonly driftOnly = signal(false);

  /** Expanded rows, by entry key. */
  private readonly expanded = signal<ReadonlySet<string>>(new Set());
  /** Chosen variant per role, when the operator switched away from the default. */
  private readonly variantChoice = signal<ReadonlyMap<string, string>>(new Map());
  /** The widget shown in the full-size preview overlay, if any. */
  readonly overlayWidget = signal<WidgetMeta | null>(null);

  // ── Catalog → entries ────────────────────────────────────────────────────
  /** Variant groups collapsed: widgets sharing a `role` become one entry. The
   *  registry has carried `role`/`variantLabel`/`variantDefault` since the
   *  variants plan, but v1 never rendered them — v1/v2 showed as unrelated cards. */
  private readonly allEntries = computed<GalleryEntry[]>(() => {
    const byRole = new Map<string, WidgetMeta[]>();
    const entries: GalleryEntry[] = [];

    for (const w of WIDGET_CATALOG) {
      if (!w.role) {
        entries.push({ widget: w, key: widgetKey(w), variants: [w] });
        continue;
      }
      const list = byRole.get(w.role);
      if (list) {
        list.push(w);
      } else {
        const fresh = [w];
        byRole.set(w.role, fresh);
        entries.push({ widget: w, key: `role:${w.role}`, variants: fresh });
      }
    }

    const choice = this.variantChoice();
    return entries.map((e) => {
      if (e.variants.length < 2) return e;
      const picked = choice.get(e.key);
      const hit = picked ? e.variants.find((v) => widgetKey(v) === picked) : undefined;
      const shown = hit ?? e.variants.find((v) => v.variantDefault) ?? e.variants[0];
      return { ...e, widget: shown };
    });
  });

  readonly total = computed(() => this.allEntries().length);

  // ── Filtering ────────────────────────────────────────────────────────────
  /** An entry matches when *any* of its variants matches — otherwise switching a
   *  variant could make the row you are looking at disappear under its own filter. */
  private matches(entry: GalleryEntry): boolean {
    return entry.variants.some((w) => this.matchesWidget(w));
  }

  private matchesWidget(w: WidgetMeta): boolean {
    const kinds = this.kindFilter();
    if (kinds.size && !kinds.has(w.kind)) return false;

    const status = this.statusFilter();
    if (status !== 'all' && w.status !== status) return false;

    const prov = this.provFilter();
    if (prov !== 'all' && w.dataSource !== prov) return false;

    const mode = this.modeFilter();
    if (mode !== 'all' && !widgetAvailableInMode(w, mode)) return false;

    if (this.driftOnly() && !this.availabilityMismatch(w)) return false;

    const q = this.query().trim().toLowerCase();
    if (q) {
      // v1 searched title + description + grounding only, so "tabbed" missed a
      // widget whose description says "One center container, tabbed".
      const haystack = [
        w.title,
        w.description,
        w.promise,
        w.grounding,
        w.type,
        w.catalogId ?? '',
        w.variantLabel ?? '',
        KIND_META[w.kind].label,
      ]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  }

  readonly groups = computed<GalleryGroup[]>(() => {
    const shown = this.allEntries().filter((e) => this.matches(e));
    return WIDGET_KIND_ORDER.map((kind) => ({
      kind,
      meta: KIND_META[kind],
      entries: shown.filter((e) => e.widget.kind === kind),
    })).filter((g) => g.entries.length > 0);
  });

  readonly shownCount = computed(() =>
    this.groups().reduce((n, g) => n + g.entries.length, 0),
  );

  readonly isFiltered = computed(
    () =>
      this.kindFilter().size > 0 ||
      this.modeFilter() !== 'all' ||
      this.statusFilter() !== 'all' ||
      this.provFilter() !== 'all' ||
      this.driftOnly() ||
      this.query().trim().length > 0,
  );

  // ── Governance tallies ───────────────────────────────────────────────────
  private countEntries(pred: (w: WidgetMeta) => boolean): number {
    return this.allEntries().filter((e) => pred(e.widget)).length;
  }

  readonly statusTally = computed(() =>
    (['shipped', 'first-cut', 'planned'] as WidgetStatus[]).map((id) => ({
      id,
      label: this.statusLabel(id),
      n: this.countEntries((w) => w.status === id),
    })),
  );

  readonly mockCount = computed(() =>
    this.countEntries((w) => w.dataSource === 'mock' || w.dataSource === 'mixed'),
  );

  /** v1 buried this as a ⚠ in the card footer; it is a governance signal about
   *  two sources of truth drifting apart, so v2 puts it in the header and makes
   *  it a filter. */
  readonly driftCount = computed(() => this.countEntries((w) => this.availabilityMismatch(w)));

  // ── Facets ───────────────────────────────────────────────────────────────
  readonly kindFacets = computed<Facet<WidgetKind>[]>(() =>
    WIDGET_KIND_ORDER.map((k) => ({
      id: k,
      label: KIND_META[k].label,
      colorVar: `var(${KIND_META[k].token})`,
      amount: this.countEntries((w) => w.kind === k),
    })),
  );

  readonly modeFacets: Facet<InteractionMode>[] = MODE_ORDER.map((m) => ({
    id: m,
    label: MODE_PRESETS[m].label,
    colorVar: null,
    amount: null,
  }));

  readonly statusFacets = computed<Facet<WidgetStatus>[]>(() =>
    (['shipped', 'first-cut', 'planned'] as WidgetStatus[]).map((s) => ({
      id: s,
      label: this.statusLabel(s),
      colorVar: this.statusColorVar(s),
      amount: this.countEntries((w) => w.status === s),
    })),
  );

  readonly provFacets = computed<Facet<WidgetDataSource>[]>(() =>
    (['simulation', 'derived', 'mixed', 'mock', 'none'] as WidgetDataSource[]).map((p) => ({
      id: p,
      label: PROVENANCE_META[p].label,
      colorVar: `var(${PROVENANCE_META[p].token})`,
      amount: this.countEntries((w) => w.dataSource === p),
    })),
  );

  // ── Filter actions ───────────────────────────────────────────────────────
  isKindActive(kind: WidgetKind): boolean {
    return this.kindFilter().has(kind);
  }

  toggleKind(kind: WidgetKind): void {
    const next = new Set(this.kindFilter());
    next.has(kind) ? next.delete(kind) : next.add(kind);
    this.kindFilter.set(next);
  }

  clearKinds(): void {
    this.kindFilter.set(new Set());
  }

  setModeFilter(mode: InteractionMode | 'all'): void {
    this.modeFilter.set(mode);
  }

  setStatusFilter(status: WidgetStatus | 'all'): void {
    this.statusFilter.set(status);
  }

  setProvFilter(prov: WidgetDataSource | 'all'): void {
    this.provFilter.set(prov);
  }

  toggleDriftOnly(): void {
    this.driftOnly.update((v) => !v);
  }

  resetFilters(): void {
    this.kindFilter.set(new Set());
    this.modeFilter.set('all');
    this.statusFilter.set('all');
    this.provFilter.set('all');
    this.driftOnly.set(false);
    this.query.set('');
  }

  // ── Rows ─────────────────────────────────────────────────────────────────
  isExpanded(entry: GalleryEntry): boolean {
    return this.expanded().has(entry.key);
  }

  toggleExpanded(entry: GalleryEntry): void {
    const next = new Set(this.expanded());
    next.has(entry.key) ? next.delete(entry.key) : next.add(entry.key);
    this.expanded.set(next);
  }

  pickVariant(entry: GalleryEntry, widget: WidgetMeta): void {
    const next = new Map(this.variantChoice());
    next.set(entry.key, widgetKey(widget));
    this.variantChoice.set(next);
  }

  isVariantActive(entry: GalleryEntry, widget: WidgetMeta): boolean {
    return widgetKey(entry.widget) === widgetKey(widget);
  }

  // ── Per-mode presentation (single entry point — see widget-mode-axes) ─────
  modeRows(widget: WidgetMeta): ModeRow[] {
    return modeRowsFor(widget);
  }

  sameInAllModes(widget: WidgetMeta): boolean {
    return sameInAllModes(widget);
  }

  isEmphasisedMode(mode: InteractionMode): boolean {
    const f = this.modeFilter();
    if (f !== 'all') return f === mode;
    return this.store.interactionMode() === mode;
  }

  /** Consistency check: registry availability vs the runtime availability map. */
  availabilityMismatch(widget: WidgetMeta): boolean {
    if (!widget.type) return false;
    return MODE_ORDER.some(
      (m) => widgetAvailableInMode(widget, m) !== isPanelAvailableInMode(widget.type, m),
    );
  }

  // ── Preview ──────────────────────────────────────────────────────────────
  canPreview(widget: WidgetMeta): boolean {
    return widget.status !== 'planned' && widget.type !== '';
  }

  openOverlay(widget: WidgetMeta): void {
    if (this.canPreview(widget)) this.overlayWidget.set(widget);
  }

  closeOverlay(): void {
    this.overlayWidget.set(null);
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

  // ── Fixture lifecycle ────────────────────────────────────────────────────
  // /widgets is an isolated authoring route with no real session. seed() fills
  // the store signals with gallery fixture data (only when no real session is
  // running) so previews render populated examples; ngOnDestroy's clear() resets
  // exactly those signals so the fixtures can never leak into a real run.
  ngOnInit(): void {
    this.fixture.seed();
  }

  ngOnDestroy(): void {
    this.fixture.clear();
  }

  // ── Cosmetics ────────────────────────────────────────────────────────────
  kindVar(kind: WidgetKind): string {
    return `var(${KIND_META[kind].token})`;
  }

  provVar(source: WidgetDataSource): string {
    return `var(${PROVENANCE_META[source].token})`;
  }

  statusColorVar(status: WidgetStatus): string {
    switch (status) {
      case 'shipped':
        return 'var(--app-positive)';
      case 'first-cut':
        return 'var(--app-severity-warn)';
      case 'planned':
        return 'var(--sbb-color-graphite)';
    }
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

  entryKey(widget: WidgetMeta): string {
    return widgetKey(widget);
  }

  trackByEntry = (_: number, e: GalleryEntry): string => e.key;
  trackByKind = (_: number, g: GalleryGroup): string => g.kind;
  trackByMode = (_: number, r: ModeRow): string => r.id;
  trackByWidget = (_: number, w: WidgetMeta): string => widgetKey(w);
}
