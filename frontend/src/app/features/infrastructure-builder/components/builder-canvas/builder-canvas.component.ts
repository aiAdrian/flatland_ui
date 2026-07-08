import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal } from '@angular/core';
import { InfrastructureAgent } from '../../models/agent.model';
import { Direction, GridPosition, TrackCell, cellId } from '../../models/grid.model';
import { InfrastructureBuilderStoreService } from '../../services/infrastructure-builder-store.service';

@Component({
  selector: 'app-builder-canvas',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './builder-canvas.component.html',
  styleUrl: './builder-canvas.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class BuilderCanvasComponent {
  readonly store = inject(InfrastructureBuilderStoreService);
  readonly zoom = signal(1);
  readonly panX = signal(0);
  readonly panY = signal(0);
  readonly isPanning = signal(false);
  readonly routePreviewCellIds = signal<Set<string>>(new Set());
  readonly zoomPercent = computed(() => Math.round(this.zoom() * 100));

  private dragStartX = 0;
  private dragStartY = 0;
  private dragStartPanX = 0;
  private dragStartPanY = 0;
  private isDrawingCells = false;
  private agentRouteStart: GridPosition | null = null;

  readonly positions = computed<GridPosition[]>(() => {
    const grid = this.store.scene().grid;
    const positions: GridPosition[] = [];

    for (let y = 0; y < grid.height; y++) {
      for (let x = 0; x < grid.width; x++) {
        positions.push({ x, y });
      }
    }

    return positions;
  });

  cellAt(position: GridPosition): TrackCell | undefined {
    return this.store.scene().cells.find((cell) => cell.x === position.x && cell.y === position.y);
  }

  positionId(position: GridPosition): string {
    return cellId(position.x, position.y);
  }

  cellLabel(position: GridPosition): string {
    const cell = this.cellAt(position);
    if (!cell) {
      return '';
    }

    if (cell.kind === 'station') {
      return 'S';
    }

    return cell.connections.length ? cell.connections.join('') : 'T';
  }

  tileHref(cell: TrackCell | undefined): string {
    if (!cell) {
      return '/flatland-svg/Background_white.svg';
    }

    if (cell.kind === 'station') {
      if (this.hasConnectionPair(cell, 'N', 'S')) {
        return '/flatland-svg/Bahnhof_color-d50000_Gleis_vertikal.svg';
      }
      return '/flatland-svg/Bahnhof_color-d50000_Gleis_horizontal.svg';
    }

    if (cell.kind === 'switch' && cell.connections.length >= 4) {
      return '/flatland-svg/Gleis_Diamond_Crossing.svg';
    }

    if (cell.kind === 'switch' && cell.connections.length >= 3) {
      return this.switchTileHref(cell);
    }

    if (this.hasConnectionPair(cell, 'N', 'S')) {
      return '/flatland-svg/Gleis_vertikal.svg';
    }

    if (this.hasConnectionPair(cell, 'E', 'W')) {
      return '/flatland-svg/Gleis_horizontal.svg';
    }

    if (this.hasConnectionPair(cell, 'N', 'E')) {
      return '/flatland-svg/Gleis_Kurve_oben_rechts.svg';
    }

    if (this.hasConnectionPair(cell, 'N', 'W')) {
      return '/flatland-svg/Gleis_Kurve_oben_links.svg';
    }

    if (this.hasConnectionPair(cell, 'S', 'E')) {
      return '/flatland-svg/Gleis_Kurve_unten_rechts.svg';
    }

    if (this.hasConnectionPair(cell, 'S', 'W')) {
      return '/flatland-svg/Gleis_Kurve_unten_links.svg';
    }

    if (cell.connections.length === 1 || cell.kind === 'dead-end') {
      return '/flatland-svg/Gleis_Deadend.svg';
    }

    return '/flatland-svg/Background_rail.svg';
  }

  startAgents(cell: TrackCell | undefined): InfrastructureAgent[] {
    if (!cell) {
      return [];
    }

    return this.store.scene().agents
      .filter((agent) => agent.startCellId === cell.id);
  }

  targetAgents(cell: TrackCell | undefined): InfrastructureAgent[] {
    if (!cell) {
      return [];
    }

    return this.store.scene().agents
      .filter((agent) => agent.targetCellId === cell.id);
  }

  agentHandle(agent: InfrastructureAgent): number {
    const index = this.store.scene().agents.findIndex((candidate) => candidate.id === agent.id);
    return index >= 0 ? index : 0;
  }

  agentMarkerTitle(agent: InfrastructureAgent, endpoint: 'start' | 'target'): string {
    const handle = this.agentHandle(agent);
    const label = endpoint === 'start' ? 'Start (Agent)' : 'Ziel';
    const position = endpoint === 'start' ? agent.start : agent.target;
    const suffix = position ? ` (${position.x}, ${position.y})` : '';
    return `${label}: Train ${handle} - ${agent.name}${suffix}`;
  }

  isAgentRoutePreview(position: GridPosition): boolean {
    return this.routePreviewCellIds().has(this.positionId(position));
  }

  onCellClick(position: GridPosition): void {
    if (this.store.activeTool() !== 'agent-route') {
      return;
    }

    const cell = this.cellAt(position);
    if (!cell) {
      return;
    }

    if (!this.agentRouteStart) {
      this.agentRouteStart = position;
      this.routePreviewCellIds.set(this.lineCellIds(position, position));
      this.store.selectedCellId.set(cellId(position.x, position.y));
      return;
    }

    this.store.assignSelectedAgentRoute(this.agentRouteStart, position);
    this.agentRouteStart = null;
    this.routePreviewCellIds.set(new Set());
    this.store.selectedCellId.set(cellId(position.x, position.y));
  }

  onCellMouseDown(event: MouseEvent, position: GridPosition): void {
    if (event.button !== 0) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    if (this.store.activeTool() === 'agent-route') {
      return;
    }

    this.isDrawingCells = this.store.activeTool() === 'track' || this.store.activeTool() === 'erase';
    this.store.applyTool(position);
  }

  onCellMouseEnter(position: GridPosition): void {
    if (this.agentRouteStart) {
      this.routePreviewCellIds.set(this.lineCellIds(this.agentRouteStart, position));
      return;
    }

    if (!this.isDrawingCells) {
      return;
    }

    this.store.applyTool(position);
  }

  onCellMouseUp(position?: GridPosition): void {
    this.isDrawingCells = false;
  }

  onCellKeydown(event: KeyboardEvent, position: GridPosition): void {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }

    event.preventDefault();
    this.store.applyTool(position);
  }

  onCellContextMenu(event: MouseEvent, position: GridPosition): void {
    event.preventDefault();
    this.store.activeTool.set('erase');
    this.store.applyTool(position);
  }

  onCanvasMouseDown(event: MouseEvent): void {
    if (event.button !== 1) {
      return;
    }

    this.isPanning.set(true);
    this.dragStartX = event.clientX;
    this.dragStartY = event.clientY;
    this.dragStartPanX = this.panX();
    this.dragStartPanY = this.panY();
    event.preventDefault();
  }

  onCanvasMouseMove(event: MouseEvent): void {
    if (!this.isPanning()) {
      return;
    }

    this.panX.set(this.dragStartPanX + event.clientX - this.dragStartX);
    this.panY.set(this.dragStartPanY + event.clientY - this.dragStartY);
  }

  onCanvasMouseUp(): void {
    this.isPanning.set(false);
    this.onCellMouseUp();
  }

  onWheel(event: WheelEvent): void {
    event.preventDefault();
    const target = event.currentTarget as HTMLElement;
    const rect = target.getBoundingClientRect();
    const cxRel = rect.width ? (event.clientX - rect.left) / rect.width : 0.5;
    const cyRel = rect.height ? (event.clientY - rect.top) / rect.height : 0.5;
    const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1;

    this.zoomBy(factor, cxRel, cyRel, rect.width, rect.height);
  }

  zoomIn(): void {
    this.zoomBy(1.2, 0.5, 0.5);
  }

  zoomOut(): void {
    this.zoomBy(1 / 1.2, 0.5, 0.5);
  }

  panStep(dirX: number, dirY: number): void {
    const step = 120;
    this.panX.update((value) => value + dirX * step);
    this.panY.update((value) => value + dirY * step);
  }

  resetPan(): void {
    this.panX.set(0);
    this.panY.set(0);
    this.zoom.set(1);
  }

  private zoomBy(
    factor: number,
    cxRel: number,
    cyRel: number,
    viewportWidth = 0,
    viewportHeight = 0,
  ): void {
    const oldZoom = this.zoom();
    const newZoom = Math.min(4, Math.max(0.35, oldZoom * factor));
    if (newZoom === oldZoom) {
      return;
    }

    this.zoom.set(newZoom);

    if (viewportWidth > 0 && viewportHeight > 0) {
      const anchorX = cxRel * viewportWidth;
      const anchorY = cyRel * viewportHeight;
      const ratio = newZoom / oldZoom;
      this.panX.set(anchorX - (anchorX - this.panX()) * ratio);
      this.panY.set(anchorY - (anchorY - this.panY()) * ratio);
    }
  }

  private hasConnectionPair(cell: TrackCell, first: Direction, second: Direction): boolean {
    return cell.connections.includes(first) && cell.connections.includes(second);
  }

  private lineCellIds(start: GridPosition, target: GridPosition): Set<string> {
    const ids = new Set<string>();
    const deltaX = Math.abs(target.x - start.x);
    const deltaY = Math.abs(target.y - start.y);
    const stepX = start.x < target.x ? 1 : -1;
    const stepY = start.y < target.y ? 1 : -1;
    let error = deltaX - deltaY;
    let currentX = start.x;
    let currentY = start.y;

    while (true) {
      ids.add(cellId(currentX, currentY));
      if (currentX === target.x && currentY === target.y) {
        return ids;
      }

      const doubledError = error * 2;
      if (doubledError > -deltaY) {
        error -= deltaY;
        currentX += stepX;
      }

      if (doubledError < deltaX) {
        error += deltaX;
        currentY += stepY;
      }
    }
  }

  private switchTileHref(cell: TrackCell): string {
    const isReverse = cell.metadata?.['switchFacing'] === 'reverse';

    if (this.hasConnectionPair(cell, 'E', 'W')) {
      if (cell.connections.includes('N')) {
        return isReverse
          ? '/flatland-svg/Weiche_horizontal_oben_links.svg'
          : '/flatland-svg/Weiche_horizontal_oben_rechts.svg';
      }

      if (cell.connections.includes('S')) {
        return isReverse
          ? '/flatland-svg/Weiche_horizontal_unten_links.svg'
          : '/flatland-svg/Weiche_horizontal_unten_rechts.svg';
      }

      return '/flatland-svg/Weiche_Symetrical_gerade.svg';
    }

    if (this.hasConnectionPair(cell, 'N', 'S')) {
      if (cell.connections.includes('E')) {
        return isReverse
          ? '/flatland-svg/Weiche_vertikal_unten_rechts.svg'
          : '/flatland-svg/Weiche_vertikal_oben_rechts.svg';
      }

      if (cell.connections.includes('W')) {
        return isReverse
          ? '/flatland-svg/Weiche_vertikal_unten_links.svg'
          : '/flatland-svg/Weiche_vertikal_oben_links.svg';
      }

      return '/flatland-svg/Weiche_Symetrical_gerade.svg';
    }

    return '/flatland-svg/Weiche_Symetrical.svg';
  }
}
