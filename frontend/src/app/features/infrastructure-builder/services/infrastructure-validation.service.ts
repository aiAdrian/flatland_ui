import { Injectable } from '@angular/core';
import {
  DIRECTION_OFFSET,
  GridConfig,
  OPPOSITE_DIRECTION,
  TrackCell,
  cellId,
} from '../models/grid.model';
import { InfrastructureScene, Station } from '../models/scene.model';
import { ValidationIssue, ValidationResult } from '../models/validation.model';

@Injectable({ providedIn: 'root' })
export class InfrastructureValidationService {
  validate(scene: InfrastructureScene): ValidationResult {
    const errors: ValidationIssue[] = [];
    const warnings: ValidationIssue[] = [];
    const cellById = new Map(scene.cells.map((cell) => [cell.id, cell]));

    if (!Number.isFinite(scene.grid.width) || scene.grid.width < 1) {
      errors.push(this.issue('grid-width', 'error', 'Grid width must be at least 1.'));
    }

    if (!Number.isFinite(scene.grid.height) || scene.grid.height < 1) {
      errors.push(this.issue('grid-height', 'error', 'Grid height must be at least 1.'));
    }

    for (const cell of scene.cells) {
      if (!this.isInsideGrid(cell.x, cell.y, scene.grid)) {
        errors.push(this.issue(`cell-outside-${cell.id}`, 'error', `Track cell ${cell.id} is outside the grid.`, { cellId: cell.id }));
        continue;
      }

      if (cell.connections.length === 0 && cell.kind !== 'station' && cell.kind !== 'dead-end') {
        errors.push(this.issue(`cell-isolated-${cell.id}`, 'error', `Track cell ${cell.id} is isolated.`, { cellId: cell.id }));
      }

      for (const direction of cell.connections) {
        const offset = DIRECTION_OFFSET[direction];
        const neighborId = cellId(cell.x + offset.x, cell.y + offset.y);
        const neighbor = cellById.get(neighborId);

        if (!neighbor) {
          errors.push(this.issue(`missing-neighbor-${cell.id}-${direction}`, 'error', `Connection ${direction} from ${cell.id} has no neighbouring track.`, { cellId: cell.id }));
          continue;
        }

        if (!neighbor.connections.includes(OPPOSITE_DIRECTION[direction])) {
          errors.push(this.issue(`one-way-${cell.id}-${direction}`, 'error', `Connection ${direction} from ${cell.id} is not matched by its neighbour.`, { cellId: cell.id }));
        }
      }
    }

    for (const station of scene.stations) {
      const stationCell = this.findCell(station, scene.cells);
      if (!stationCell) {
        errors.push(this.issue(`station-no-cell-${station.id}`, 'error', `Station ${station.name} is not placed on a track cell.`, { cellId: cellId(station.x, station.y) }));
      }
    }

    for (const agent of scene.agents) {
      const startCell = agent.startCellId ? cellById.get(agent.startCellId) : null;
      const targetCell = agent.targetCellId ? cellById.get(agent.targetCellId) : null;

      if (!startCell) {
        errors.push(this.issue(`agent-start-${agent.id}`, 'error', `${agent.name} needs a valid start track cell.`, { agentId: agent.id }));
      }

      if (!targetCell) {
        errors.push(this.issue(`agent-target-${agent.id}`, 'error', `${agent.name} needs a valid target track cell.`, { agentId: agent.id }));
      }

      if (agent.startCellId && agent.targetCellId && agent.startCellId === agent.targetCellId) {
        errors.push(this.issue(`agent-same-${agent.id}`, 'error', `${agent.name} start and target must differ.`, { agentId: agent.id }));
      }

      if (startCell && targetCell && scene.graph.edges.length === 0 && scene.cells.length > 1) {
        warnings.push(this.issue(`agent-route-${agent.id}`, 'warning', `${agent.name} may not have a route because the graph has no edges yet.`, { agentId: agent.id }));
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
    };
  }

  private findCell(station: Station, cells: TrackCell[]): TrackCell | undefined {
    return cells.find((cell) => cell.x === station.x && cell.y === station.y);
  }

  private isInsideGrid(x: number, y: number, grid: GridConfig): boolean {
    return x >= 0 && y >= 0 && x < grid.width && y < grid.height;
  }

  private issue(
    id: string,
    severity: ValidationIssue['severity'],
    message: string,
    refs: Partial<ValidationIssue> = {},
  ): ValidationIssue {
    return { id, severity, message, ...refs };
  }
}
