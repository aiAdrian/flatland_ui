import { Injectable } from '@angular/core';
import { InfrastructureScene } from '../models/scene.model';

@Injectable({ providedIn: 'root' })
export class InfrastructureExportService {
  exportJson(scene: InfrastructureScene): string {
    return JSON.stringify({
      version: scene.version,
      grid: {
        width: scene.grid.width,
        height: scene.grid.height,
      },
      cells: scene.cells,
      nodes: scene.graph.nodes,
      edges: scene.graph.edges,
      stations: scene.stations,
      agents: scene.agents,
      linkedLayoutId: scene.linkedLayoutId,
      metadata: scene.metadata,
    }, null, 2);
  }

  exportMermaid(scene: InfrastructureScene): string {
    const lines = ['graph LR'];

    for (const node of scene.graph.nodes) {
      lines.push(`  ${node.id}[${node.kind} ${node.x},${node.y}]`);
    }

    for (const edge of scene.graph.edges) {
      lines.push(`  ${edge.from} --> ${edge.to}`);
    }

    return lines.join('\n');
  }
}
