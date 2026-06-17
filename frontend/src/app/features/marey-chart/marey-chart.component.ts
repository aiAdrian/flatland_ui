import {
  Component, CUSTOM_ELEMENTS_SCHEMA, computed, effect, inject, signal,
  ElementRef, viewChild, AfterViewInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
import { RailTile, NextDecision, DecisionOption, AgentDTO } from '../../core/models';
import { AgentColorService } from '../../core/agent-color.service';

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

  readonly mergedTrajectories = computed<Record<string, Array<{ step: number; endStep?: number; durationSteps?: number; dwellSteps?: number; row: number; col: number; dir: number; state?: string }>>>(() => {
    const sc = this.forecastScenario();
    const now = this.elapsed();
    if (!sc) return {};

    const forecast = sc.trajectories ?? {};
    const history = this.store.trajectories();
    const handles = new Set<string>([
      ...Object.keys(forecast),
      ...Array.from(history.keys()).map((h) => String(h)),
    ]);

    const out: Record<string, Array<{ step: number; endStep?: number; durationSteps?: number; dwellSteps?: number; row: number; col: number; dir: number; state?: string }>> = {};
    for (const handleStr of handles) {
      const h = Number(handleStr);
      const hist = (history.get(h) ?? [])
        .filter((p) => p.position != null && p.step <= now)
        .map((p) => ({
          step: p.step,
          endStep: p.endStep ?? p.step,
          durationSteps: p.durationSteps ?? p.dwellSteps ?? Math.max(1, (p.endStep ?? p.step) - p.step + 1),
          dwellSteps: p.dwellSteps ?? p.durationSteps ?? Math.max(1, (p.endStep ?? p.step) - p.step + 1),
          row: p.position![0],
          col: p.position![1],
          dir: p.direction ?? 0,
          state: p.state,
        }));

      const fut = (forecast[handleStr] ?? [])
        .filter((p) => p.step > now)
        .map((p) => ({
          step: p.step,
          endStep: p.step,
          durationSteps: 1,
          dwellSteps: 1,
          row: p.row,
          col: p.col,
          dir: p.dir,
        }));

      out[handleStr] = this.compressMareyTrajectoryRuns([...hist, ...fut]);
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

  /** Marey-Topologie (begradigt): jede Pfad-Cell wird auf das passende
   *  horizontale Asset gemappt — Gerade / Weiche-Variante / Merging — basierend
   *  auf dem Original-Tile (Map) und der Action des aktiven Zugs (F/L/R), die
   *  aus den `dir`-Werten benachbarter Trajectory-Punkte abgeleitet wird. */
  readonly pathTiles = computed<({ svg: string; rot: number; xCoord: number; yCoord: number } | null)[]>(() => {
    const handle = this.activeHandle();
    const cells = this.pathCells();
    const tr = this.mergedTrajectories();
    if (handle == null || cells.length === 0) return [];

    const traj = tr[String(handle)] ?? [];
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
