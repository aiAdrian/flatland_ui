import {
  Component, CUSTOM_ELEMENTS_SCHEMA, computed, effect, inject, signal,
  ElementRef, viewChild, AfterViewInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
import { RailTile } from '../../core/models';
import { AgentColorService } from '../../core/agent-color.service';

interface AgentLine {
  handle: number;
  color: string;
  pastD: string;
  futureD: string;
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
  private readonly colors = inject(AgentColorService);
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
  readonly PAD = { top: 16, right: 24, bottom: 36, left: 56 };

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
  readonly TOPOLOGY_PX = 48;

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
    const tx = -(r.start / n) * 100;
    return `scaleX(${sx}) translateX(${tx}%)`;
  });

  /** Swap axes: false = time vertical (default), true = time horizontal. */
  readonly axesSwapped = signal(false);

  readonly viewBox = computed(() => {
    const w = this.W / this.zoomX();
    const h = this.H / this.zoomY();
    return `${this.panX()} ${this.panY()} ${w} ${h}`;
  });

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

  readonly pathCells = computed<string[]>(() => {
    const sc = this.forecastScenario();
    const handle = this.activeHandle();
    if (!sc || handle == null || !sc.trajectories) return [];
    const traj = sc.trajectories[String(handle)] ?? [];
    // Cells in the order the active agent visits them, deduping only
    // back-to-back identical entries (multi-step dwells) but KEEPING
    // repeat visits that come from loops — those become separate
    // X-axis positions so the active agent's line stays monotone.
    const out: string[] = [];
    let lastKey = "";
    for (const p of traj) {
      const key = `${p.row},${p.col}`;
      if (key === lastKey) continue;
      lastKey = key;
      out.push(key);
    }
    return out;
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

  /** Marey-Topologie (begradigt): jede Pfad-Cell wird auf das passende
   *  horizontale Asset gemappt — Gerade / Weiche-Variante / Merging — basierend
   *  auf dem Original-Tile (Map) und der Action des aktiven Zugs (F/L/R), die
   *  aus den `dir`-Werten benachbarter Trajectory-Punkte abgeleitet wird. */
  readonly pathTiles = computed<({ svg: string; rot: number; xCoord: number; yCoord: number } | null)[]>(() => {
    const sc = this.forecastScenario();
    const handle = this.activeHandle();
    const cells = this.pathCells();
    if (!sc || handle == null || cells.length === 0 || !sc.trajectories) return [];

    const traj = sc.trajectories[String(handle)] ?? [];
    if (traj.length === 0) return [];

    // Cell-key → first index of that cell in the trajectory.
    const trajIdxByKey = new Map<string, number>();
    traj.forEach((t, i) => {
      const k = `${t.row},${t.col}`;
      if (!trajIdxByKey.has(k)) trajIdxByKey.set(k, i);
    });

    // Cell-key → original RailTile from the map.
    const tilesByKey = new Map<string, RailTile>();
    for (const t of this.store.railTiles()) tilesByKey.set(`${t.r},${t.c}`, t);

    const out: ({ svg: string; rot: number; xCoord: number; yCoord: number } | null)[] = [];

    for (let i = 0; i < cells.length; i++) {
      const key = cells[i];
      const tile = tilesByKey.get(key);
      const tIdx = trajIdxByKey.get(key);

      let svg = "Gleis_horizontal.svg";
      const rot = 0; // begradigt: alles horizontal

      if (tile && tIdx !== undefined) {
        const cur = traj[tIdx];
        const next = tIdx < traj.length - 1 ? traj[tIdx + 1] : null;
        const curDir = cur.dir;
        const nextDir = next ? next.dir : curDir;

        // Action F / L / R based on direction change at this cell.
        let action: "F" | "L" | "R" = "F";
        if (nextDir === (curDir + 3) % 4) action = "L";
        else if (nextDir === (curDir + 1) % 4) action = "R";

        const t = tile.svg;
        if (t === "Weiche_horizontal_oben_links.svg") {
          // L/F switch: Forward → keep oben_links (Stummel oben);
          //             Left   → unten_links (curve up).
          svg = action === "L" ? "Weiche_horizontal_unten_links.svg" : "Weiche_horizontal_oben_links.svg";
        } else if (t === "Weiche_horizontal_unten_links.svg") {
          // R/F switch: Forward → keep unten_links (Stummel unten);
          //             Right   → oben_links (curve down).
          svg = action === "R" ? "Weiche_horizontal_oben_links.svg" : "Weiche_horizontal_unten_links.svg";
        } else if (t === "Weiche_horizontal_oben_rechts.svg") {
          svg = "Weiche_horizontal_oben_rechts.svg";
        } else if (t === "Weiche_horizontal_unten_rechts.svg") {
          svg = "Weiche_horizontal_unten_rechts.svg";
        } else if (t === "Weiche_Double_Slip.svg" || t === "Weiche_Single_Slip.svg") {
          svg = t;
        } else {
          // Gerade or Kurve → flatten to straight horizontal.
          svg = "Gleis_horizontal.svg";
        }
      }

      const xCoord = this.axesSwapped() ? this.PAD.left + 18 : this.pathCoord(i);
      const yCoord = this.axesSwapped() ? this.pathCoord(i) : this.TOPOLOGY_PX / 2;
      out.push({ svg, rot, xCoord, yCoord });
    }
    return out;
  });

  readonly agentLines = computed<AgentLine[]>(() => {
    const sc = this.forecastScenario();
    const active = this.activeHandle();
    const idx = this.pathIndex();
    if (!sc || active == null || idx.size === 0 || !sc.trajectories) return [];

    const now = this.elapsed();
    const lines: AgentLine[] = [];

    for (const [handleStr, traj] of Object.entries(sc.trajectories)) {
      const handle = Number(handleStr);
      const isActive = handle === active;
      const past: { x: number; y: number }[] = [];
      const future: { x: number; y: number }[] = [];

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
        const sx = this.axesSwapped() ? this.timeCoord(p.step) : this.pathCoord(xIdx);
        const sy = this.axesSwapped() ? this.pathCoord(xIdx)   : this.timeCoord(p.step);
        (p.step <= now ? past : future).push({ x: sx, y: sy });
      }

      const pastD = past.length > 1 ? this.toPathD(past) : '';
      const futureD = future.length > 1 ? this.toPathD(future) : '';
      if (!pastD && !futureD) continue;

      lines.push({ handle, color: this.colors.getColorSolid(handle), pastD, futureD, isActive });
    }
    lines.sort((a, b) => Number(a.isActive) - Number(b.isActive));
    return lines;
  });

  /** Agent labels at the START of each line, side determined by motion direction. */
  readonly agentLabels = computed<AgentLabel[]>(() => {
    const sc = this.forecastScenario();
    const active = this.activeHandle();
    const idx = this.pathIndex();
    if (!sc || active == null || idx.size === 0 || !sc.trajectories) return [];

    const out: AgentLabel[] = [];
    const OFFSET = 16;  // distance from line start to circle centre

    for (const [handleStr, traj] of Object.entries(sc.trajectories)) {
      const handle = Number(handleStr);
      const isActive = handle === active;

      // Collect on-path points using the same closest-index policy.
      const pts: { x: number; y: number }[] = [];
      let prevX = isActive ? -1 : 0;
      let firstXIdx = -1;
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

      out.push({
        handle,
        color: this.colors.getColorSolid(handle),
        tileIndex: Math.max(0, firstXIdx),
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
    const r = this.xRange();
    const span = Math.max(1, r.end - r.start);
    const t = (i - r.start) / span;
    if (this.axesSwapped()) {
      const inner = this.H - this.PAD.top - this.PAD.bottom;
      return this.PAD.top + t * inner;
    }
    const inner = this.W - this.PAD.left - this.PAD.right;
    return this.PAD.left + t * inner;
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
    this.panX.set(this.clampPanX(0)); this.panY.set(this.clampPanY(0));
    this.zoomX.set(this.clampZ(1)); this.zoomY.set(this.clampZ(1));
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
