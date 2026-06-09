import {
  Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal,
  ElementRef, viewChild, AfterViewInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
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

  readonly W = 1200;
  readonly H = 700;
  readonly PAD = { top: 32, right: 24, bottom: 36, left: 56 };

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
    const id = this.forecastScenarioId();
    const all = this.scenarios();
    if (!all || all.length === 0) return null;
    if (id) {
      const found = all.find(s => s.id === id);
      if (found) return found;
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
        x: start.x, y: start.y,
        textX: cx, textY: cy,
        textAnchor: "middle",
        lineX1: cx, lineY1: cy, lineX2: cx, lineY2: cy,
        isActive,
      });
    }
    return out;
  });

  // ── coord helpers ────────────────────────────────────────────
  pathCoord(i: number): number {
    const cells = this.pathCells().length || 1;
    if (this.axesSwapped()) {
      const inner = this.H - this.PAD.top - this.PAD.bottom;
      return this.PAD.top + (i / Math.max(1, cells - 1)) * inner;
    }
    const inner = this.W - this.PAD.left - this.PAD.right;
    return this.PAD.left + (i / Math.max(1, cells - 1)) * inner;
  }
  timeCoord(step: number): number {
    const m = this.maxSteps();
    if (this.axesSwapped()) {
      const inner = this.W - this.PAD.left - this.PAD.right;
      return this.PAD.left + (step / m) * inner;
    }
    const inner = this.H - this.PAD.top - this.PAD.bottom;
    return this.PAD.top + (step / m) * inner;
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
    this.panX.set(this.dragStartPanX - dx * sx);
    this.panY.set(this.dragStartPanY - dy * sy);
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
    this.panX.update(v => v + dirX * stepX);
    this.panY.update(v => v + dirY * stepY);
  }

  // ── zoom ─────────────────────────────────────────────────────
  resetPan(): void {
    this.panX.set(0); this.panY.set(0);
    this.zoomX.set(1); this.zoomY.set(1);
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
    this.zoomX.set(newZx);
    this.zoomY.set(newZy);
    this.panX.set(ax - cxRel * (this.W / newZx));
    this.panY.set(ay - cyRel * (this.H / newZy));
  }

  // ── agent selection (mirrors flatland-map) ───────────────────
  isSelected(handle: number): boolean {
    return this.store.selectedHandle() === handle;
  }
  onAgentClick(handle: number, ev: MouseEvent): void {
    ev.stopPropagation();
    this.store.toggleAgentSelection(handle);
  }

  setForecastScenario(id: string | null): void {
    this.forecastScenarioId.set(id);
  }
}
