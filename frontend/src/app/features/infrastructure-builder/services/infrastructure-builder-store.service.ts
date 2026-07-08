import { Injectable, computed, inject, signal } from '@angular/core';
import { InfrastructureAgent } from '../models/agent.model';
import { GridConfig, GridPosition, TrackCell, cellId } from '../models/grid.model';
import { InfrastructureScene, Station } from '../models/scene.model';
import { InfrastructureBuilderTool } from '../models/tool.model';
import { EMPTY_VALIDATION_RESULT } from '../models/validation.model';
import { AgentRandomizationService } from './agent-randomization.service';
import { GridGraphConverterService } from './grid-graph-converter.service';
import { InfrastructureValidationService } from './infrastructure-validation.service';

@Injectable({ providedIn: 'root' })
export class InfrastructureBuilderStoreService {
  private readonly graphConverter = inject(GridGraphConverterService);
  private readonly validator = inject(InfrastructureValidationService);
  private readonly randomizer = inject(AgentRandomizationService);

  readonly scene = signal<InfrastructureScene>(this.createDefaultScene());
  readonly activeTool = signal<InfrastructureBuilderTool>('track');
  readonly selectedCellId = signal<string | null>(null);
  readonly selectedAgentId = signal<string | null>(null);
  readonly randomAgentCount = signal(2);

  readonly selectedCell = computed(() => {
    const selected = this.selectedCellId();
    return selected ? this.scene().cells.find((cell) => cell.id === selected) ?? null : null;
  });

  readonly selectedAgent = computed(() => {
    const selected = this.selectedAgentId();
    return selected ? this.scene().agents.find((agent) => agent.id === selected) ?? null : null;
  });

  newScene(width = 20, height = 12): void {
    this.scene.set(this.createDefaultScene({ width, height, cellSizePx: 28 }));
    this.selectedAgentId.set(null);
    this.selectedCellId.set(null);
  }

  newRandomScene(width = 20, height = 12): void {
    const grid = {
      width: this.clampInt(width, 6, 80),
      height: this.clampInt(height, 5, 60),
      cellSizePx: 28,
    };
    const scene = this.createDefaultScene(grid);
    const centerY = Math.max(1, Math.floor(grid.height / 2));
    const branchX = Math.max(2, Math.floor(grid.width / 2));
    const cells: TrackCell[] = [];

    for (let x = 1; x < grid.width - 1; x++) {
      cells.push({
        id: cellId(x, centerY),
        x,
        y: centerY,
        kind: x === branchX ? 'switch' : 'track',
        connections: [],
        ...(x === branchX ? { metadata: { switchFacing: 'forward' } } : {}),
      });
    }

    const branchEndY = Math.max(1, centerY - 3);
    for (let y = centerY - 1; y >= branchEndY; y--) {
      cells.push({
        id: cellId(branchX, y),
        x: branchX,
        y,
        kind: y === branchEndY ? 'station' : 'track',
        connections: [],
        ...(y === branchEndY ? { stationId: 'station_branch' } : {}),
      });
    }

    const stations: Station[] = [
      { id: 'station_branch', name: 'Station 1', x: branchX, y: branchEndY },
    ];
    const agents: InfrastructureAgent[] = [{
      id: `agent_${Date.now()}`,
      name: 'Train 1',
      color: 'var(--sbb-color-blue)',
      speed: 1,
      startCellId: cellId(1, centerY),
      targetCellId: cellId(grid.width - 2, centerY),
      start: { x: 1, y: centerY },
      target: { x: grid.width - 2, y: centerY },
    }];

    this.scene.set(this.rebuild({
      ...scene,
      name: 'Random Infrastructure Scene',
      cells,
      stations,
      agents,
    }));
    this.selectedAgentId.set(agents[0].id);
    this.selectedCellId.set(null);
  }

  loadScene(scene: InfrastructureScene): void {
    this.scene.set(this.rebuild({ ...scene }));
    this.selectedAgentId.set(scene.agents[0]?.id ?? null);
    this.selectedCellId.set(null);
  }

  updateSceneName(name: string): void {
    this.patchScene({ name });
  }

  updateLinkedLayoutId(linkedLayoutId: string): void {
    this.patchScene({ linkedLayoutId: linkedLayoutId.trim() || undefined });
  }

