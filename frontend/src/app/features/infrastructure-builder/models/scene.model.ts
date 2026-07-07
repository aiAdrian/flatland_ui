import { InfrastructureAgent } from './agent.model';
import { GridConfig, TrackCell } from './grid.model';
import { InfrastructureGraph } from './graph.model';
import { ValidationResult } from './validation.model';

export interface Station {
  id: string;
  name: string;
  x: number;
  y: number;
  metadata?: Record<string, unknown>;
}

export interface InfrastructureScene {
  id: string;
  name: string;
  version: string;
  createdAt: string;
  updatedAt: string;
  grid: GridConfig;
  cells: TrackCell[];
  graph: InfrastructureGraph;
  stations: Station[];
  agents: InfrastructureAgent[];
  validation: ValidationResult;
  linkedLayoutId?: string;
  metadata?: Record<string, unknown>;
}

export interface InfrastructureSceneSummary {
  id: string;
  name: string;
  updatedAt: string;
  gridWidth: number;
  gridHeight: number;
  agentCount: number;
  stationCount: number;
  valid: boolean;
  linkedLayoutId?: string;
}

export interface InfrastructureSceneExport {
  version: 1;
  exportedAt: string;
  scenes: InfrastructureScene[];
}

export interface InfrastructureLayoutLink {
  sceneId: string;
  layoutId: string;
  name?: string;
  createdAt: string;
  updatedAt: string;
}
