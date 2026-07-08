import { Direction } from './grid.model';

export interface InfrastructureNode {
  id: string;
  x: number;
  y: number;
  kind: 'track' | 'switch' | 'crossing' | 'station' | 'dead-end';
  metadata?: Record<string, unknown>;
}

export interface InfrastructureEdge {
  id: string;
  from: string;
  to: string;
  direction: Direction;
  bidirectional?: boolean;
  metadata?: Record<string, unknown>;
}

export interface InfrastructureGraph {
  nodes: InfrastructureNode[];
  edges: InfrastructureEdge[];
}
