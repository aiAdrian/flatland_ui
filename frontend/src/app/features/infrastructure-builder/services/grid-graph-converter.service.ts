import { Injectable } from '@angular/core';
import {
  DIRECTION_OFFSET,
  DIRECTIONS,
  Direction,
  GridConfig,
  OPPOSITE_DIRECTION,
  TrackCell,
  cellId,
} from '../models/grid.model';
import { InfrastructureEdge, InfrastructureGraph, InfrastructureNode } from '../models/graph.model';

@Injectable({ providedIn: 'root' })
export class GridGraphConverterService {
  withDerivedConnections(cells: TrackCell[], grid: GridConfig): TrackCell[] {
    const cellById = new Map(cells.map((cell) => [cell.id, cell]));

    return cells
      .filter((cell) => this.isInsideGrid(cell.x, cell.y, grid))
      .map((cell) => {
        const connections = DIRECTIONS.filter((direction) => {
          const offset = DIRECTION_OFFSET[direction];
          return cellById.has(cellId(cell.x + offset.x, cell.y + offset.y));
        });

        return {
          ...cell,
          connections: this.limitConnectionsForCellKind(cell, connections, cellById),
        };
      });
  }

  toGraph(cells: TrackCell[], grid: GridConfig): InfrastructureGraph {
    const connectedCells = this.withDerivedConnections(cells, grid);
    const nodeByCell = new Map<string, InfrastructureNode>();

    for (const cell of connectedCells) {
      nodeByCell.set(cell.id, {
        id: this.nodeId(cell.x, cell.y),
        x: cell.x,
        y: cell.y,
        kind: cell.kind === 'empty' ? 'track' : cell.kind,
      });
    }

    const edges: InfrastructureEdge[] = [];
    const seen = new Set<string>();

    for (const cell of connectedCells) {
      const from = nodeByCell.get(cell.id);
      if (!from) {
        continue;
      }

      for (const direction of cell.connections) {
        const offset = DIRECTION_OFFSET[direction];
        const neighborCell = connectedCells.find((candidate) => (
          candidate.x === cell.x + offset.x && candidate.y === cell.y + offset.y
        ));

        if (!neighborCell?.connections.includes(OPPOSITE_DIRECTION[direction])) {
          continue;
        }

        const to = nodeByCell.get(neighborCell.id);
        if (!to) {
          continue;
        }

        const edgeKey = [from.id, to.id].sort().join('__');
        if (seen.has(edgeKey)) {
          continue;
        }

        seen.add(edgeKey);
        edges.push({
          id: `edge_${from.id}_${to.id}`,
          from: from.id,
          to: to.id,
          direction,
          bidirectional: true,
        });
      }
    }

    return {
      nodes: Array.from(nodeByCell.values()),
      edges,
    };
  }

  nodeId(x: number, y: number): string {
    return `n_${x}_${y}`;
  }

  private isInsideGrid(x: number, y: number, grid: GridConfig): boolean {
    return x >= 0 && y >= 0 && x < grid.width && y < grid.height;
  }

  private limitConnectionsForCellKind(
    cell: TrackCell,
    connections: Direction[],
    cellById: Map<string, TrackCell>,
  ): Direction[] {
    if (cell.kind === 'switch' || cell.kind === 'crossing') {
      return connections;
    }

    if (connections.length <= 2) {
      return connections;
    }

    const switchConnections = connections.filter((direction) => {
      const offset = DIRECTION_OFFSET[direction];
      const neighbor = cellById.get(cellId(cell.x + offset.x, cell.y + offset.y));
      return neighbor?.kind === 'switch';
    });

    if (switchConnections.length >= 2) {
      return switchConnections.slice(0, 2);
    }

    if (switchConnections.length === 1) {
      const switchDirection = switchConnections[0];
      const opposite = OPPOSITE_DIRECTION[switchDirection];
      if (connections.includes(opposite)) {
        return [opposite, switchDirection].sort((a, b) => DIRECTIONS.indexOf(a) - DIRECTIONS.indexOf(b));
      }

      const continuation = connections.find((direction) => direction !== switchDirection);
      return continuation
        ? [switchDirection, continuation].sort((a, b) => DIRECTIONS.indexOf(a) - DIRECTIONS.indexOf(b))
        : [switchDirection];
    }

    if (connections.includes('N') && connections.includes('S')) {
      return ['N', 'S'];
    }

    if (connections.includes('E') && connections.includes('W')) {
      return ['E', 'W'];
    }

    return connections.slice(0, 2);
  }
}