  updateGrid(width: number, height: number): void {
    const current = this.scene();
    const grid = {
      ...current.grid,
      width: this.clampInt(width, 1, 80),
      height: this.clampInt(height, 1, 60),
    };
    const cells = current.cells.filter((cell) => cell.x < grid.width && cell.y < grid.height);
    const stations = current.stations.filter((station) => station.x < grid.width && station.y < grid.height);
    const cellIds = new Set(cells.map((cell) => cell.id));

    this.scene.set(this.rebuild({
      ...current,
      grid,
      cells,
      stations,
      agents: current.agents.map((agent) => ({
        ...agent,
        ...(agent.startCellId && !cellIds.has(agent.startCellId) ? { startCellId: undefined, start: undefined } : {}),
        ...(agent.targetCellId && !cellIds.has(agent.targetCellId) ? { targetCellId: undefined, target: undefined } : {}),
      })),
    }));
  }

  applyTool(position: GridPosition): void {
    const tool = this.activeTool();
    this.selectedCellId.set(cellId(position.x, position.y));

    if (tool === 'select') {
      return;
    }

    if (tool === 'track') {
      this.upsertTrack(position, 'track');
      return;
    }

    if (tool === 'erase') {
      this.eraseCell(position);
      return;
    }

    if (tool === 'switch') {
      this.upsertSwitch(position);
      return;
    }

    if (tool === 'station') {
      this.placeStation(position);
      return;
    }

    if (tool === 'agent-route') {
      return;
    }

    if (tool === 'agent-start') {
      this.assignAgentEndpoint(position, 'start');
      return;
    }

    if (tool === 'agent-target') {
      this.assignAgentEndpoint(position, 'target');
    }
  }

  addAgent(): void {
    const current = this.scene();
    const agent: InfrastructureAgent = {
      id: `agent_${Date.now()}`,
      name: `Train ${current.agents.length + 1}`,
      color: 'var(--sbb-color-blue)',
      speed: 1,
    };

    this.scene.set(this.rebuild({ ...current, agents: [...current.agents, agent] }));
    this.selectedAgentId.set(agent.id);
  }

  selectAgent(agentId: string): void {
    this.selectedAgentId.set(agentId);
  }

  generateRandomAgents(count = this.randomAgentCount()): void {
    const current = this.scene();
    const agents = this.randomizer.createAgents(current.cells, count, current.agents.length);

    if (agents.length === 0) {
      return;
    }

    this.scene.set(this.rebuild({ ...current, agents: [...current.agents, ...agents] }));
    this.selectedAgentId.set(agents[0].id);
  }

  removeSelectedAgent(): void {
    const selected = this.selectedAgentId();
    if (!selected) {
      return;
    }

    const current = this.scene();
    const agents = current.agents.filter((agent) => agent.id !== selected);
    this.scene.set(this.rebuild({ ...current, agents }));
    this.selectedAgentId.set(agents[0]?.id ?? null);
  }

  assignSelectedAgentRoute(start: GridPosition, target: GridPosition): void {
    const startId = cellId(start.x, start.y);
    const targetId = cellId(target.x, target.y);

    if (startId === targetId) {
      return;
    }

    const current = this.scene();
    const hasStartTrack = current.cells.some((cell) => cell.id === startId);
    const hasTargetTrack = current.cells.some((cell) => cell.id === targetId);

    if (!hasStartTrack || !hasTargetTrack) {
      return;
    }

    if (!this.selectedAgentId()) {
      this.addAgent();
    }

    const selected = this.selectedAgentId();
    if (!selected) {
      return;
    }

    const nextScene = this.scene();
    this.scene.set(this.rebuild({
      ...nextScene,
      agents: nextScene.agents.map((agent) => agent.id === selected
        ? {
          ...agent,
          startCellId: startId,
          targetCellId: targetId,
          start: { x: start.x, y: start.y },
          target: { x: target.x, y: target.y },
        }
        : agent),
    }));
  }

  deleteSelectedElement(): void {
    const selectedCell = this.selectedCell();
    if (selectedCell) {
      this.eraseCell({ x: selectedCell.x, y: selectedCell.y });
      this.selectedCellId.set(null);
      return;
    }

    this.removeSelectedAgent();
  }

  validateNow(): void {
    this.scene.set(this.rebuild(this.scene()));
  }

  private upsertTrack(position: GridPosition, kind: TrackCell['kind']): void {
    const current = this.scene();
    const id = cellId(position.x, position.y);
    const existing = current.cells.find((cell) => cell.id === id);
    const nextCell: TrackCell = {
      ...(existing ?? { id, x: position.x, y: position.y, connections: [] }),
      kind,
    };
    const cells = existing
      ? current.cells.map((cell) => cell.id === id ? nextCell : cell)
      : [...current.cells, nextCell];

    this.scene.set(this.rebuild({ ...current, cells }));
  }

