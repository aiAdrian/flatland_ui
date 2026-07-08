export type InfrastructureBuilderTool =
  | 'select'
  | 'track'
  | 'erase'
  | 'switch'
  | 'station'
  | 'agent-route'
  | 'agent-start'
  | 'agent-target'
  | 'random-agents';

export interface InfrastructureBuilderToolDefinition {
  id: InfrastructureBuilderTool;
  label: string;
  description: string;
}

export const MVP_TOOLS: InfrastructureBuilderToolDefinition[] = [
  { id: 'select', label: 'Select', description: 'Inspect cells and agents.' },
  { id: 'track', label: 'Track', description: 'Create a track cell.' },
  { id: 'erase', label: 'Erase', description: 'Remove track, station, and markers.' },
  { id: 'switch', label: 'Switch', description: 'Place an explicit switch cell.' },
  { id: 'station', label: 'Station', description: 'Place a station on a track cell.' },
  { id: 'agent-route', label: 'Agent Line', description: 'Drag from start to target for the selected train.' },
  { id: 'random-agents', label: 'Random Agents', description: 'Generate trains from valid tracks.' },
];
