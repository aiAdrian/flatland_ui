import { Injectable } from '@angular/core';
import { InfrastructureAgent } from '../models/agent.model';
import { TrackCell } from '../models/grid.model';

const AGENT_COLOR_TOKENS = [
  'var(--sbb-color-red)',
  'var(--sbb-color-blue)',
  'var(--sbb-color-green)',
  'var(--sbb-color-orange)',
  'var(--sbb-color-violet)',
  'var(--sbb-color-iron)',
];

@Injectable({ providedIn: 'root' })
export class AgentRandomizationService {
  createAgents(trackCells: TrackCell[], count: number, existingCount = 0): InfrastructureAgent[] {
    if (trackCells.length < 2 || count < 1) {
      return [];
    }

    const agents: InfrastructureAgent[] = [];

    for (let index = 0; index < count; index++) {
      const start = this.pick(trackCells);
      let target = this.pick(trackCells);
      let guard = 0;

      while (target.id === start.id && guard < 20) {
        target = this.pick(trackCells);
        guard++;
      }

      agents.push({
        id: `agent_${Date.now()}_${index}`,
        name: `Train ${existingCount + index + 1}`,
        startCellId: start.id,
        targetCellId: target.id,
        start: { x: start.x, y: start.y },
        target: { x: target.x, y: target.y },
        color: AGENT_COLOR_TOKENS[(existingCount + index) % AGENT_COLOR_TOKENS.length],
        speed: 1,
      });
    }

    return agents;
  }

  private pick(cells: TrackCell[]): TrackCell {
    return cells[Math.floor(Math.random() * cells.length)];
  }
}
