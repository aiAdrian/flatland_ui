import { GridPosition } from './grid.model';

export interface InfrastructureAgent {
  id: string;
  name: string;
  startCellId?: string;
  targetCellId?: string;
  start?: GridPosition;
  target?: GridPosition;
  color?: string;
  speed?: number;
  metadata?: Record<string, unknown>;
}
