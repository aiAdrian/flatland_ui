export type ToggleSplitOrientation = 'vertical' | 'horizontal';

export interface DesignerPanelSettings {
  toggleSplitOrientation?: ToggleSplitOrientation;
  splitOrientation?: ToggleSplitOrientation;
  [key: string]: unknown;
}

export type DesignerSelection =
  | { kind: 'design' }
  | { kind: 'row'; rowId: string }
  | { kind: 'column'; columnId: string }
  | { kind: 'panel'; columnId: string; panelId: string };

export interface DesignerPanel {
  id: string;
  type: string;
  title: string;
  expanded: boolean;
  collapsible: boolean;
  minHeight: number;
  height?: number | null;
  settings?: DesignerPanelSettings;
}

export interface DesignerColumn {
  id: string;
    rowId?: string;
  rowHeight?: number | null;
name: string;
  width: number;
  role: 'sidebar' | 'main' | 'custom';
  panels: DesignerPanel[];
}

export interface DesignerLayout {
  columns: DesignerColumn[];
}

export interface FlatlandDesign {
  id: string;
  name: string;
  sessionId?: string;
  scale: number;
  createdAt: string;
  updatedAt: string;
  layout: DesignerLayout;
}

export interface DesignerExport {
  version: 1;
  exportedAt: string;
  designs: FlatlandDesign[];
}
