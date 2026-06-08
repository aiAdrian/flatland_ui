export type PolicyName = 'random' | 'shortest_path';

export type CellType = 'OUTSIDE' | 'FORWARD_ONLY' | 'MERGING' | 'SWITCH' | 'DONE' | 'UNKNOWN';

export type ActionInt = 0 | 1 | 2 | 3 | 4;

export interface DecisionOption {
  action: ActionInt;
  action_name: string;
  label: string;
  target_position: [number, number];
}

export interface NextDecision {
  path: [number, number][];
  decision_position: [number, number];
  decision_direction: number;
  cell_type: 'SWITCH' | 'MERGING';
  options: DecisionOption[];
}

export interface AgentDTO {
  handle: number;
  position: [number, number] | null;
  direction: number | null;
  initial_position: [number, number] | null;
  initial_direction: number | null;
  target: [number, number];
  state: string;
  speed: number;
  earliest_departure: number | null;
  latest_arrival: number | null;
  cell_type: CellType;
  next_decision: NextDecision | null;
  override_action: ActionInt | null;
}

export interface RailTile {
  r: number;
  c: number;
  rot: number;
  svg: string;
  binary?: number;
  hex?: string;
  description?: string;
}

export interface SessionState {
  width: number;
  height: number;
  num_agents: number;
  elapsed_steps: number;
  max_episode_steps: number;
  agents: AgentDTO[];
  rail_grid: number[][];
  rail_tiles: RailTile[];
  episode_done: boolean;
  decision_cells?: DecisionCell[];
}

export interface SessionInfo {
  id: string;
  width: number;
  height: number;
  num_agents: number;
}

export interface StepResponse {
  session_id: string;
  elapsed_steps: number;
  rewards?: Record<string, unknown>;
  dones?: Record<string, unknown>;
  all_done?: boolean;
  episode_done?: boolean;
  message?: string;
}

export interface PlayRequest {
  speed?: number;
  policy?: PolicyName;
}

export interface DecisionCell {
  r: number;
  c: number;
  kind: 'switch' | 'merge';
  directions?: number[]; // 0=N, 1=E, 2=S, 3=W (incoming)
  switch_exits?: number[];   // for SWITCH cells: directions a train can leave by
}
