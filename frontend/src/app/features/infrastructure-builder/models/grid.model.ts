export interface GridConfig {
  width: number;
  height: number;
  cellSizePx: number;
}

export type Direction = 'N' | 'E' | 'S' | 'W';

export interface GridPosition {
  x: number;
  y: number;
}

export type TrackCellKind =
  | 'empty'
  | 'track'
  | 'switch'
  | 'crossing'
  | 'dead-end'
  | 'station';

export interface TrackCell {
  id: string;
  x: number;
  y: number;
  kind: TrackCellKind;
  connections: Direction[];
  stationId?: string;
  metadata?: Record<string, unknown>;
}

export const DIRECTIONS: Direction[] = ['N', 'E', 'S', 'W'];

export const OPPOSITE_DIRECTION: Record<Direction, Direction> = {
  N: 'S',
  E: 'W',
  S: 'N',
  W: 'E',
};

export const DIRECTION_OFFSET: Record<Direction, GridPosition> = {
  N: { x: 0, y: -1 },
  E: { x: 1, y: 0 },
  S: { x: 0, y: 1 },
  W: { x: -1, y: 0 },
};

export function cellId(x: number, y: number): string {
  return `cell_${x}_${y}`;
}