  private upsertSwitch(position: GridPosition): void {
    const current = this.scene();
    const id = cellId(position.x, position.y);
    const existing = current.cells.find((cell) => cell.id === id);
    const currentFacing = existing?.metadata?.['switchFacing'] === 'reverse' ? 'reverse' : 'forward';
    const switchFacing = existing?.kind === 'switch' && currentFacing === 'forward' ? 'reverse' : 'forward';
    const nextCell: TrackCell = {
      ...(existing ?? { id, x: position.x, y: position.y, connections: [] }),
      kind: 'switch',
      metadata: {
        ...(existing?.metadata ?? {}),
        switchFacing,
      },
    };
    const cells = existing
      ? current.cells.map((cell) => cell.id === id ? nextCell : cell)
      : [...current.cells, nextCell];

    this.scene.set(this.rebuild({ ...current, cells }));
  }

  private eraseCell(position: GridPosition): void {
    const current = this.scene();
    const id = cellId(position.x, position.y);
    const stations = current.stations.filter((station) => station.x !== position.x || station.y !== position.y);

    this.scene.set(this.rebuild({
      ...current,
      cells: current.cells.filter((cell) => cell.id !== id),
      stations,
      agents: current.agents.map((agent) => ({
        ...agent,
        ...(agent.startCellId === id ? { startCellId: undefined, start: undefined } : {}),
        ...(agent.targetCellId === id ? { targetCellId: undefined, target: undefined } : {}),
      })),
    }));
  }

  private placeStation(position: GridPosition): void {
    const current = this.scene();
    const id = cellId(position.x, position.y);
    const stationId = `station_${position.x}_${position.y}`;
    const station: Station = {
      id: stationId,
      name: `Station ${current.stations.length + 1}`,
      x: position.x,
      y: position.y,
    };
    const existing = current.cells.find((cell) => cell.id === id);
    const stationCell: TrackCell = {
      ...(existing ?? { id, x: position.x, y: position.y, connections: [] }),
      kind: 'station',
      stationId,
    };

    this.scene.set(this.rebuild({
      ...current,
      cells: existing
        ? current.cells.map((cell) => cell.id === id ? stationCell : cell)
        : [...current.cells, stationCell],
      stations: current.stations.some((candidate) => candidate.x === position.x && candidate.y === position.y)
        ? current.stations
        : [...current.stations, station],
    }));
  }

  private assignAgentEndpoint(position: GridPosition, endpoint: 'start' | 'target'): void {
    const current = this.scene();
    const id = cellId(position.x, position.y);
    const track = current.cells.find((cell) => cell.id === id);

    if (!track) {
      return;
    }

    if (!this.selectedAgentId()) {
      this.addAgent();
    }

    const selected = this.selectedAgentId();
    if (!selected) {
      return;
    }

    this.scene.set(this.rebuild({
      ...this.scene(),
      agents: this.scene().agents.map((agent) => agent.id === selected
        ? {
          ...agent,
          ...(endpoint === 'start'
            ? { startCellId: id, start: { x: position.x, y: position.y } }
            : { targetCellId: id, target: { x: position.x, y: position.y } }),
        }
        : agent),
    }));
  }

  private patchScene(patch: Partial<InfrastructureScene>): void {
    this.scene.set(this.rebuild({ ...this.scene(), ...patch }));
  }

  private rebuild(scene: InfrastructureScene): InfrastructureScene {
    const cells = this.graphConverter.withDerivedConnections(scene.cells, scene.grid);
    const graph = this.graphConverter.toGraph(cells, scene.grid);
    const next = {
      ...scene,
      cells,
      graph,
      updatedAt: new Date().toISOString(),
    };

    return {
      ...next,
      validation: this.validator.validate(next),
    };
  }

  private createDefaultScene(grid: GridConfig = { width: 20, height: 12, cellSizePx: 28 }): InfrastructureScene {
    const now = new Date().toISOString();
    return {
      id: `scene_${Date.now()}`,
      name: 'Untitled Infrastructure Scene',
      version: 'fib-v1',
      createdAt: now,
      updatedAt: now,
      grid,
      cells: [],
      graph: { nodes: [], edges: [] },
      stations: [],
      agents: [],
      validation: EMPTY_VALIDATION_RESULT,
      metadata: {},
    };
  }

  private clampInt(value: number, min: number, max: number): number {
    if (!Number.isFinite(value)) {
      return min;
    }
    return Math.max(min, Math.min(max, Math.round(value)));
  }
}
