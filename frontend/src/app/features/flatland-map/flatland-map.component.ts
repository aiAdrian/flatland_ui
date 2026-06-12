import { Component, CUSTOM_ELEMENTS_SCHEMA, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { AgentColorService } from '../../core/agent-color.service';
import { AgentDTO, DecisionCell, RailTile, DecisionOption, NextDecision } from '../../core/models';


interface DirectionalMarker {
  id: string;
  kind: 'signal' | 'switch';
  x: number;
  y: number;
  rotation: number;
  d: number;
  // Cell centre (start point of the spoke from centre to this marker)
  cx: number;
  cy: number;
}

interface DecisionLayer {
  handle: number;
  color: string;
  // 'switch' or 'merge' from agent.next_decision.cell_type,
  // used to render the right destination symbol on the map.
  cellKind: 'switch' | 'merge';
  pathD: string;
  decisionCx: number;
  decisionCy: number;
  pillsX: number;
  pillsY: number;
  options: PillData[];
}

interface PillData {
  action: number;
  label: string;
  isOverride: boolean;
}

interface BoundingBox {
  minR: number;
  maxR: number;
  minC: number;
  maxC: number;
}

interface TrajectoryOverlayCell {
  id: string;
  x: number;
  y: number;
  href: string;
  transform: string;
  color: string;
  opacity: number;
}

@Component({
  selector: 'app-flatland-map',
  standalone: true,
  templateUrl: './flatland-map.component.html',
  styleUrl: './flatland-map.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class FlatlandMapComponent {
  store = inject(SessionStore);
  private agentColors = inject(AgentColorService);

  newWidth = signal(50);
  newHeight = signal(20);
  newAgents = signal(3);

  // Rail tiles transparency (0..1). User-controllable so the operator
  // can dim or strengthen the track layout against agent overlays.
  railOpacity = signal(0.25);

  // Zoom factor. 1 = neutral; <1 zooms in, >1 zooms out (because we
  // scale the viewBox dimensions, not the SVG element).
  zoom = signal(1);

  // Display helpers (avoid the | number pipe so we do not need CommonModule).
  zoomPercent = computed(() => Math.round((1 / this.zoom()) * 100));
  opacityPercent = computed(() => Math.round(this.railOpacity() * 100));

  onNewSession() {
    this.store.newSession({
      width: this.newWidth(),
      height: this.newHeight(),
      agents: this.newAgents(),
    });
  }

  cellSize = 32;
  padCells = 1;

  // Pan-State (offset relativ zur initial bbox)
  panX = signal(0);
  panY = signal(0);

  // Drag-State (intern)
  private isDragging = false;
  private dragStartX = 0;
  private dragStartY = 0;
  private dragStartPanX = 0;
  private dragStartPanY = 0;
  private svgRef = viewChild<ElementRef<SVGSVGElement>>('svgRoot');

  private get svgEl(): SVGSVGElement | undefined {
    return this.svgRef()?.nativeElement;
  }

  constructor() {
    effect(() => {
      this.store.panResetTrigger();
      this.panX.set(0);
      this.panY.set(0);
    });
  }

  readonly bbox = computed<BoundingBox>(() => {
    const tiles = this.store.railTiles();
    const agents = this.agents();

    let minR = Infinity, maxR = -Infinity;
    let minC = Infinity, maxC = -Infinity;

    for (const t of tiles) {
      if (t.r < minR) minR = t.r;
      if (t.r > maxR) maxR = t.r;
      if (t.c < minC) minC = t.c;
      if (t.c > maxC) maxC = t.c;
    }

    for (const a of agents) {
      const pos = a.position ?? a.initial_position;
      if (pos) {
        if (pos[0] < minR) minR = pos[0];
        if (pos[0] > maxR) maxR = pos[0];
        if (pos[1] < minC) minC = pos[1];
        if (pos[1] > maxC) maxC = pos[1];
      }
      if (a.target) {
        if (a.target[0] < minR) minR = a.target[0];
        if (a.target[0] > maxR) maxR = a.target[0];
        if (a.target[1] < minC) minC = a.target[1];
        if (a.target[1] > maxC) maxC = a.target[1];
      }
    }

    if (!isFinite(minR)) {
      return { minR: 0, maxR: this.store.height() - 1, minC: 0, maxC: this.store.width() - 1 };
    }

    const pad = this.padCells;
    return {
      minR: Math.max(0, minR - pad),
      maxR: Math.min(this.store.height() - 1, maxR + pad),
      minC: Math.max(0, minC - pad),
      maxC: Math.min(this.store.width() - 1, maxC + pad),
    };
  });

  readonly viewBox = computed(() => {
    const b = this.bbox();
    const x = b.minC * this.cellSize + this.panX();
    const y = b.minR * this.cellSize + this.panY();
    const w = (b.maxC - b.minC + 1) * this.cellSize * this.zoom();
    const h = (b.maxR - b.minR + 1) * this.cellSize * this.zoom();
    return `${x} ${y} ${w} ${h}`;
  });

  readonly tiles = computed(() => this.store.railTiles());

  readonly selectedTrajectoryCells = computed<TrajectoryOverlayCell[]>(() => {
    if (!this.store.layerVisibility().agentTrajectory) return [];

    const handle = this.store.selectedHandle();
    if (handle == null) return [];

    const now = this.store.elapsedSteps();
    const history = this.store.trajectories().get(handle) ?? [];
    const scenarios = this.store.scenarios();
    const previewId = this.store.previewScenarioId();
    const forecastScenario = previewId
      ? scenarios.find((s) => s.id === previewId)
      : null;
    const activeScenario = forecastScenario ?? scenarios.find((s) => s.isBaseline) ?? scenarios[0] ?? null;
    const forecast = activeScenario?.trajectories?.[String(handle)] ?? [];

    const byCell = new Map<string, { row: number; col: number; isPast: boolean }>();

    // Past: build by step first (one snapshot per elapsed step), then
    // interpolate gaps between sampled points so visited cells are not missing.
    const pastByStep = new Map<number, { step: number; row: number; col: number }>();
    for (const p of history) {
      if (p.position == null || p.step > now) continue;
      pastByStep.set(p.step, {
        step: p.step,
        row: Number(p.position[0]),
        col: Number(p.position[1]),
      });
    }
    // Optional gap-fill source: some scenarios include full absolute steps,
    // including <= now. Use only where local history has no sample.
    for (const p of forecast) {
      if (p.step > now || pastByStep.has(p.step)) continue;
      pastByStep.set(p.step, { step: p.step, row: p.row, col: p.col });
    }

    const orderedPast = Array.from(pastByStep.values()).sort((a, b) => a.step - b.step);
    let prev: { row: number; col: number } | null = null;
    for (const pt of orderedPast) {
      this._markPastCell(byCell, pt.row, pt.col);
      if (prev) {
        this._interpolatePastCells(byCell, prev.row, prev.col, pt.row, pt.col);
      }
      prev = { row: pt.row, col: pt.col };
    }

    for (const p of forecast) {
      if (p.step <= now) continue;
      const key = `${p.row}_${p.col}`;
      if (byCell.has(key)) continue;
      byCell.set(key, { row: p.row, col: p.col, isPast: false });
    }

    const tilesByKey = new Map(this.tiles().map((t) => [`${t.r}_${t.c}`, t] as const));
    const color = this.agentColors.getColorSolid(handle);
    return Array.from(byCell.values())
      .map((cell) => {
        const tile = tilesByKey.get(`${cell.row}_${cell.col}`);
        if (!tile) return null;
        return {
          id: `traj_${handle}_${cell.row}_${cell.col}`,
          x: cell.col * this.cellSize,
          y: cell.row * this.cellSize,
          href: this.tileHref(tile),
          transform: this.tileTransform(tile),
          color,
          // Same visual separation as Marey: darker past, lighter forecast.
          opacity: cell.isPast ? 0.55 : 0.25,
        };
      })
      .filter((cell): cell is TrajectoryOverlayCell => cell != null);
  });

  private _markPastCell(
    map: Map<string, { row: number; col: number; isPast: boolean }>,
    row: number,
    col: number,
  ): void {
    const key = `${row}_${col}`;
    const cur = map.get(key);
    if (cur) {
      if (!cur.isPast) map.set(key, { ...cur, isPast: true });
      return;
    }
    map.set(key, { row, col, isPast: true });
  }

  private _interpolatePastCells(
    map: Map<string, { row: number; col: number; isPast: boolean }>,
    fromRow: number,
    fromCol: number,
    toRow: number,
    toCol: number,
  ): void {
    const dr = toRow - fromRow;
    const dc = toCol - fromCol;
    if (dr === 0 && dc === 0) return;

    const stepR = Math.sign(dr);
    const stepC = Math.sign(dc);

    // Standard case: movement samples are axis-aligned in grid space.
    if (dr === 0 || dc === 0) {
      let r = fromRow;
      let c = fromCol;
      while (r !== toRow || c !== toCol) {
        if (r !== toRow) r += stepR;
        if (c !== toCol) c += stepC;
        this._markPastCell(map, r, c);
      }
      return;
    }

    // Fallback for sparse samples around turns: fill an L-shape.
    let r = fromRow;
    let c = fromCol;
    while (r !== toRow) {
      r += stepR;
      this._markPastCell(map, r, c);
    }
    while (c !== toCol) {
      c += stepC;
      this._markPastCell(map, r, c);
    }
  }
  /** Active agents only: hide WAITING (not yet departed) and DONE
   *  (already arrived). The sidebar still shows the full roster. */
  readonly agents = computed(() =>
    this.store.agents().filter((a) => a.is_visible !== false),
  );

  readonly mergeCells = computed<DecisionCell[]>(() => {
    const state = this.store.state();
    const all = (state?.decision_cells ?? []) as DecisionCell[];
    return all.filter((c) => c.kind === 'merge');
  });
  /**
   * Markers for old "merge" cells - rendered as the Signals layer.
   * Each cell yields one marker per incoming rail direction, placed
   * at the OUTGOING edge of the cell along the rail axis (where a
   * physical signal would stand), rotated to face the direction of
   * travel.
   *
   * Direction encoding (matches Flatland): 0=N, 1=E, 2=S, 3=W
   * That is also the angle in 90deg steps for a glyph that natively
   * points NORTH (i.e. up) - we therefore rotate by direction*90.
   */
  readonly signalMarkers = computed<DirectionalMarker[]>(() => {
    const cells = (this.store.state()?.decision_cells ?? []) as DecisionCell[];
    return cells
      .filter((c) => c.kind === 'merge')
      .flatMap((c) => this._buildDirectionalMarkers(c, 'signal'));
  });


  /** Switches/signals symbols at the destination of every visible
   * Next-Decisions layer. Rendered ALWAYS when decisionLayers shows
   * the line, even if the All-Switches / All-Signals layer toggles
   * are off - so the operator can still see "what kind of decision
   * point is the train heading to". */
  readonly decisionDestSwitchInflows = computed(() => {
    return this._destSwitchCells().flatMap((c) => this._buildSwitchInflows(c));
  });

  readonly decisionDestSwitchExits = computed(() => {
    return this._destSwitchCells().flatMap((c) => {
      const exits = c.switch_exits ?? [];
      if (exits.length === 0) return [];
      return this._buildDirectionalMarkers({ ...c, directions: exits }, 'switch');
    });
  });

  readonly decisionDestSignals = computed(() => {
    return this._destSignalCells().flatMap((c) => this._buildDirectionalMarkers(c, 'signal'));
  });

  private _destSwitchCells(): DecisionCell[] {
    const cells = (this.store.state()?.decision_cells ?? []) as DecisionCell[];
    const byPos = new Map(cells.map((c) => [`${c.r}_${c.c}`, c]));
    // Dedup: when N agents target the SAME decision cell, we still only
    // render its switch markings once. Without this guard, _buildSwitchInflows
    // would emit identical IDs N times → NG0955 'duplicated keys' warnings
    // in @for tracking. Functionally identical: same cell, same arrows.
    const out: DecisionCell[] = [];
    const seen = new Set<string>();
    for (const layer of this.decisionLayers()) {
      if (layer.cellKind !== 'switch') continue;
      const key = this._destKeyForLayer(layer);
      if (seen.has(key)) continue;
      seen.add(key);
      const cell = byPos.get(key);
      if (cell) out.push(cell);
    }
    return out;
  }

  private _destSignalCells(): DecisionCell[] {
    const cells = (this.store.state()?.decision_cells ?? []) as DecisionCell[];
    const byPos = new Map(cells.map((c) => [`${c.r}_${c.c}`, c]));
    // Same dedup rationale as _destSwitchCells: multiple agents may share
    // a destination merge cell. We render its signal markings only once.
    const out: DecisionCell[] = [];
    const seen = new Set<string>();
    for (const layer of this.decisionLayers()) {
      if (layer.cellKind !== 'merge') continue;
      const key = this._destKeyForLayer(layer);
      if (seen.has(key)) continue;
      seen.add(key);
      const cell = byPos.get(key);
      if (cell) out.push(cell);
    }
    return out;
  }

  private _destKeyForLayer(layer: DecisionLayer): string {
    // decisionCx/Cy are pixel centres; reverse to grid r,c.
    const cs = this.cellSize;
    const r = Math.floor(layer.decisionCy / cs);
    const c = Math.floor(layer.decisionCx / cs);
    return `${r}_${c}`;
  }

  /** Inflow lines for a single switch cell, factored out so we can
   * reuse it both in switchInflows() and decisionDestSwitchInflows(). */
  private _buildSwitchInflows(cell: DecisionCell): {
    id: string; x1: number; y1: number; x2: number; y2: number;
  }[] {
    const cs = this.cellSize;
    const cx = cell.c * cs + cs / 2;
    const cy = cell.r * cs + cs / 2;
    const reach = cs * 0.33;
    const out: { id: string; x1: number; y1: number; x2: number; y2: number }[] = [];
    for (const d of cell.directions ?? []) {
      const sx = d === 1 ? cx - reach : d === 3 ? cx + reach : cx;
      const sy = d === 0 ? cy + reach : d === 2 ? cy - reach : cy;
      out.push({
        id: `inflow_${cell.r}_${cell.c}_${d}`,
        x1: sx, y1: sy, x2: cx, y2: cy,
      });
    }
    return out;
  }

  /** Animated inflow line per switch entry direction.
   * Each switch may classify under one or more headings (directions[]).
   * For each heading we draw an animated ">>>>>" line that comes from
   * 25% beyond the cell edge (i.e. into the neighbour cell) and runs
   * to the cell centre - showing how a train would enter that switch. */
  readonly switchInflows = computed<{
    id: string; x1: number; y1: number; x2: number; y2: number;
  }[]>(() => {
    const cells = (this.store.state()?.decision_cells ?? []) as DecisionCell[];
    return cells
      .filter((c) => c.kind === 'switch')
      .flatMap((c) => this._buildSwitchInflows(c));
  });

  /** Centre marker per switch-cell (one diamond in the middle).
   * Renders for every switch and signals "this cell is a switch" at a glance. */
  readonly switchCentres = computed<{ id: string; x: number; y: number }[]>(() => {
    const cells = (this.store.state()?.decision_cells ?? []) as DecisionCell[];
    const cs = this.cellSize;
    return cells
      .filter((c) => c.kind === 'switch')
      .map((c) => ({
        id: `switch_centre_${c.r}_${c.c}`,
        x: c.c * cs + cs / 2,
        y: c.r * cs + cs / 2,
      }));
  });

  /** Exit arrows per switch-cell - one outward arrow per switch_exits direction.
   * Reuses _buildDirectionalMarkers by feeding switch_exits as if they were
   * "directions", so each arrow sits on the corresponding cell edge pointing
   * OUT in that direction. */
  readonly switchExitArrows = computed<DirectionalMarker[]>(() => {
    const cells = (this.store.state()?.decision_cells ?? []) as DecisionCell[];
    return cells
      .filter((c) => c.kind === 'switch')
      .flatMap((c) => {
        const exits = c.switch_exits ?? [];
        if (exits.length === 0) return [];
        const fakeCell: DecisionCell = { ...c, directions: exits };
        return this._buildDirectionalMarkers(fakeCell, 'switch');
      });
  });

  private _buildDirectionalMarkers(
    cell: DecisionCell,
    kind: 'signal' | 'switch',
  ): DirectionalMarker[] {
    const dirs = cell.directions ?? [];
    if (dirs.length === 0) return [];
    const cs = this.cellSize;
    const cx = cell.c * cs + cs / 2;
    const cy = cell.r * cs + cs / 2;
    // Arrow tip sits 5% before the cell edge (off = 0.45 * cellSize).
    const off = cs * 0.33;
    return dirs.map((d, i) => {
      // Move (dx, dy) one direction step from centre toward edge
      const dx = d === 1 ? off : d === 3 ? -off : 0;
      const dy = d === 0 ? -off : d === 2 ? off : 0;
      return {
        id: `${kind}_${cell.r}_${cell.c}_${d}_${i}`,
        kind,
        x: cx + dx,
        y: cy + dy,
        rotation: d * 90,
        d,
        cx,
        cy,
      };
    });
  }

  readonly decisionLayers = computed<DecisionLayer[]>(() => {
    const result: DecisionLayer[] = [];
    for (const a of this.agents()) {
      if (!a.next_decision) continue;
      if (!this.store.isDecisionVisibleFor(a.handle)) continue;
      const layer = this._buildLayer(a, a.next_decision);
      if (layer) result.push(layer);
    }
    return result;
  });

  private _buildLayer(a: AgentDTO, nd: NextDecision): DecisionLayer | null {
    if (!a.position) return null;

    const pathPoints = nd.path.map(([r, c]) => ({
      x: c * this.cellSize + this.cellSize / 2,
      y: r * this.cellSize + this.cellSize / 2,
    }));

    if (pathPoints.length === 0) return null;

    let pathD = '';
    pathPoints.forEach((p, i) => {
      pathD += (i === 0 ? 'M' : 'L') + ` ${p.x} ${p.y} `;
    });

    const decisionCx = nd.decision_position[1] * this.cellSize + this.cellSize / 2;
    const decisionCy = nd.decision_position[0] * this.cellSize + this.cellSize / 2;

    const agentX = a.position[1] * this.cellSize + this.cellSize / 2;
    const agentY = a.position[0] * this.cellSize + this.cellSize / 2;
    const pillsX = agentX + 12;
    const pillsY = agentY + 8;

    const options: PillData[] = nd.options.map((opt: DecisionOption) => ({
      action: opt.action,
      label: opt.label,
      isOverride: a.override_action === opt.action,
    }));

    const cellKind: 'switch' | 'merge' =
      nd.cell_type === 'SWITCH' ? 'switch' : 'merge';
    return {
      handle: a.handle,
      color: this.agentColor(a.handle),
      cellKind,
      pathD,
      decisionCx,
      decisionCy,
      pillsX,
      pillsY,
      options,
    };
  }

  // ========== Pan Handlers ==========

  onMouseDown(event: MouseEvent) {
    // Nur Linke Maustaste, und nicht auf interaktiven Elementen
    if (event.button !== 0) return;
    const target = event.target as Element;
    if (target.closest('.agent') || target.closest('.pill')) {
      return;
    }
    this.isDragging = true;
    this.dragStartX = event.clientX;
    this.dragStartY = event.clientY;
    this.dragStartPanX = this.panX();
    this.dragStartPanY = this.panY();
    if (this.svgEl) {
      this.svgEl.style.cursor = 'grabbing';
    }
    event.preventDefault();
  }

  onMouseMove(event: MouseEvent) {
    if (!this.isDragging) return;
    const dx = event.clientX - this.dragStartX;
    const dy = event.clientY - this.dragStartY;
    // Mit preserveAspectRatio="meet" gibt es nur EINEN echten Scale-Faktor:
    // den groesseren der beiden (das limitiert die Anzeige).
    // -> beide Achsen MUESSEN den gleichen Scale verwenden.
    if (this.svgEl) {
      const rect = this.svgEl.getBoundingClientRect();
      const b = this.bbox();
      const w = (b.maxC - b.minC + 1) * this.cellSize;
      const h = (b.maxR - b.minR + 1) * this.cellSize;
      const scaleX = w / rect.width;
      const scaleY = h / rect.height;
      const scale = Math.max(scaleX, scaleY); // "meet" => der groessere ist sichtbar
      this.panX.set(this.dragStartPanX - dx * scale);
      this.panY.set(this.dragStartPanY - dy * scale);
    } else {
      this.panX.set(this.dragStartPanX - dx);
      this.panY.set(this.dragStartPanY - dy);
    }
  }

  // Step-Pan (Buttons): bewegt Map um eine Bildschirm-Haelfte
  panStep(dirX: number, dirY: number) {
    if (this.svgEl) {
      const rect = this.svgEl.getBoundingClientRect();
      const b = this.bbox();
      const w = (b.maxC - b.minC + 1) * this.cellSize;
      const h = (b.maxR - b.minR + 1) * this.cellSize;
      const scaleX = w / rect.width;
      const scaleY = h / rect.height;
      const scale = Math.max(scaleX, scaleY);
      // Step: 30% des Screen-Bereichs
      const stepPx = Math.min(rect.width, rect.height) * 0.3;
      this.panX.update((v) => v + dirX * stepPx * scale);
      this.panY.update((v) => v + dirY * stepPx * scale);
    }
  }

  onMouseUp() {
    if (this.isDragging) {
      this.isDragging = false;
      if (this.svgEl) {
        this.svgEl.style.cursor = 'grab';
      }
    }
  }

  onMouseLeave() {
    this.onMouseUp();
  }

  resetPan() {
    this.panX.set(0);
    this.panY.set(0);
    this.zoom.set(1);
  }

  // Zoom: smaller value = zoomed in (smaller viewBox)
  zoomIn() {
    this._zoomBy(1 / 1.2, 0.5, 0.5);
  }

  zoomOut() {
    this._zoomBy(1.2, 0.5, 0.5);
  }

  onWheel(event: WheelEvent) {
    event.preventDefault();
    if (!this.svgEl) return;
    const rect = this.svgEl.getBoundingClientRect();
    const cxRel = (event.clientX - rect.left) / rect.width;
    const cyRel = (event.clientY - rect.top) / rect.height;
    const factor = event.deltaY < 0 ? 1 / 1.1 : 1.1;
    this._zoomBy(factor, cxRel, cyRel);
  }

  // ========== Standard Helpers ==========

  tileX(t: RailTile): number { return t.c * this.cellSize; }
  tileY(t: RailTile): number { return t.r * this.cellSize; }

  tileTransform(t: RailTile): string {
    const cx = t.c * this.cellSize + this.cellSize / 2;
    const cy = t.r * this.cellSize + this.cellSize / 2;
    return `rotate(${t.rot} ${cx} ${cy})`;
  }

  tileHref(t: RailTile): string { return `/flatland-svg/${t.svg}`; }

  agentColor(handle: number): string {
    // Map paths and agent symbols need full opacity to read clearly,
    // so use the solid palette. Selected agents pop in focus state.
    const state = this.isSelected(handle) ? 'focus' : 'default';
    return this.agentColors.getColorSolid(handle, state);
  }

  agentX(a: AgentDTO): number {
    const pos = a.position ?? a.initial_position;
    if (!pos) return 0;
    return pos[1] * this.cellSize + this.cellSize / 2;
  }

  agentY(a: AgentDTO): number {
    const pos = a.position ?? a.initial_position;
    if (!pos) return 0;
    return pos[0] * this.cellSize + this.cellSize / 2;
  }

  targetX(a: AgentDTO): number {
    return a.target[1] * this.cellSize + this.cellSize / 2;
  }

  targetY(a: AgentDTO): number {
    return a.target[0] * this.cellSize + this.cellSize / 2;
  }

  isSelected(handle: number): boolean {
    return this.store.selectedHandles().has(handle);
  }

  toggleSelect(handle: number) {
    this.store.toggleAgentSelection(handle);
  }

  onPillClick(handle: number, action: number, isOverride: boolean) {
    if (isOverride) {
      this.store.clearOverride(handle);
    } else {
      this.store.setOverride(handle, action);
    }
  }

  trackByTile = (_: number, t: RailTile) => `${t.r}_${t.c}`;
  trackByAgent = (_: number, a: AgentDTO) => a.handle;
  trackByLayer = (_: number, l: DecisionLayer) => l.handle;
  trackByPill = (_: number, p: PillData) => p.action;

  /**
   * Apply a zoom factor while keeping a chosen anchor point fixed.
   * cxRel/cyRel are 0..1 relative coordinates inside the SVG element
   * (0.5/0.5 = window centre, cursor-relative for wheel zoom).
   */
  private _zoomBy(factor: number, cxRel: number, cyRel: number) {
    if (!this.svgEl) {
      this.zoom.update((v) => Math.min(5, Math.max(0.2, v * factor)));
      return;
    }
    const b = this.bbox();
    const oldZoom = this.zoom();
    const newZoom = Math.min(5, Math.max(0.2, oldZoom * factor));
    if (newZoom === oldZoom) return;

    const colSpan = (b.maxC - b.minC + 1) * this.cellSize;
    const rowSpan = (b.maxR - b.minR + 1) * this.cellSize;
    const vbX = b.minC * this.cellSize + this.panX();
    const vbY = b.minR * this.cellSize + this.panY();

    // World point under the anchor BEFORE zoom
    const anchorVbX = vbX + cxRel * (colSpan * oldZoom);
    const anchorVbY = vbY + cyRel * (rowSpan * oldZoom);

    this.zoom.set(newZoom);

    // Solve new pan so that the anchor world point stays under (cxRel, cyRel)
    const newPanX = anchorVbX - cxRel * (colSpan * newZoom) - b.minC * this.cellSize;
    const newPanY = anchorVbY - cyRel * (rowSpan * newZoom) - b.minR * this.cellSize;
    this.panX.set(newPanX);
    this.panY.set(newPanY);
  }
}
