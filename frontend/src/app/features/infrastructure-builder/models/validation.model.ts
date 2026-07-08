export interface ValidationResult {
  valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
}

export interface ValidationIssue {
  id: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
  cellId?: string;
  nodeId?: string;
  edgeId?: string;
  agentId?: string;
}

export const EMPTY_VALIDATION_RESULT: ValidationResult = {
  valid: true,
  errors: [],
  warnings: [],
};
