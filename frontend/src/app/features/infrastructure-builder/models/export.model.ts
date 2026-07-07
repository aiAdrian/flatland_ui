export type InfrastructureExportFormat = 'json' | 'mermaid' | 'yaml' | 'dot';

export interface InfrastructureExportResult {
  format: InfrastructureExportFormat;
  content: string;
}
