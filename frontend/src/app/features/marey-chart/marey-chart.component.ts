import {
  Component, CUSTOM_ELEMENTS_SCHEMA, computed, effect, inject, signal, ElementRef, viewChild, AfterViewInit, HostListener
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
import { ApiService } from '../../core/api.service';
import { RailTile, NextDecision, DecisionOption, AgentDTO } from '../../core/models';
import { AgentColorService } from '../../core/agent-color.service';
import { RailCellHoverService } from '../../services/rail-cell-hover.service';
import type { TrajectoryPoint } from '../../core/events/event-types';

type MareyTrajectoryPoint = TrajectoryPoint & {
  endStep?: number;
  durationSteps?: number;
  dwellSteps?: number;
  state?: string;
};

interface DecisionPill {
  /** Action int (0..4) — matches RailEnvActions / AgentDTO.override_action. */
  action: number;
  /** Label shown on the pill, e.g. "← Left". */
  label: string;
  /** True if the user already set this action as override. */
  isOverride: boolean;
  /** True if the active baseline policy would play this action at the
   *  next decision point — used to render the pill bold. */
  isRecommended: boolean;
}

interface DecisionGlyph {
  handle: number;
  color: string;
  /** SVG path 'M x y L x y L ...' along the cells from the agent's
   *  current position to the next decision cell, drawn at the current
   *  time-row in the Marey. */
  pathD: string;
  /** Centre of the decision marker (the 'o' at the end of the glyph). */
  decisionCx: number;
  decisionCy: number;
  /** Origin for the pill stack. */
  pillsX: number;
  pillsY: number;
  /** Pills shown next to the decision marker. */
  options: DecisionPill[];
  /** SWITCH or MERGING — controls marker style. */
  cellKind: 'switch' | 'merge';
}

interface AgentLine {
  handle: number;
  color: string;
  pastD: string;
  futureD: string;
  /** Overlay segments for compressed same-cell dwell intervals. */
  dwellD: string;
  isActive: boolean;
}

interface AgentLabel {
  handle: number;
  color: string;
  /** Index in pathCells where the agent first appears (used by HTML topology). */
  tileIndex: number;
  /** Anchor position (start of line). */
  x: number;
  y: number;
  /** Where to place the text (left/right of anchor based on motion direction). */
  textX: number;
  textY: number;
  textAnchor: "start" | "middle" | "end";
  /** Lead line endpoint (short dash before label). */
  lineX1: number;
  lineY1: number;
  lineX2: number;
  lineY2: number;
  isActive: boolean;
}

interface TopologyTile {
  svg: string;
  rot: number;
  xCoord: number;
  yCoord: number;
  step?: number;
  row?: number;
  col?: number;
  dir?: number;
  marey_topology?: string | null;
  marey_debug?: TrajectoryPoint['marey_debug'];
  marey_switch?: TrajectoryPoint['marey_switch'];
  marey_merge?: TrajectoryPoint['marey_merge'];
}

@Component({
  selector: 'app-marey-chart',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './marey-chart.component.html',
  styleUrls: ['./marey-chart.component.scss'],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class MareyChartComponent implements AfterViewInit {
  private readonly store = inject(SessionStore);
  private readonly api = inject(ApiService);
  private readonly colors = inject(AgentColorService);
  private readonly railHover = inject(RailCellHoverService);
  // ── decision-pill click (mirrors left-sidebar.onActionClick) ────
  // First click sets the override; second click on the same action
  // clears it. The store handles the API round-trip + state refresh,
  // and the sticky-override semantics in OverridePolicy mean the
  // action keeps applying at every decision point until cleared.
  onMareyPillClick(handle: number, action: number, isOverride: boolean): void {
    if (isOverride) {
      this.store.clearOverride(handle);
    } else {
      this.store.setOverride(handle, action);
    }
  }

  trajectoryCellInfoEnabled(): boolean {
    return this.isTrajectoryCellInfoEnabled();
  }

  private isTrajectoryCellInfoEnabled(): boolean {
    return this.store.layerVisibility().trajectoryCellInfo !== false;
  }

  private setRailCellHoverFromTopologyTile(tile: TopologyTile | null): void {
    if (!this.isTrajectoryCellInfoEnabled()) return;
    if (!tile || tile.row == null || tile.col == null) return;
    this.railHover.setHoveredCell(`${tile.row},${tile.col}`, 'marey', null);
  }

  onTopologyTileEnter(tile: TopologyTile | null, ev: MouseEvent): void {
    if (!this.isTrajectoryCellInfoEnabled()) return;
    if (!tile) return;
    this.setRailCellHoverFromTopologyTile(tile);

    const current = this.topologyTooltip();
    if (current?.pinned) return;

    this.topologyTooltip.set({
      tile,
      x: ev.clientX + 14,
      y: ev.clientY + 14,
      pinned: false,
    });
  }

  onTopologyTileMove(ev: MouseEvent): void {
    if (!this.isTrajectoryCellInfoEnabled()) return;
    const current = this.topologyTooltip();
    if (!current || current.pinned) return;

    this.topologyTooltip.set({
      ...current,
      x: ev.clientX + 14,
      y: ev.clientY + 14,
    });
  }

  onTopologyTileLeave(): void {
    const current = this.topologyTooltip();
    if (current?.pinned) return;
    this.railHover.clearHoveredCell();
    this.topologyTooltip.set(null);
  }

  onTopologyTileClick(tile: TopologyTile | null, ev: MouseEvent): void {
    if (!this.isTrajectoryCellInfoEnabled()) return;
    if (!tile) return;

    // Important: do not let this click bubble into agent/map selection logic.
    ev.preventDefault();
    ev.stopPropagation();

    this.setRailCellHoverFromTopologyTile(tile);

    this.topologyTooltip.set({
      tile,
      x: ev.clientX + 14,
      y: ev.clientY + 14,
      pinned: true,
    });
  }

  closeTopologyTooltip(): void {
    this.railHover.clearHoveredCell();
    this.topologyTooltip.set(null);
  }

  @HostListener('document:keydown.escape')
  onTopologyTooltipEscape(): void {
    this.closeTopologyTooltip();
  }

  @HostListener('document:mousedown', ['$event'])
  onTopologyTooltipDocumentMouseDown(ev: MouseEvent): void {
    const current = this.topologyTooltip();
    if (!current?.pinned) return;

    const target = ev.target as HTMLElement | null;
    if (!target) return;

    // Click inside tooltip: keep it open and do not affect train selection.
    if (target.closest('.marey-topology-tooltip')) return;

    // Click on a topology tile is handled by onTopologyTileClick.
    if (target.closest('.topo-cell.has-topology-tooltip')) return;

    this.closeTopologyTooltip();
  }

  isTopologyTileRailHovered(tile: TopologyTile | null): boolean {
    if (!this.isTrajectoryCellInfoEnabled()) return false;
    if (!tile || tile.row == null || tile.col == null) return false;
    return this.railHover.hoveredCellKey() === `${tile.row},${tile.col}`;
  }

  private dirName(value: unknown): string {
    if (value === null || value === undefined) return "–";

    const n = Number(value);
    if (!Number.isFinite(n)) return String(value);

    switch (((n % 4) + 4) % 4) {
      case 0: return "North ↑";
      case 1: return "East →";
      case 2: return "South ↓";
      case 3: return "West ←";
      default: return String(value);
    }
  }

  private dirList(values: unknown): string {
    if (!Array.isArray(values) || values.length === 0) return "–";
    return values.map((v) => this.dirName(v)).join(", ");
  }

  private plainList(values: unknown): string {
    if (!Array.isArray(values) || values.length === 0) return "–";
    return values.map((v) => String(v)).join(", ");
  }

  topologyHumanLabel(tile: TopologyTile): string {
    const topology = String(tile.marey_topology ?? "topology");

    switch (topology) {
      case "straight": return "Straight track";
      case "switch": return "Switch / Weiche";
      case "merge": return "Merge / Zusammenführung";
      case "switch_merge": return "Switch + merge";
      case "diamond": return "Diamond crossing";
      case "unknown": return "Unknown topology";
      default: return topology;
    }
  }

  directionHumanLabel(value: unknown): string {
    return this.dirName(value);
  }

  topologyReason(tile: TopologyTile): string {
    const debug = tile.marey_debug as Record<string, unknown> | null | undefined;
    const reason = debug?.["classification_reason"];
    return typeof reason === "string" && reason.trim() ? reason.trim() : "–";
  }

  possibleOutgoingHumanLabel(tile: TopologyTile): string {
    const debug = tile.marey_debug as Record<string, unknown> | null | undefined;
    return this.dirList(debug?.["possible_out_dirs"]);
  }

  possibleIncomingHumanLabel(tile: TopologyTile): string {
    const debug = tile.marey_debug as Record<string, unknown> | null | undefined;
    const raw = debug?.["possible_in_dirs_for_out"];

    if (!raw || typeof raw !== "object") return "–";

    const entries = Object.entries(raw as Record<string, unknown>);
    if (entries.length === 0) return "–";

    return entries
      .map(([outDir, inDirs]) => `${this.dirName(outDir)} from ${this.dirList(inDirs)}`)
      .join("; ");
  }

  transitionCountHumanLabel(tile: TopologyTile): string {
    const debug = tile.marey_debug as Record<string, unknown> | null | undefined;
    const transitions = debug?.["possible_transitions"];

    if (!Array.isArray(transitions)) return "–";
    return `${transitions.length}`;
  }

  switchTakenHumanLabel(tile: TopologyTile): string {
    const sw = tile.marey_switch as Record<string, unknown> | null | undefined;
    return this.dirName(sw?.["taken"]);
  }

  switchNotTakenHumanLabel(tile: TopologyTile): string {
    const sw = tile.marey_switch as Record<string, unknown> | null | undefined;
    return this.dirList(sw?.["not_taken"]);
  }

  switchPossibleExitsHumanLabel(tile: TopologyTile): string {
    const sw = tile.marey_switch as Record<string, unknown> | null | undefined;
    return this.dirList(sw?.["possible_exits"]);
  }

  mergeArrivedFromHumanLabel(tile: TopologyTile): string {
    const merge = tile.marey_merge as Record<string, unknown> | null | undefined;
    return this.dirName(merge?.["arrived_from"]);
  }

  mergeOtherInputsHumanLabel(tile: TopologyTile): string {
    const merge = tile.marey_merge as Record<string, unknown> | null | undefined;
    return this.dirList(merge?.["other_inputs"]);
  }

  mergePossibleInputsHumanLabel(tile: TopologyTile): string {
    const merge = tile.marey_merge as Record<string, unknown> | null | undefined;
    return this.dirList(merge?.["possible_inputs"]);
  }

  hasReadableDebug(tile: TopologyTile): boolean {
    return !!tile.marey_debug;
  }

  topologyTileTitle(tile: TopologyTile): string {
    const parts: string[] = [];

    if (tile.step !== undefined) parts.push(`step ${tile.step}`);
    if (tile.row !== undefined && tile.col !== undefined) parts.push(`cell ${tile.row},${tile.col}`);
    if (tile.marey_topology) parts.push(String(tile.marey_topology));
    if (tile.svg) parts.push(tile.svg);

    return parts.join(" · ");
  }

  private readonly svgRef = viewChild<ElementRef<SVGSVGElement>>('svgEl');
  private svgEl: SVGSVGElement | null = null;

  constructor() {
    // Re-bind svgEl whenever the @else branch (re)mounts the SVG.
    effect(() => {
      const ref = this.svgRef();
      if (ref) this.svgEl = ref.nativeElement;
    });

    // Auto-reset xRange to the full path whenever pathCells changes
    // (active agent switched, scenario reloaded, …). The user can
    // narrow it again via the X-slider in Etappe 4.
    effect(() => {
      const n = this.pathCells().length;
      if (n > 0) {
        this.xRange.set({ start: 0, end: n - 1 });
      }
    });

    // Auto-reset yRange to the full time horizon whenever maxSteps
    // changes (new session / new scenario).
    effect(() => {
      const m = this.maxSteps();
      if (m > 0) {
        this.yRange.set({ start: 0, end: m });
      }
    });
  }

  readonly W = 1200;
  readonly H = 700;
  readonly PAD = { top: 16, right: 0, bottom: 36, left: 0 };

  /** Grid toggle: bound to the global layer-visibility checkbox in
   *  the left sidebar so Marey + Map share one source of truth. */
  readonly showGrid = computed(() => this.store.layerVisibility().grid);

  /** Width of one path-cell column = tile size in the topology strip. */
  readonly tileSize = computed(() => {
    const cells = this.pathCells();
    if (cells.length < 2) return this.TOPOLOGY_PX;
    return Math.abs(this.pathCoord(1) - this.pathCoord(0));
  });

  readonly activeHandle = this.store.activeHandle;
  readonly elapsed = computed(() => this.store.state()?.elapsed_steps ?? 0);
  readonly maxSteps = computed(() => this.store.maxSteps() || 1);
  readonly scenarios = this.store.scenarios;
  readonly forecastScenarioId = signal<string | null>(null);
  readonly topologyTooltip = signal<{ tile: TopologyTile; x: number; y: number; pinned: boolean } | null>(null);

  // viewport: pan + dual-axis zoom
  readonly panX = signal(0);
  readonly panY = signal(0);
  readonly zoomX = signal(1);
  readonly zoomY = signal(1);

  /** Visible Tile-Index range on the X (path) axis. start/end inclusive.
   *  Default: full path. The topology overlay AND the SVG chart both
   *  read this signal — that's the structural sync guarantee. */
  readonly xRange = signal<{ start: number; end: number }>({ start: 0, end: 0 });

  /** Visible Step range on the Y (time) axis. Default: full time. */
  readonly yRange = signal<{ start: number; end: number }>({ start: 0, end: 0 });

  /** Topology header height in CSS pixels (matches HTML overlay). */
  readonly TOPOLOGY_PX = 48; readonly GLYPH_PX = 64;


  /** CSS transform for the HTML topology track, driven by xRange.
   *  The flex track is N tiles wide at 100%. To show only [start, end]:
   *    - scaleX(N / visible)   makes the visible window fill 100%
   *    - translateX(-start/N*100%)  moves 'start' to the left edge
   *  Order in CSS string: scale first (= applied last math), translate
   *  applied first in element-local space (% of own width). */
  readonly topologyTrackTransform = computed(() => {
    const n = this.pathCells().length;
    if (n === 0) return "none";
    const r = this.xRange();
    const visible = Math.max(1, r.end - r.start + 1);
    const sx = n / visible;
    // translate is in element-local % (of own width). To pan so that
    // tile r.start sits at the left edge, we shift by -(r.start * sx /
    // n) * 100% which simplifies to -(r.start / visible) * 100% after
    // applying scaleX. Order matters: scale first, then translate.
    const tx = -(r.start / visible) * 100;
    return `translateX(${tx}%) scaleX(${sx})`;
  });


  // ── Y-Range Brush (Etappe 5) ─────────────────────────────────
  /** Brush window top edge as % of total time span. */
  readonly yBrushTopPct = computed(() => {
    const m = this.maxSteps();
    if (m <= 0) return 0;
    return (this.yRange().start / m) * 100;
  });
  /** Brush window height as % of total time span. */
  readonly yBrushHeightPct = computed(() => {
    const m = this.maxSteps();
    if (m <= 0) return 100;
    const r = this.yRange();
    return ((r.end - r.start) / m) * 100;
  });

  /** Pointer-driven vertical brush drag.
   *  mode: 'top'    = drag top handle, bottom stays fixed
   *        'bottom' = drag bottom handle, top stays fixed
   *        'window' = drag whole window (both edges move) */
  onYBrushDown(ev: MouseEvent, mode: 'top'|'bottom'|'window', track: HTMLElement): void {
    ev.preventDefault();
    ev.stopPropagation();
    const m = this.maxSteps();
    if (m <= 0) return;
    const rect = track.getBoundingClientRect();
    const startY = ev.clientY;
    const startRange = { ...this.yRange() };
    const pxPerStep = rect.height / m;

    const onMove = (e: MouseEvent) => {
      const dy = e.clientY - startY;
      const dSteps = Math.round(dy / pxPerStep);
      let { start, end } = startRange;
      if (mode === 'top') {
        start = Math.max(0, Math.min(end - 1, startRange.start + dSteps));
      } else if (mode === 'bottom') {
        end = Math.max(start + 1, Math.min(m, startRange.end + dSteps));
      } else {
        const width = startRange.end - startRange.start;
        let ns = startRange.start + dSteps;
        if (ns < 0) ns = 0;
        if (ns + width > m) ns = m - width;
        start = ns;
        end = ns + width;
      }
      this.yRange.set({ start, end });
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }

  // ── X-Range Brush (Etappe 4) ─────────────────────────────────
  /** Brush window left edge as % of the full path span. */
  readonly brushWindowLeftPct = computed(() => {
    const n = this.pathCells().length;
    if (n === 0) return 0;
    return (this.xRange().start / n) * 100;
  });
  /** Brush window width as % of the full path span. */
  readonly brushWindowWidthPct = computed(() => {
    const n = this.pathCells().length;
    if (n === 0) return 100;
    const r = this.xRange();
    return ((r.end - r.start + 1) / n) * 100;
  });

  /** Pointer-driven brush drag. mode = which part is being grabbed.
   *  'left'   = drag start handle, end stays fixed
   *  'right'  = drag end handle, start stays fixed
   *  'window' = drag whole window, both edges move together (pan)
   *  Pixel→tile mapping uses the brush track's own client width so
   *  it stays correct under any container size. */
  onBrushDown(ev: MouseEvent, mode: 'left'|'right'|'window', track: HTMLElement): void {
    ev.preventDefault();
    ev.stopPropagation();
    const n = this.pathCells().length;
    if (n === 0) return;
    const rect = track.getBoundingClientRect();
    const startX = ev.clientX;
    const startRange = { ...this.xRange() };
    const pxPerTile = rect.width / n;

    const onMove = (e: MouseEvent) => {
      const dx = e.clientX - startX;
      const dTiles = Math.round(dx / pxPerTile);
      let { start, end } = startRange;
      if (mode === 'left') {
        start = Math.max(0, Math.min(end - 1, startRange.start + dTiles));
      } else if (mode === 'right') {
        end = Math.max(start + 1, Math.min(n - 1, startRange.end + dTiles));
      } else {
        // window pan — keep width, shift both edges, clamp to [0, n-1]
        const width = startRange.end - startRange.start;
        let ns = startRange.start + dTiles;
        if (ns < 0) ns = 0;
        if (ns + width > n - 1) ns = n - 1 - width;
        start = ns;
        end = ns + width;
      }
      this.xRange.set({ start, end });
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }

  /** Swap axes: false = time vertical (default), true = time horizontal. */
  readonly axesSwapped = signal(false);

  /** viewBox is fixed at the full chart canvas. All zoom/pan is now
   *  expressed via xRange/yRange in the coord helpers, so we don't
   *  double-transform here. The old panX/panY/zoomX/zoomY signals
   *  remain for backwards-compat with pan/zoom buttons; a thin layer
   *  in Etappe 4/5 will translate them into xRange/yRange writes. */
  readonly viewBox = computed(() => `0 0 ${this.W} ${this.H}`);

  /** Display-friendly zoom percentage (geometric mean of X+Y zoom). */
  readonly zoomPct = computed(() => {
    const z = Math.sqrt(this.zoomX() * this.zoomY());
    return Math.round(z * 100);
  });

  // drag state
  private isDragging = false;
  private dragStartX = 0;
  private dragStartY = 0;
  private dragStartPanX = 0;
  private dragStartPanY = 0;

  ngAfterViewInit(): void {
    this.svgEl = this.svgRef()?.nativeElement ?? null;
  }

  notificationHoverHandleCount(): number {
    return this.store.notificationHoverHandles().size;
  }

  isNotificationHovered(handle: number): boolean {
    return this.store.notificationHoverHandles().has(handle);
  }
  mareyAgentLineColor(handle: number, fallbackColor?: string | null): string {
    if (fallbackColor && String(fallbackColor).trim().length > 0) {
      return String(fallbackColor);
    }

    const anyThis = this as any;
    if (anyThis.agentColors?.getColor) {
      try {
        return anyThis.agentColors.getColor(handle, 'default');
      } catch {
        // fall through
      }
    }

    const palette = [
      '#0079c7', '#00973b', '#ff9800', '#6f42c1',
      '#00a1de', '#2e7d32', '#ad1457', '#795548',
    ];
    return palette[Math.abs(handle) % palette.length];
  }

  mareyHoverLineColor(handle: number, fallbackColor?: string | null): string {
    // Line highlighting in Marey is hover/cross-hover only.
    // If explicitly selected, hover highlight uses edit magenta.
    // Otherwise it uses the agent's own line color.
    if (this.store.selectedHandle() === handle) return '#f939e9';
    return this.mareyAgentLineColor(handle, fallbackColor);
  }
  mareyAgentDisplayColor(handle: number, fallbackColor?: string | null): string {
    // Only explicit user click gets edit color.
    // Do NOT use activeHandle(): activeHandle may be default/fallback.
    if (this.store.selectedHandle() === handle) return '#f939e9';

    if (fallbackColor && String(fallbackColor).trim().length > 0) {
      return String(fallbackColor);
    }

    return this.mareyAgentLineColor(handle, fallbackColor);
  }



  onAgentMouseEnter(handle: number): void {
    this.store.setAgentHoverAgent(handle);
  }

  onAgentMouseLeave(): void {
    this.store.clearAgentHoverAgents();
  }

  isAgentMalfunctioning(handle: number): boolean {
    return this.store.agents().some((a) =>
      a.handle === handle
      && (
        !!a.is_malfunctioning
        || (a.malfunction_remaining ?? 0) > 0
        || String(a.state ?? '').includes('MALFUNCTION')
      )
    );
  }

  agentMalfunctionTitle(handle: number): string {
    const a = this.store.agents().find((x) => x.handle === handle);
    const remaining = a?.malfunction_remaining ?? 0;
    return remaining > 0
      ? `Malfunction: ${remaining} step(s) remaining`
      : 'Malfunction';
  }

  // ── data: scenario + path + agent lines ──────────────────────
  readonly forecastScenario = computed(() => {
    // Priority: hover-preview from a scenario card → local override
    // (kept for direct API) → baseline (= currently active policy).
    const all = this.scenarios();
    if (!all || all.length === 0) return null;
    const previewId = this.store.previewScenarioId();
    if (previewId) {
      const f = all.find(s => s.id === previewId);
      if (f) return f;
    }
    const localId = this.forecastScenarioId();
    if (localId) {
      const f = all.find(s => s.id === localId);
      if (f) return f;
    }
    return all.find(s => s.isBaseline) ?? all[0];
  });


  compressMareyTrajectoryRuns<T extends {
    step: number;
    endStep?: number;
    durationSteps?: number;
    dwellSteps?: number;
    row: number;
    col: number;
    dir: number;
    state?: string;
  }>(points: T[]): T[] {
    const sorted = [...points].sort((a, b) => a.step - b.step);
    const out: T[] = [];

    for (const p of sorted) {
      const last = out[out.length - 1];

      // Consecutive compression: only compare with immediate previous run.
      // Same cell later after another cell remains a new run.
      if (last && last.row === p.row && last.col === p.col) {
        const endStep = Math.max(last.endStep ?? last.step, p.endStep ?? p.step);
        const durationSteps = Math.max(1, endStep - last.step + 1);

        out[out.length - 1] = {
          ...last,
          endStep,
          durationSteps,
          dwellSteps: durationSteps,
          // Keep latest metadata for the run.
          dir: p.dir,
          state: p.state ?? last.state,
        };
      } else {
        const endStep = p.endStep ?? p.step;
        const durationSteps = p.durationSteps
          ?? p.dwellSteps
          ?? Math.max(1, endStep - p.step + 1);

        out.push({
          ...p,
          endStep,
          durationSteps,
          dwellSteps: p.dwellSteps ?? durationSteps,
        });
      }
    }

    return out;
  }

  readonly mareyData = signal<any | null>(null);

  private readonly mareyDataRefreshEffect = effect(() => {
    const sessionId = this.store.session()?.id ?? null;
    const elapsed = this.store.state()?.elapsed_steps ?? null;
    const showMarey = this.store.showMarey();
    const previewScenarioId = this.store.previewScenarioId();

    // Explicit signal dependencies.
    void elapsed;
    void previewScenarioId;

    if (!showMarey || !sessionId) return;

    this.refreshMareyData();
  });

  private refreshMareyData(): void {
    const session = this.store.session();
    if (!session) return;

    this.api.getMareyData(session.id).subscribe({
      next: (data: any) => this.mareyData.set(data),
      error: () => {
        // Keep UI robust: backend-history can fail; local-history fallback remains.
        this.mareyData.set(null);
      },
    });
  }

  private normalizeBackendMareyPoint(p: any): MareyTrajectoryPoint | null {
    if (!p) return null;

    const row = p.row ?? p.position?.[0];
    const col = p.col ?? p.position?.[1];
    const dir = p.dir ?? p.direction ?? 0;
    const step = p.step;

    if (row == null || col == null || step == null) return null;

    const endStep = p.endStep ?? p.end_step ?? p.step;
    const durationSteps =
      p.durationSteps ??
      p.duration_steps ??
      p.dwellSteps ??
      p.dwell_steps ??
      Math.max(1, Number(endStep) - Number(step) + 1);

    return {
      ...(p as Partial<MareyTrajectoryPoint>),
      step: Number(step),
      endStep: Number(endStep),
      durationSteps: Number(durationSteps),
      dwellSteps: Number(p.dwellSteps ?? p.dwell_steps ?? durationSteps),
      row: Number(row),
      col: Number(col),
      dir: Number(dir),
      direction: Number(dir),
      position: [Number(row), Number(col)],
      state: p.state ?? "MOVING",
    } as MareyTrajectoryPoint;
  }

  readonly backendHistoryTrajectories = computed<Record<string, MareyTrajectoryPoint[]>>(() => {
    const data = this.mareyData();
    const agents = data?.agents ?? {};
    const out: Record<string, MareyTrajectoryPoint[]> = {};

    for (const [handle, agentData] of Object.entries(agents as Record<string, any>)) {
      const history = Array.isArray(agentData?.history) ? agentData.history : [];
      out[String(handle)] = history
        .map((p: any) => this.normalizeBackendMareyPoint(p))
        .filter((p: MareyTrajectoryPoint | null): p is MareyTrajectoryPoint => !!p);
    }

    return out;
  });

  readonly mergedTrajectories = computed<Record<string, MareyTrajectoryPoint[]>>(() => {
    const sc = this.forecastScenario();
    const now = this.elapsed();
    if (!sc) return {};

    const forecast = sc.trajectories ?? {};
    const history = this.store.trajectories();
    const backendHistory = this.backendHistoryTrajectories();
    const handles = new Set<string>([
      ...Object.keys(forecast),
      ...Array.from(history.keys()).map((h) => String(h)),
    ]);

    const out: Record<string, MareyTrajectoryPoint[]> = {};
    for (const handleStr of handles) {
      const h = Number(handleStr);
      const localHist = (history.get(h) ?? [])
        .filter((p) => p.position != null && p.step <= now)
        .map((p): MareyTrajectoryPoint => ({
          ...(p as unknown as Partial<MareyTrajectoryPoint>),
          step: p.step,
          endStep: p.endStep ?? p.step,
          durationSteps: p.durationSteps ?? p.dwellSteps ?? Math.max(1, (p.endStep ?? p.step) - p.step + 1),
          dwellSteps: p.dwellSteps ?? p.durationSteps ?? Math.max(1, (p.endStep ?? p.step) - p.step + 1),
          row: p.position![0],
          col: p.position![1],
          dir: p.direction ?? 0,
          state: p.state,
        }));

      const apiHist = backendHistory[handleStr] ?? [];

      // Preferred: backend-enriched executed history.
      // Fallback: local frontend history for old/pre-patch sessions.
      const hist = apiHist.length > 0 ? apiHist.filter((p: MareyTrajectoryPoint) => p.step <= now) : localHist;

      const fut = (forecast[handleStr] ?? [])
        .filter((p) => p.step > now)
        .map((p): MareyTrajectoryPoint => ({
          ...p,
          step: p.step,
          endStep: p.step,
          durationSteps: 1,
          dwellSteps: 1,
          row: p.row,
          col: p.col,
          dir: p.dir,
        }));

      const merged = [...hist, ...fut] as MareyTrajectoryPoint[];
      const compressed = this.compressMareyTrajectoryRuns(merged) as MareyTrajectoryPoint[];

      // compressMareyTrajectoryRuns may normalize points. Re-attach backend
      // Marey metadata from the source point so pathTiles can use marey_svg.
      out[handleStr] = compressed.map((point) => {
        const source = merged.find((candidate) =>
          candidate.step === point.step &&
          candidate.row === point.row &&
          candidate.col === point.col
        );

        if (!source) return point;

        return {
          ...source,
          ...point,
          marey_topology: point.marey_topology ?? source.marey_topology,
          marey_svg: point.marey_svg ?? source.marey_svg,
          marey_debug: point.marey_debug ?? source.marey_debug,
          marey_switch: point.marey_switch ?? source.marey_switch,
          marey_merge: point.marey_merge ?? source.marey_merge,
          handle: point.handle ?? source.handle,
          agent_id: point.agent_id ?? source.agent_id,
        };
      });
    }
    return out;
  });

  readonly pathCells = computed<string[]>(() => {
    const handle = this.activeHandle();
    const tr = this.mergedTrajectories();
    if (handle == null) return [];
    const traj = tr[String(handle)] ?? [];
    // Keep every step-cell (including repeated dwells on the same cell).
    // This makes the topology visibly longer when an agent is delayed,
    // blocked, or misses the target horizon.
    return traj.map((p) => `${p.row},${p.col}`);
  });

  readonly pathIndex = computed<Map<string, number[]>>(() => {
    const m = new Map<string, number[]>();
    this.pathCells().forEach((k, i) => {
      const arr = m.get(k);
      if (arr) arr.push(i);
      else m.set(k, [i]);
    });
    return m;
  });

  private numericDir(value: unknown): number | null {
    if (value === null || value === undefined) return null;
    const n = Number(value);
    if (!Number.isFinite(n)) return null;
    return ((Math.trunc(n) % 4) + 4) % 4;
  }

  private firstNumericDir(value: unknown): number | null {
    if (Array.isArray(value)) {
      for (const item of value) {
        const n = this.numericDir(item);
        if (n !== null) return n;
      }
      return null;
    }

    return this.numericDir(value);
  }

  private oppositeDir(value: unknown): number | null {
    const n = this.numericDir(value);
    return n === null ? null : (n + 2) % 4;
  }

  /**
   * Direction side in driver-view.
   *
   * Flatland directions:
   *   0=N, 1=E, 2=S, 3=W
   *
   * Relative to forwardDir:
   *   +1 = right
   *   +3 = left
   */
  private relativeSide(
    targetDir: unknown,
    forwardDir: unknown,
  ): "left" | "right" | "straight" | "back" | "unknown" {
    const target = this.numericDir(targetDir);
    const forward = this.numericDir(forwardDir);

    if (target === null || forward === null) return "unknown";

    const rel = (target - forward + 4) % 4;
    if (rel === 0) return "straight";
    if (rel === 1) return "right";
    if (rel === 2) return "back";
    if (rel === 3) return "left";

    return "unknown";
  }

  private mareySwitchInfo(point: MareyTrajectoryPoint): Record<string, unknown> | null {
    return point.marey_switch && typeof point.marey_switch === "object"
      ? point.marey_switch as Record<string, unknown>
      : null;
  }

  private mareyMergeInfo(point: MareyTrajectoryPoint): Record<string, unknown> | null {
    return point.marey_merge && typeof point.marey_merge === "object"
      ? point.marey_merge as Record<string, unknown>
      : null;
  }

  private driverViewSwitchSvg(point: MareyTrajectoryPoint, tile?: RailTile | null, next?: MareyTrajectoryPoint | null): string {
    const sw = this.mareySwitchInfo(point);

    const taken = this.firstNumericDir(sw?.["taken"]) ?? this.numericDir(point.dir) ?? this.numericDir(next?.dir) ?? 0;
    let other = this.firstNumericDir(sw?.["not_taken"]);

    // History fallback: no backend switch metadata. Infer side from the
    // actually taken direction change. The driven path is straightened;
    // if the train turns left, the non-taken branch is shown on the right,
    // and vice versa.
    if (other === null && tile) {
      const curDir = this.numericDir(point.dir);
      const nextDir = this.numericDir(next?.dir);
      if (curDir !== null && nextDir !== null) {
        const relTaken = (nextDir - curDir + 4) % 4;
        if (relTaken === 3) other = (taken + 1) % 4; // taken left -> other right
        else if (relTaken === 1) other = (taken + 3) % 4; // taken right -> other left
      }
    }

    const side = this.relativeSide(other, taken);

    // Driver-view switch:
    // - own route is straight
    // - not-taken branch leaves to left/right
    if (side === "right") return "Weiche_horizontal_unten_links.svg";
    return "Weiche_horizontal_oben_links.svg";
  }

  private driverViewMergeSvg(point: MareyTrajectoryPoint, tile?: RailTile | null, prev?: MareyTrajectoryPoint | null): string {
    const merge = this.mareyMergeInfo(point);

    // For merges, other_inputs are incoming directions into the merge.
    // To decide whether the other track COMES FROM left/right, we compare
    // the source side of that input, i.e. opposite(other_input), against
    // the train's own forward direction.
    const ownForward =
      this.firstNumericDir(merge?.["arrived_from"]) ??
      this.numericDir(point.dir);

    let otherInput = this.firstNumericDir(merge?.["other_inputs"]);
    let otherSourceSide = this.oppositeDir(otherInput);

    // History fallback: no backend merge metadata. If this looks like a
    // switch/merge tile and we know the previous direction, use the tile name
    // as a weak hint. This is intentionally conservative: it prevents
    // history from becoming all-straight while keeping the driven route flat.
    if (otherSourceSide === null && tile) {
      const svg = tile.svg || "";
      if (svg.includes("_oben_")) otherSourceSide = (this.numericDir(point.dir) ?? 1) + 3;
      else if (svg.includes("_unten_")) otherSourceSide = (this.numericDir(point.dir) ?? 1) + 1;
    }

    const side = this.relativeSide(otherSourceSide, ownForward);

    // Driver-view merge:
    // - own route is straight
    // - other track joins from left/right
    if (side === "right") return "Weiche_horizontal_unten_rechts.svg";
    return "Weiche_horizontal_oben_rechts.svg";
  }

  private driverViewTopologySvg(
    point: MareyTrajectoryPoint,
    tile?: RailTile | null,
    prev?: MareyTrajectoryPoint | null,
    next?: MareyTrajectoryPoint | null,
  ): string {
    const topology = String(point.marey_topology ?? "").trim();
    const backendSvg = String(point.marey_svg ?? "").trim();
    const tileSvg = String(tile?.svg ?? "").trim();
    const sourceSvg = backendSvg || tileSvg;

    // Special topologies must win before generic switch/merge handling.
    if (
      topology === "diamond" ||
      sourceSvg.includes("Diamond_Crossing")
    ) {
      return "Gleis_Diamond_Crossing.svg";
    }

    if (sourceSvg.includes("Double_Slip")) {
      return "Weiche_Double_Slip.svg";
    }

    if (sourceSvg.includes("Single_Slip")) {
      return "Weiche_Single_Slip.svg";
    }

    // Important: do NOT use backend marey_svg directly for normal switches.
    // marey_svg describes the map/topology tile. The Marey header needs
    // a straightened driver-view symbol.
    if (point.marey_switch || topology === "switch" || topology === "switch_merge") {
      return this.driverViewSwitchSvg(point, tile, next);
    }

    if (point.marey_merge || topology === "merge") {
      return this.driverViewMergeSvg(point, tile, prev);
    }

    // History fallback: points from store.trajectories() often do not carry
    // marey_* metadata. If the underlying map cell is a special tile, still
    // render a driver-view symbol instead of flattening everything.
    if (tileSvg.startsWith("Weiche_")) {
      // Without metadata we cannot reliably distinguish switch vs merge.
      // Use suffix as weak visual hint: left-side variants as switch,
      // right-side variants as merge.
      if (tileSvg.includes("_rechts")) {
        return this.driverViewMergeSvg(point, tile, prev);
      }
      return this.driverViewSwitchSvg(point, tile, next);
    }

    return "Gleis_horizontal.svg";
  }


  /** Marey-Topologie in driver-view:
   *  the train's own path is always straightened horizontally.
   *
   *  Switch:
   *    other branch leaves left  -> Weiche_horizontal_oben_links.svg
   *    other branch leaves right -> Weiche_horizontal_unten_links.svg
   *
   *  Merge:
   *    other branch joins from left  -> Weiche_horizontal_oben_rechts.svg
   *    other branch joins from right -> Weiche_horizontal_unten_rechts.svg
   */
  readonly pathTiles = computed<(TopologyTile | null)[]>(() => {
    const handle = this.activeHandle();
    const cells = this.pathCells();
    const tr = this.mergedTrajectories();
    if (handle == null || cells.length === 0) return [];

    const traj = tr[String(handle)] ?? [];
    if (traj.length === 0) return [];

    const tilesByKey = new Map<string, RailTile>();
    for (const t of this.store.railTiles()) tilesByKey.set(`${t.r},${t.c}`, t);

    const out: (TopologyTile | null)[] = [];

    for (let i = 0; i < cells.length; i++) {
      const key = cells[i];
      const tile = tilesByKey.get(key);

      // pathCells() is built from traj.map(...), therefore index i is the
      // correct trajectory point, including repeated dwell cells.
      const cur = traj[i];
      const prev = i > 0 ? traj[i - 1] : null;
      const next = i < traj.length - 1 ? traj[i + 1] : null;

      const [keyRow, keyCol] = key.split(",").map((v) => Number(v));
      const xCoord = this.axesSwapped() ? this.PAD.left + 18 : this.pathCoord(i);
      const yCoord = this.axesSwapped() ? this.pathCoord(i) : this.TOPOLOGY_PX / 2;

      if (!cur) {
        out.push({
          svg: "Gleis_horizontal.svg",
          rot: 0,
          xCoord,
          yCoord,
          row: keyRow,
          col: keyCol,
        });
        continue;
      }

      out.push({
        svg: this.driverViewTopologySvg(cur, tile, prev, next),
        rot: 0,
        xCoord,
        yCoord,
        step: cur.step,
        row: cur.row ?? keyRow,
        col: cur.col ?? keyCol,
        dir: cur.dir,
        marey_topology: cur.marey_topology,
        marey_debug: cur.marey_debug,
        marey_switch: cur.marey_switch,
        marey_merge: cur.marey_merge,
      });
    }

    return out;
  });



  /** Subset of pathTiles inside xRange — used by the main topology
   *  header [2]. Mini-topology in [6] keeps using full pathTiles(). */
  readonly pathTilesVisible = computed(() => {
    const all = this.pathTiles();
    const r = this.xRange();
    const end = Math.min(all.length, r.end + 1);
    return all.slice(r.start, end);
  });

  // ── decision glyph (active agent only) ──────────────────────────
  // Mirrors the path-to-next-decision visual from flatland-map:
  // a polyline of arrows from the agent's current cell to its next
  // SWITCH/MERGING cell, with action pills at the end. The bold pill
  // is the action the active baseline policy would play, derived from
  // the forecast trajectory's direction change at the decision cell.
  readonly decisionGlyph = computed<DecisionGlyph | null>(() => {
    if (!this.store.layerVisibility().nextDecisions) return null;

    const handle = this.activeHandle();
    if (handle == null) return null;

    const agents = this.store.agents();
    const agent: AgentDTO | undefined = agents.find(a => a.handle === handle);
    if (!agent || !agent.next_decision || !agent.position) return null;
    if (this.axesSwapped()) return null;  // glyph layout assumes X=cells, Y=time

    const nd: NextDecision = agent.next_decision;
    const cells = this.pathCells();
    if (cells.length === 0) return null;

    // Map next_decision.path cells (each "[r,c]") onto pathCells indices.
    // pathCells holds the active agent's full forecast trail, so the
    // first few cells of nd.path should already be in there in order.
    // We accept any monotone non-decreasing index sequence; if a cell
    // isn't found we bail (defensive: forecast/state mismatch can happen
    // during a state-update race).
    const cellKey = (rc: [number, number]) => `${rc[0]},${rc[1]}`;
    let lastIdx = -1;
    const pathIdx: number[] = [];
    for (const rc of nd.path) {
      const key = cellKey(rc);
      const idx = cells.indexOf(key, Math.max(0, lastIdx));
      if (idx < 0) return null;
      pathIdx.push(idx);
      lastIdx = idx;
    }
    const decisionIdx = cells.indexOf(cellKey(nd.decision_position), lastIdx);
    if (decisionIdx < 0) return null;

    // Build SVG path along the topology row, NOT the Marey body.
    // The overlay is rendered absolutely over cell-topology [2].
    const y = this.TOPOLOGY_PX / 2;
    const pts = pathIdx.map(i => ({ x: this.pathCoord(i), y }));
    pts.push({ x: this.pathCoord(decisionIdx), y });
    const pathD = pts.map((p, i) =>
      (i === 0 ? 'M' : 'L') + ` ${p.x} ${p.y}`
    ).join(' ');

    // Pill anchor: just below+right of the agent's tile, exactly
    // the way flatland-map positions it. The overlay sits OVER
    // cell-topology [2], so agent_y is the tile-row centre.
    const decisionCx = this.pathCoord(decisionIdx);
    const decisionCy = y;
    const agentX = pts[0].x;
    const agentY = y;
    const pillsX = agentX + 12;
    const pillsY = agentY + 8;

    // Recommended action: derive from the baseline forecast trajectory.
    // Find the first forecast step where the agent sits ON the decision
    // cell, then look at the NEXT step's direction. The change in
    // direction (mod 4) tells us LEFT / FORWARD / RIGHT.
    //   delta 0  → FORWARD (action 2)
    //   delta +1 → RIGHT   (action 3)   [E→S, S→W, W→N, N→E]
    //   delta -1 → LEFT    (action 1)
    //   no movement (same cell next step) → STOP (action 4)
    const recommendedAction = this._recommendedActionAt(handle, nd.decision_position);

    const cellKind: 'switch' | 'merge' =
      nd.cell_type === 'SWITCH' ? 'switch' : 'merge';

    const options: DecisionPill[] = nd.options.map((opt: DecisionOption) => ({
      action: opt.action,
      label: opt.label,
      isOverride: agent.override_action === opt.action,
      isRecommended: recommendedAction != null && opt.action === recommendedAction,
    }));

    return {
      handle,
      color: this.colors.getColor(handle),
      pathD,
      decisionCx,
      decisionCy,
      pillsX,
      pillsY,
      options,
      cellKind,
    };
  });

  /** Walk the active baseline forecast for `handle`; return the action
   *  the policy would play AT `decisionPos` (the next decision cell).
   *  Returns null when the forecast doesn't reach that cell or any
   *  required snapshot is missing. */
  private _recommendedActionAt(handle: number, decisionPos: [number, number]): number | null {
    const now = this.elapsed();
    const sc = this.forecastScenario();
    if (!sc?.trajectories) return null;
    const traj = (sc.trajectories[String(handle)] ?? []).filter((p) => p.step >= now);
    if (!traj || traj.length < 2) return null;

    // Find first index where (row,col) == decisionPos.
    const i = traj.findIndex(p => p.row === decisionPos[0] && p.col === decisionPos[1]);
    if (i < 0) return null;

    // Stopping detection: agent is on the decision cell for >=2 steps.
    const next = traj[i + 1];
    if (!next) return null;
    if (next.row === decisionPos[0] && next.col === decisionPos[1] && next.dir === traj[i].dir) {
      return 4; // STOP
    }

    // Direction-change → LEFT/FORWARD/RIGHT.
    const delta = ((next.dir - traj[i].dir) + 4) % 4;
    if (delta === 0) return 2; // FORWARD
    if (delta === 1) return 3; // RIGHT
    if (delta === 3) return 1; // LEFT
    return null;
  }


  mareyRenderTimesForPoint(
    p: { step: number; endStep?: number },
    now: number,
  ): number[] {
    const start = p.step;
    const end = p.endStep ?? p.step;

    const times = new Set<number>();
    times.add(start);

    if (start < now && now < end) {
      times.add(now);
    }

    if (end > start) {
      times.add(end);
    }

    return Array.from(times).sort((a, b) => a - b);
  }

  readonly agentLines = computed<AgentLine[]>(() => {
    const active = this.activeHandle();
    const idx = this.pathIndex();
    const tr = this.mergedTrajectories();
    if (active == null || idx.size === 0) return [];

    const now = this.elapsed();
    const lines: AgentLine[] = [];

    for (const [handleStr, traj] of Object.entries(tr)) {
      const handle = Number(handleStr);
      const isActive = handle === active;
      const past: { x: number; y: number }[] = [];
      const future: { x: number; y: number }[] = [];
      const dwellSegments: string[] = [];

      // For each on-path step, pick the X-index that is CLOSEST to the
      // previous step's chosen index. This makes the active agent monotone
      // (its visits are in path order) and lets other agents draw clean
      // lines that go up/down on the X-axis where they cross the path.
      let prevXIdx = isActive ? -1 : 0;
      for (const p of traj) {
        const key = `${p.row},${p.col}`;
        const candidates = idx.get(key);
        if (!candidates || candidates.length === 0) continue;
        let xIdx: number;
        if (isActive) {
          // Active agent: take the next path-index >= prev (its visits
          // are the path itself, so this is monotone).
          xIdx = candidates.find(c => c > prevXIdx) ?? candidates[candidates.length - 1];
        } else {
          // Other agents: pick the candidate closest to prev so the line
          // stays continuous through repeated cells.
          xIdx = candidates[0];
          let bestDist = Math.abs(xIdx - prevXIdx);
          for (const c of candidates) {
            const d = Math.abs(c - prevXIdx);
            if (d < bestDist) { bestDist = d; xIdx = c; }
          }
        }
        prevXIdx = xIdx;
        const dwellEnd = p.endStep ?? p.step;
        if (dwellEnd > p.step) {
          // Compressed same-cell run:
          // draw an explicit overlay at the same path index from step -> endStep.
          const t0 = p.step;
          const t1 = dwellEnd;

          if (t1 > t0) {
            const dwellPts = this.axesSwapped()
              ? [
                  { x: this.timeCoord(t0), y: this.pathCoord(xIdx) },
                  { x: this.timeCoord(t1), y: this.pathCoord(xIdx) },
                ]
              : [
                  { x: this.pathCoord(xIdx), y: this.timeCoord(t0) },
                  { x: this.pathCoord(xIdx), y: this.timeCoord(t1) },
                ];

            dwellSegments.push(this.toPathD(dwellPts));
          }
        }

        for (const t of this.mareyRenderTimesForPoint(p, now)) {
          const sx = this.axesSwapped() ? this.timeCoord(t) : this.pathCoord(xIdx);
          const sy = this.axesSwapped() ? this.pathCoord(xIdx) : this.timeCoord(t);
          const pt = { x: sx, y: sy };

          if (t <= now) {
            past.push(pt);
          }

          if (t >= now) {
            future.push(pt);
          }
        }
      }

      const pastD = past.length > 1 ? this.toPathD(past) : '';
      const futureD = future.length > 1 ? this.toPathD(future) : '';
      const dwellD = dwellSegments.join(' ');
      if (!pastD && !futureD) continue;

      lines.push({ handle, color: this.colors.getColorSolid(handle), pastD, futureD, dwellD,
        isActive });
    }
    lines.sort((a, b) => Number(a.isActive) - Number(b.isActive));
    return lines;
  });

  /** Agent labels at the START of each line, side determined by motion direction. */
  readonly agentLabels = computed<AgentLabel[]>(() => {
    const active = this.activeHandle();
    const idx = this.pathIndex();
    const tr = this.mergedTrajectories();
    if (active == null || idx.size === 0) return [];

    const out: AgentLabel[] = [];
    const OFFSET = 16;  // distance from line start to circle centre

    const now = this.elapsed();
    for (const [handleStr, traj] of Object.entries(tr)) {
      const handle = Number(handleStr);
      const isActive = handle === active;

      // Collect on-path points using the same closest-index policy.
      const pts: { x: number; y: number }[] = [];
      let prevX = isActive ? -1 : 0;
      let firstXIdx = -1;
      // Track which path-cell index corresponds to the agent's CURRENT
      // position (largest traj.step <= elapsed). Falls back to firstXIdx
      // when the agent has not started or the trajectory hasn't begun.
      let currentXIdx = -1;
      for (const p of traj) {
        const key = `${p.row},${p.col}`;
        const candidates = idx.get(key);
        if (!candidates || candidates.length === 0) continue;
        let xIdx: number;
        if (isActive) {
          xIdx = candidates.find(c => c > prevX) ?? candidates[candidates.length - 1];
        } else {
          xIdx = candidates[0];
          let bestDist = Math.abs(xIdx - prevX);
          for (const c of candidates) {
            const d = Math.abs(c - prevX);
            if (d < bestDist) { bestDist = d; xIdx = c; }
          }
        }
        prevX = xIdx;
        if (firstXIdx < 0) firstXIdx = xIdx;
        if (p.step <= now && (p.endStep ?? p.step) >= now) currentXIdx = xIdx;
        const sx = this.axesSwapped() ? this.timeCoord(p.step) : this.pathCoord(xIdx);
        const sy = this.axesSwapped() ? this.pathCoord(xIdx)   : this.timeCoord(p.step);
        pts.push({ x: sx, y: sy });
      }
      if (pts.length === 0) continue;

      const start = pts[0];
      const next = pts[1] ?? { x: start.x + 1, y: start.y };

      let cx: number, cy: number;
      if (this.axesSwapped()) {
        // Path runs vertically: motion is up or down.
        const goingDown = next.y > start.y;
        cx = start.x;
        cy = goingDown ? start.y - OFFSET : start.y + OFFSET;
      } else {
        // Path runs horizontally: motion is left or right.
        const goingRight = next.x > start.x;
        cx = goingRight ? start.x - OFFSET : start.x + OFFSET;
        cy = start.y;
      }

      const finalTileIdx = Math.max(0, currentXIdx >= 0 ? currentXIdx : firstXIdx);
      // Skip agents whose current tile is outside the visible xRange —
      // they would otherwise either disappear (no cellIdx match) or in
      // edge cases attach to a boundary tile. Explicit skip is clearer.
      const r = this.xRange();
      if (finalTileIdx < r.start || finalTileIdx > r.end) continue;

      out.push({
        handle,
        color: this.colors.getColorSolid(handle),
        tileIndex: finalTileIdx,
        x: start.x, y: start.y,
        textX: cx, textY: cy,
        textAnchor: "middle",
        lineX1: cx, lineY1: cy, lineX2: cx, lineY2: cy,
        isActive,
      });
    }
    return out;
  });

  // ── coord helpers (range-driven, single source of truth) ─────
  /** Map a tile-index to its X (or Y if axes swapped) pixel coord.
   *  Indices inside [xRange.start, xRange.end] map linearly into the
   *  chart's inner area; indices outside fall outside the area and
   *  get clipped by the SVG. Topology + chart use the same range so
   *  they stay structurally in sync. */
  pathCoord(i: number): number {
    // Map a path-cell INDEX to the pixel coord at the CELL CENTRE.
    //
    // The visible window covers cells [start..end] inclusive, i.e.
    // (end - start + 1) cells laid out edge-to-edge in flex. Cell k's
    // centre therefore sits at fraction (k - start + 0.5) / count of
    // the inner pixel range. Earlier this returned an endpoint scale
    // (0 → left edge, end-start → right edge), which made cell 0
    // render at x=0 instead of x=tileSize/2. Visible result: the
    // decision-glyph + agent-line started at the LEFT EDGE of the
    // first tile instead of going through its centre, off-by-half
    // a tile across the whole topology row.
    const r = this.xRange();
    const count = Math.max(1, r.end - r.start + 1);
    const t = (i - r.start + 0.5) / count;
    if (this.axesSwapped()) {
      const inner = this.H - this.PAD.top - this.PAD.bottom;
      return this.PAD.top + t * inner;
    }
    const inner = this.W - this.PAD.left - this.PAD.right;
    return this.PAD.left + t * inner;
  }


  private mareyTimePanDrag: {
    axisCoord: number;
    range: { start: number; end: number };
  } | null = null;

  private mareyTimeAxisCoordFromEvent(ev: MouseEvent | WheelEvent, svg: SVGSVGElement): number {
    const rect = svg.getBoundingClientRect();

    if (!rect || rect.width <= 0 || rect.height <= 0) {
      return 0;
    }

    // Convert browser pixels to SVG/viewBox coordinates.
    const svgX = ((ev.clientX - rect.left) / rect.width) * this.W;
    const svgY = ((ev.clientY - rect.top) / rect.height) * this.H;

    // Time axis is vertical normally, horizontal when axes are swapped.
    return this.axesSwapped() ? svgX : svgY;
  }

  private clampTimeRange(start: number, end: number): { start: number; end: number } {
    const fullStart = 0;
    const fullEnd = Math.max(1, this.maxSteps());
    const span = Math.max(1, end - start);

    let ns = start;
    let ne = end;

    if (ns < fullStart) {
      ns = fullStart;
      ne = ns + span;
    }

    if (ne > fullEnd) {
      ne = fullEnd;
      ns = ne - span;
    }

    ns = Math.max(fullStart, ns);
    ne = Math.min(fullEnd, ne);

    return { start: ns, end: ne };
  }

  onMareyMouseDown(ev: MouseEvent): void {
    // Left mouse button only.
    if (ev.button !== 0) return;

    const fullStart = 0;
    const fullEnd = Math.max(1, this.maxSteps());
    const r = this.yRange();
    const span = r.end - r.start;
    const fullSpan = fullEnd - fullStart;

    // Panning only makes sense when zoomed.
    if (span >= fullSpan - 1e-6) {
      this.mareyTimePanDrag = null;
      return;
    }

    const svg = ev.currentTarget as SVGSVGElement | null;
    if (!svg) return;

    ev.preventDefault();
    ev.stopPropagation();

    this.mareyTimePanDrag = {
      axisCoord: this.mareyTimeAxisCoordFromEvent(ev, svg),
      range: { start: r.start, end: r.end },
    };
  }

  onMareyMouseMove(ev: MouseEvent): void {
    const drag = this.mareyTimePanDrag;
    if (!drag) return;

    const svg = ev.currentTarget as SVGSVGElement | null;
    if (!svg) return;

    ev.preventDefault();
    ev.stopPropagation();

    const axisStart = this.axesSwapped() ? this.PAD.left : this.PAD.top;
    const axisEnd = this.axesSwapped()
      ? this.W - this.PAD.right
      : this.H - this.PAD.bottom;

    const axisSpanPx = Math.max(1, axisEnd - axisStart);
    const rangeSpan = Math.max(1, drag.range.end - drag.range.start);

    const currentAxisCoord = this.mareyTimeAxisCoordFromEvent(ev, svg);
    const deltaPx = currentAxisCoord - drag.axisCoord;
    const deltaSteps = (deltaPx / axisSpanPx) * rangeSpan;

    // Natural "grab chart" behaviour:
    // dragging down/right moves the visible content down/right,
    // therefore the time range shifts backwards.
    const next = this.clampTimeRange(
      drag.range.start - deltaSteps,
      drag.range.end - deltaSteps,
    );

    this.yRange.set(next);
  }

  onMareyMouseUp(ev?: MouseEvent): void {
    if (!this.mareyTimePanDrag) return;

    ev?.preventDefault();
    ev?.stopPropagation();

    this.mareyTimePanDrag = null;
  }


  resetZoom(): void {
    // Reset Marey view to full time horizon and default pan/zoom.
    const m = Math.max(1, this.maxSteps());

    this.yRange.set({ start: 0, end: m });

    this.zoomX.set(1);
    this.zoomY.set(1);
    this.panX.set(0);
    this.panY.set(0);

    this.mareyTimePanDrag = null;
  }

  onMareyWheel(ev: WheelEvent): void {
    // Wheel zooms the TIME axis only.
    // The time value under the cursor remains stable after zoom.
    ev.preventDefault();
    ev.stopPropagation();

    const svg = ev.currentTarget as SVGSVGElement | null;
    const rect = svg?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;

    // Convert browser pixels to SVG/viewBox coordinates.
    // This is important when the SVG is rendered scaled.
    const svgX = ((ev.clientX - rect.left) / rect.width) * this.W;
    const svgY = ((ev.clientY - rect.top) / rect.height) * this.H;

    // Time axis is vertical normally, horizontal when axes are swapped.
    const axisCoord = this.axesSwapped() ? svgX : svgY;

    const axisStart = this.axesSwapped() ? this.PAD.left : this.PAD.top;
    const axisEnd = this.axesSwapped()
      ? this.W - this.PAD.right
      : this.H - this.PAD.bottom;

    const axisSpanPx = Math.max(1, axisEnd - axisStart);

    // Cursor ratio on the time axis.
    // Clamp so wheel slightly outside the plot still behaves predictably.
    const ratio = Math.max(0, Math.min(1, (axisCoord - axisStart) / axisSpanPx));

    const fullStart = 0;
    const fullEnd = Math.max(1, this.maxSteps());

    const current = this.yRange();
    const currentStart = Math.max(fullStart, Math.min(current.start, fullEnd));
    const currentEnd = Math.max(currentStart + 1, Math.min(current.end, fullEnd));
    const currentSpan = Math.max(1, currentEnd - currentStart);

    // This is the time currently under the cursor.
    const focusedTime = currentStart + ratio * currentSpan;

    // deltaY < 0 means wheel up -> zoom in.
    const zoomFactor = ev.deltaY < 0 ? 0.82 : 1.22;

    const minSpan = Math.min(4, fullEnd - fullStart);
    const maxSpan = Math.max(minSpan, fullEnd - fullStart);

    let newSpan = currentSpan * zoomFactor;
    newSpan = Math.max(minSpan, Math.min(maxSpan, newSpan));

    // Keep focusedTime at the same cursor ratio:
    // focusedTime = newStart + ratio * newSpan
    let newStart = focusedTime - ratio * newSpan;
    let newEnd = newStart + newSpan;

    // Clamp to full time horizon while keeping span.
    if (newStart < fullStart) {
      newStart = fullStart;
      newEnd = newStart + newSpan;
    }

    if (newEnd > fullEnd) {
      newEnd = fullEnd;
      newStart = newEnd - newSpan;
    }

    newStart = Math.max(fullStart, newStart);
    newEnd = Math.min(fullEnd, newEnd);

    // If effectively zoomed fully out, snap exactly to full range.
    if (newStart <= fullStart + 1e-6 && newEnd >= fullEnd - 1e-6) {
      this.yRange.set({ start: fullStart, end: fullEnd });
      return;
    }

    this.yRange.set({ start: newStart, end: newEnd });
  }

  /** Map a step to its Y (or X if axes swapped) pixel coord, using yRange. */
  timeCoord(step: number): number {
    const r = this.yRange();
    const span = Math.max(1, r.end - r.start);
    const t = (step - r.start) / span;
    if (this.axesSwapped()) {
      const inner = this.W - this.PAD.left - this.PAD.right;
      return this.PAD.left + t * inner;
    }
    const inner = this.H - this.PAD.top - this.PAD.bottom;
    return this.PAD.top + t * inner;
  }
  toPathD(pts: { x: number; y: number }[]): string {
    return pts.map((p, i) =>
      `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`
    ).join(' ');
  }

  readonly timeTicks = computed(() => {
    const m = this.maxSteps();
    const step = m <= 200 ? 50 : m <= 500 ? 100 : 200;
    const out: { v: number; coord: number }[] = [];
    for (let v = 0; v <= m; v += step) out.push({ v, coord: this.timeCoord(v) });
    return out;
  });
  readonly nowCoord = computed(() => this.timeCoord(this.elapsed()));

  // ── pan via drag ─────────────────────────────────────────────
  onMouseDown(ev: MouseEvent): void {
    if (ev.button !== 0) return;
    this.isDragging = true;
    this.dragStartX = ev.clientX;
    this.dragStartY = ev.clientY;
    this.dragStartPanX = this.panX();
    this.dragStartPanY = this.panY();
    if (this.svgEl) this.svgEl.style.cursor = 'grabbing';
    ev.preventDefault();
  }
  onMouseMove(ev: MouseEvent): void {
    if (!this.isDragging || !this.svgEl) return;
    const rect = this.svgEl.getBoundingClientRect();
    const dx = ev.clientX - this.dragStartX;
    const dy = ev.clientY - this.dragStartY;
    const sx = (this.W / this.zoomX()) / rect.width;
    const sy = (this.H / this.zoomY()) / rect.height;
    this.panX.set(this.clampPanX(this.dragStartPanX - dx * sx));
    this.panY.set(this.clampPanY(this.dragStartPanY - dy * sy));
  }
  onMouseUp(): void {
    if (this.isDragging) {
      this.isDragging = false;
      if (this.svgEl) this.svgEl.style.cursor = 'grab';
    }
  }
  onMouseLeave(): void { this.onMouseUp(); }

  // ── pan via buttons (30% of viewport) ────────────────────────
  panStep(dirX: number, dirY: number): void {
    const stepX = (this.W / this.zoomX()) * 0.3;
    const stepY = (this.H / this.zoomY()) * 0.3;
    this.panX.update(v => this.clampPanX(v + dirX * stepX));
    this.panY.update(v => this.clampPanY(v + dirY * stepY));
  }

  // ── clamping helpers ─────────────────────────────────────────
  /** Min zoom = 1 (full content visible). Max = 10 for sanity. */
  private clampZ(v: number): number {
    return Math.max(1, Math.min(10, v));
  }
  /** Pan-X is clamped so the viewBox X range [pan, pan + W/zoom]
   *  stays inside [0, W]. With zoom=1 this forces pan=0. */
  private clampPanX(v: number): number {
    const span = this.W / this.zoomX();
    const max = Math.max(0, this.W - span);
    return Math.max(0, Math.min(max, v));
  }
  private clampPanY(v: number): number {
    const span = this.H / this.zoomY();
    const max = Math.max(0, this.H - span);
    return Math.max(0, Math.min(max, v));
  }

  // ── zoom ─────────────────────────────────────────────────────
  resetPan(): void {
    // Legacy zoom/pan signals — kept for now while old code paths
    // (panStep, zoomIn/Out) still reference them, even though the
    // actual rendering is driven by xRange/yRange.
    this.panX.set(this.clampPanX(0)); this.panY.set(this.clampPanY(0));
    this.zoomX.set(this.clampZ(1)); this.zoomY.set(this.clampZ(1));
    // Range brushes — full extent.
    const n = this.pathCells().length;
    this.xRange.set({ start: 0, end: Math.max(0, n - 1) });
    this.yRange.set({ start: 0, end: this.maxSteps() });
  }
  zoomIn():  void { this._zoomBy(1.2, 1.2, 0.5, 0.5); }
  zoomOut(): void { this._zoomBy(1/1.2, 1/1.2, 0.5, 0.5); }
  swapAxes(): void { this.axesSwapped.update(v => !v); this.resetPan(); }

  onWheel(ev: WheelEvent): void {
    ev.preventDefault();
    if (!this.svgEl) return;
    const rect = this.svgEl.getBoundingClientRect();
    const cxRel = (ev.clientX - rect.left) / rect.width;
    const cyRel = (ev.clientY - rect.top) / rect.height;
    const factor = ev.deltaY < 0 ? 1.1 : 1/1.1;
    let fx = factor, fy = factor;
    if (ev.shiftKey) fy = 1;
    if (ev.ctrlKey)  fx = 1;
    this._zoomBy(fx, fy, cxRel, cyRel);
  }

  private _zoomBy(fx: number, fy: number, cxRel: number, cyRel: number): void {
    const oldZx = this.zoomX();
    const oldZy = this.zoomY();
    const newZx = Math.min(20, Math.max(1, oldZx * fx));
    const newZy = Math.min(20, Math.max(1, oldZy * fy));
    if (newZx === oldZx && newZy === oldZy) return;
    const ax = this.panX() + cxRel * (this.W / oldZx);
    const ay = this.panY() + cyRel * (this.H / oldZy);
    this.zoomX.set(this.clampZ(newZx));
    this.zoomY.set(this.clampZ(newZy));
    this.panX.set(this.clampPanX(ax - cxRel * (this.W / newZx)));
    this.panY.set(this.clampPanY(ay - cyRel * (this.H / newZy)));
  }

  // ── agent selection (mirrors flatland-map) ───────────────────

  isSelected(handle: number): boolean {
    // Explicit click only. Default/context agent must not look selected.
    return this.store.selectedHandle() === handle;
  }
  onAgentClick(handle: number, ev: MouseEvent): void {
    ev.stopPropagation();
    // Always select (no toggle) — clicking another agent's marker
    // should switch the Marey to that agent's path, never deselect.
    this.store.selectedHandle.set(handle);
  }

  setForecastScenario(id: string | null): void {
    this.forecastScenarioId.set(id);
  }
}
