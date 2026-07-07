export type PolicyName =
  | 'deadlock_avoidance'
  | 'shortest_path'
  | 'forward_only'
  | 'do_nothing'
  | 'random';

export interface PolicyInfo {
  id: PolicyName;
  label: string;
  description: string;
  is_default: boolean;
  show_in_ui: boolean;
  supports_scenarios: boolean;
}

export interface ScenarioPoliciesConfig {
  session_id: string;
  // Scenario policies
  enabled_ids: string[];
  available_ids: string[];
  // Runtime / toolbar policy control
  enabled_policy_ids?: string[];
  available_policy_ids?: string[];
}

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
  eta_to_depart: number | null;
  time_to_deadline: number | null;
  delay: number;
  is_visible: boolean;
  delay_color_intensity: number;
  cell_type: CellType;
  next_decision: NextDecision | null;
  override_action: ActionInt | null;
  malfunction_remaining: number;
  is_malfunctioning: boolean;
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
  infrastructure_scene_id?: string | null;
  infrastructure_scene_diagnostics?: InfrastructureSceneDiagnostics | null;
  elapsed_steps: number;
  max_episode_steps: number;
  agents: AgentDTO[];
  rail_grid: number[][];
  rail_tiles: RailTile[];
  episode_done: boolean;
  decision_cells?: DecisionCell[];
}

export interface InfrastructureSceneDiagnostics {
  scene_cell_count: number;
  scene_switch_count: number;
  scene_agent_count: number;
  routable_agent_count: number;
  rail_cell_count: number;
  rail_tile_count: number;
  rail_switch_tile_count: number;
  switch_cell_tiles?: Array<{
    id?: string;
    x: number;
    y: number;
    connections?: string[];
    switchFacing?: string;
    svg?: string;
    rot?: number;
    visual_kind?: string;
  }>;
  switch_cell_visual_counts?: {
    switch: number;
    crossing: number;
    track: number;
  };
  unknown_tile_count: number;
  unknown_tiles: RailTile[];
  mismatched_cell_count?: number;
  mismatched_cells?: Array<{
    id?: string;
    x: number;
    y: number;
    kind?: string;
    reason?: string;
    connections?: string[];
    expected?: number;
    actual?: number;
  }>;
}

export interface SessionInfo {
  id: string;
  width: number;
  height: number;
  num_agents: number;
  infrastructure_scene_id?: string | null;
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
