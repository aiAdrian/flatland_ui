import { CommonModule } from '@angular/common';
import { Component, HostListener, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DesignerColumn,
  DesignerPanel,
  DesignerSelection,
  FlatlandDesign,
} from './layout-designer.models';
import { DesignStorageService } from './design-storage.service';
import { SessionStore } from '../../core/session.store';
import { PanelShellComponent } from '../layout/components/panel-shell/panel-shell.component';
import { PanelInstance } from '../../core/layout';

interface PaletteItem {
  type: string;
  title: string;
  minHeight: number;
}

type DragPayload =
  | { source: 'palette'; type: string; title: string; minHeight: number }
  | { source: 'layout'; columnId: string; panelId: string }
  | { source: 'row'; rowId: string }
  | { source: 'column'; columnId: string };

@Component({
  selector: 'app-layout-designer',
  standalone: true,
  imports: [CommonModule, FormsModule, PanelShellComponent],
  templateUrl: './layout-designer.component.html',
  styleUrls: ['./layout-designer.component.scss'],
})
export class LayoutDesignerComponent {

  constructor() {
    queueMicrotask(() => { this.syncActiveSession(); this.runLivePreview(); });
  }
  private readonly storage = inject(DesignStorageService);
  private readonly sessionStore = inject(SessionStore);

  designs = this.storage.list();
  design: FlatlandDesign = this.loadInitialDesign();

  selection: DesignerSelection = { kind: 'design' };

  palette: PaletteItem[] = [
    { type: 'toggle-view', title: 'Toggle View', minHeight: 520 },
    { type: 'toolbar', title: 'Toolbar', minHeight: 74 },
    { type: 'layer-visibility', title: 'Layer Visibility', minHeight: 80 },
    { type: 'flatland-map', title: 'Flatland Map', minHeight: 320 },
    { type: 'marey', title: 'Graphical Timetable', minHeight: 260 },
    { type: 'agents-list', title: 'Agents List', minHeight: 180 },
    { type: 'agent-inspector', title: 'Agent Inspector', minHeight: 180 },
    { type: 'goal-achievement', title: 'Goal Achievement', minHeight: 140 },
    { type: 'impact', title: 'Impact', minHeight: 160 },
    { type: 'timeline', title: 'Timeline', minHeight: 130 },
    { type: 'validation', title: 'Validation', minHeight: 130 },
    { type: 'cell-inspector', title: 'Cell Inspector', minHeight: 160 },
  ];

  livePreviewSteps = 10;
  livePreviewRunning = false;
  livePreviewConnected = false;
  livePreviewLastRun: string | null = null;
  livePreviewLog: string[] = [];
  previewRenderMode: 'live' | 'wireframe' = 'live';

  designerFeedbackMessage = '';
  designerFeedbackTone: 'success' | 'info' | 'warn' = 'info';
  buttonFeedbackId: string | null = null;
  private designerFeedbackTimer: any = null;

  isDirty = false;
  designerFooterStatusMessage = 'Ready';
  designerFooterStatusTone: 'saved' | 'dirty' | 'info' | 'warn' = 'info';


  private undoStack: FlatlandDesign[] = [];
  private readonly maxUndoSteps = 50;
  private layoutDropHandled = false;


  private resizing: any = null;


  get activeSessionId(): string {
    const session = this.sessionStore.session() as any;

    return (
      session?.id ??
      session?.sessionId ??
      session?.session_id ??
      session?.uuid ??
      ''
    );
  }

  get hasActiveSession(): boolean {
    return !!this.activeSessionId;
  }

  syncActiveSession(): void {
    const id = this.activeSessionId;

    if (id && this.design.sessionId !== id) {
      this.design.sessionId = id;
      this.touch();
    }
  }

  get selectedColumn(): DesignerColumn | undefined {
    if (this.selection.kind === 'column') {
      return this.findColumn(this.selection.columnId);
    }

    if (this.selection.kind === 'panel') {
      return this.findColumn(this.selection.columnId);
    }

    return undefined;
  }

  get selectedPanel(): DesignerPanel | undefined {
    if (this.selection.kind !== 'panel') {
      return undefined;
    }

    return this.findPanel(this.selection.columnId, this.selection.panelId);
  }

  get layoutRows(): DesignerColumn[][] {
    const columns = this.design?.layout?.columns ?? [];
    const rows: DesignerColumn[][] = [];
    const rowOrder: string[] = [];
    const rowMap = new Map<string, DesignerColumn[]>();

    for (const [index, column] of columns.entries()) {
      const rowId = column.rowId || `row-${Math.floor(index / 3) + 1}`;
      column.rowId = rowId;

      if (!rowMap.has(rowId)) {
        rowMap.set(rowId, []);
        rowOrder.push(rowId);
      }

      rowMap.get(rowId)!.push(column);
    }

    for (const rowId of rowOrder) {
      rows.push(rowMap.get(rowId)!);
    }

    return rows;
  }

  get layoutRowCount(): number {
    return this.layoutRows.length;
  }

  get maxColumnsPerRow(): number {
    return this.layoutRows.reduce((max, row) => Math.max(max, row.length), 0);
  }

  get selectedRowId(): string | null {
    if (this.selection.kind === 'row') {
      return this.selection.rowId;
    }

    if (this.selection.kind === 'column' || this.selection.kind === 'panel') {
      const column = this.findColumn(this.selection.columnId);
      return column?.rowId ?? null;
    }

    return null;
  }

  get canvasWidth(): number {
    return this.layoutRows.reduce(
      (max, row) => Math.max(max, row.reduce((sum, column) => sum + column.width, 0)),
      0,
    );
  }

  private rowIdForColumn(column: DesignerColumn): string {
    if (column.rowId) {
      return column.rowId;
    }

    const index = this.design.layout.columns.findIndex((candidate) => candidate.id === column.id);
    const rowId = `row-${Math.floor(Math.max(0, index) / 3) + 1}`;
    column.rowId = rowId;
    return rowId;
  }

  rowIdForRow(row: DesignerColumn[]): string {
    return row?.[0] ? this.rowIdForColumn(row[0]) : `row-${Date.now()}`;
  }

  private selectedOrLastRowId(): string {
    if (this.selection.kind === 'row') {
      return this.selection.rowId;
    }

    if (this.selection.kind === 'column' || this.selection.kind === 'panel') {
      const column = this.findColumn(this.selection.columnId);
      if (column) {
        return this.rowIdForColumn(column);
      }
    }

    const lastRow = this.layoutRows[this.layoutRows.length - 1];
    return lastRow?.[0] ? this.rowIdForRow(lastRow) : `row-${Date.now()}`;
  }

  private columnsInRow(rowId: string): DesignerColumn[] {
    return this.design.layout.columns.filter((column) => this.rowIdForColumn(column) === rowId);
  }

  private distributeWidthAcrossRow(rowId: string, targetWidth?: number): void {
    const columns = this.columnsInRow(rowId);
    if (!columns.length) {
      return;
    }

    const width = targetWidth ?? columns.reduce((sum, column) => sum + column.width, 0);
    const base = Math.max(160, Math.floor(width / columns.length));
    let rest = Math.max(0, width - base * columns.length);

    for (const column of columns) {
      column.width = base + (rest > 0 ? 1 : 0);
      rest = Math.max(0, rest - 1);
    }
  }

  rowStyle(row: DesignerColumn[]): Record<string, string> {
    const h = row?.[0]?.rowHeight;
    return h ? { minHeight: `${h}px`, height: `${h}px` } : {};
  }









  selectDesign(): void {
    this.selection = { kind: 'design' };
    this.runLivePreview();
  }

  selectRow(row: DesignerColumn[], event?: Event): void {
    event?.stopPropagation();

    if (!row?.length) {
      return;
    }

    this.selection = { kind: 'row', rowId: this.rowIdForRow(row) };
  }

  selectColumn(column: DesignerColumn, event?: Event): void {
    event?.stopPropagation();
    this.selection = { kind: 'column', columnId: column.id };
  }

  selectPanel(column: DesignerColumn, panel: DesignerPanel, event: Event): void {
    event.stopPropagation();
    this.selection = { kind: 'panel', columnId: column.id, panelId: panel.id };
  }

  addColumn(): void {
    const rowId = this.selectedOrLastRowId();
    const rowColumns = this.columnsInRow(rowId);
    const previousRowWidth = rowColumns.reduce((sum, column) => sum + column.width, 0) || 1320;
    const index = rowColumns.length + 1;

    const col: DesignerColumn = {
      id: `column_${Date.now()}`,
      rowId,
      name: `Column ${index}`,
      width: 280,
      role: 'custom',
      panels: [],
    };

    this.pushUndoState();

    const insertAfterIndex = this.design.layout.columns.reduce((lastIndex, column, currentIndex) => (
      this.rowIdForColumn(column) === rowId ? currentIndex : lastIndex
    ), -1);

    if (insertAfterIndex >= 0) {
      this.design.layout.columns.splice(insertAfterIndex + 1, 0, col);
    } else {
      this.design.layout.columns.push(col);
    }

    this.distributeWidthAcrossRow(rowId, previousRowWidth);
    this.selection = { kind: 'column', columnId: col.id };
    this.touch();
  }



  addRow(): void {
    const sourceRowId = this.selectedOrLastRowId();
    const sourceColumns = this.columnsInRow(sourceRowId);
    const newRowId = `row-${Date.now()}`;
    const newRowIndex = this.layoutRows.length + 1;
    const template = sourceColumns.length ? sourceColumns : [
      { width: 280 },
      { width: 720 },
      { width: 320 },
    ];

    const newColumns: DesignerColumn[] = template.map((source: any, index: number) => ({
      id: `column_${Date.now()}_${index}`,
      rowId: newRowId,
      rowHeight: null,
      name: `Row ${newRowIndex} · Column ${index + 1}`,
      width: Math.max(160, source.width ?? 280),
      role: 'custom',
      panels: [],
    }));

    this.pushUndoState();

    const insertAfterIndex = this.design.layout.columns.reduce((lastIndex, column, currentIndex) => (
      this.rowIdForColumn(column) === sourceRowId ? currentIndex : lastIndex
    ), -1);

    if (insertAfterIndex >= 0) {
      this.design.layout.columns.splice(insertAfterIndex + 1, 0, ...newColumns);
    } else {
      this.design.layout.columns.push(...newColumns);
    }

    this.selection = { kind: 'row', rowId: newRowId };
    this.touch();
  }






  addRowBelow(sourceRowId?: string): void {
    const selectedRowId = sourceRowId || this.selectedOrLastRowId();
    const sourceColumns = this.columnsInRow(selectedRowId);
    const newRowId = `row-${Date.now()}`;
    const newRowIndex = this.layoutRows.length + 1;
    const columnsToCopy = sourceColumns.length ? sourceColumns : [
      { width: 280 },
      { width: 720 },
      { width: 320 },
    ];

    const newColumns: DesignerColumn[] = columnsToCopy.map((sourceColumn: any, index: number) => ({
      id: `column_${Date.now()}_${index}`,
      rowId: newRowId,
      rowHeight: sourceColumn.rowHeight ?? null,
      name: `Row ${newRowIndex} · Column ${index + 1}`,
      width: Math.max(160, sourceColumn.width ?? 280),
      role: 'custom',
      panels: [],
    }));

    this.pushUndoState();

    const insertAfterIndex = this.design.layout.columns.reduce((lastIndex, column, currentIndex) => (
      this.rowIdForColumn(column) === selectedRowId ? currentIndex : lastIndex
    ), -1);

    if (insertAfterIndex >= 0) {
      this.design.layout.columns.splice(insertAfterIndex + 1, 0, ...newColumns);
    } else {
      this.design.layout.columns.push(...newColumns);
    }

    this.selection = { kind: 'row', rowId: newRowId };
    this.touch();
  }







  removeSelectedRow(): void {
    if (this.selection.kind !== 'row') {
      return;
    }

    this.removeRow(this.selection.rowId);
  }

  removeRow(rowId: string): void {
    const rowColumns = this.columnsInRow(rowId);

    if (!rowColumns.length) {
      return;
    }

    this.pushUndoState();

    this.design.layout.columns = this.design.layout.columns.filter(
      (column) => this.rowIdForColumn(column) !== rowId,
    );

    const firstRemainingRow = this.layoutRows[0];

    this.selection = firstRemainingRow?.[0]
      ? { kind: 'row', rowId: this.rowIdForRow(firstRemainingRow) }
      : { kind: 'design' };

    this.touch();
  }

  removeSelectedColumn(): void {
    if (this.selection.kind !== 'column') {
      return;
    }

    const col = this.findColumn(this.selection.columnId);
    if (!col) {
      return;
    }

    const rowId = this.rowIdForColumn(col);
    const widthBefore = this.columnsInRow(rowId).reduce((sum, column) => sum + column.width, 0);

    this.pushUndoState();
    this.design.layout.columns = this.design.layout.columns.filter((column) => column.id !== col.id);

    const remaining = this.columnsInRow(rowId);
    if (remaining.length) {
      this.distributeWidthAcrossRow(rowId, widthBefore);
      this.selection = { kind: 'row', rowId };
    } else {
      this.selection = { kind: 'design' };
    }

    this.touch();
  }




  removeSelectedPanel(): void {
    if (this.selection.kind !== 'panel') {
      return;
    }

    const column = this.findColumn(this.selection.columnId);
    if (!column) {
      return;
    }

    const panelId = this.selection.panelId;

    this.pushUndoState();

    column.panels = column.panels.filter((p) => p.id !== panelId);
    this.selection = { kind: 'design' };
    this.touch();
  }

  duplicateSelectedPanel(): void {
    const panel = this.selectedPanel;
    const column = this.selectedColumn;
    if (!panel || !column) {
      return;
    }

    column.panels.push({
      ...panel,
      id: `${panel.type}_${Math.random().toString(36).slice(2, 9)}`,
      title: `${panel.title} Copy`,
    });

    this.touch();
  }

  save(): void {
    this.storage.save(this.design);
    this.designs = this.storage.list();
  }

  saveAs(): void {
    const name = prompt('Layout name', `${this.design.name} Copy`);
    if (!name) {
      return;
    }

    this.design = {
      ...structuredClone(this.design),
      id: `design_${Date.now()}`,
      name,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    this.save();
  }

  deleteDesign(): void {
    this.storage.delete(this.design.id);
    this.designs = this.storage.list();
    this.design = this.loadInitialDesign();
    this.selection = { kind: 'design' };
    this.isDirty = false;
    this.designerFooterStatusMessage = 'Layout deleted';
    this.designerFooterStatusTone = 'info';
    this.runLivePreview();
  }


  loadDesign(id: string): void {
    const found = this.storage.get(id);
    if (!found) {
      return;
    }

    this.design = structuredClone(found);
    this.normalizeDesign(this.design);
    this.storage.setActive(id);
    this.selection = { kind: 'design' };
    this.runLivePreview();
  }

  exportJson(): void {
    const blob = new Blob([JSON.stringify(this.storage.exportAll(), null, 2)], {
      type: 'application/json',
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'flatland-designs.json';
    a.click();
    URL.revokeObjectURL(url);
  }

  async importJson(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];

    if (!file) {
      return;
    }

    const text = await file.text();
    const payload = JSON.parse(text);
    const count = this.storage.importMany(payload);

    this.designs = this.storage.list();

    if (count > 0 && this.designs.length) {
      this.design = structuredClone(this.designs[this.designs.length - 1]);
      this.normalizeDesign(this.design);
      this.runLivePreview();
    }

    input.value = '';
    alert(`Imported ${count} design(s).`);
  }

  runSession(): void {
    this.save();
    window.location.href = '/';
  }

  dragPalette(item: PaletteItem, event: DragEvent): void {
    const payload: DragPayload = {
      source: 'palette',
      type: item.type,
      title: item.title,
      minHeight: item.minHeight,
    };

    event.dataTransfer?.setData('application/json', JSON.stringify(payload));
    event.dataTransfer?.setData('text/plain', item.type);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'copy';
    }
  }

  dragPanel(column: DesignerColumn, panel: DesignerPanel, event: DragEvent): void {
    event.stopPropagation();
    this.layoutDropHandled = false;

    const payload: DragPayload = {
      source: 'layout',
      columnId: column.id,
      panelId: panel.id,
    };

    event.dataTransfer?.setData('application/json', JSON.stringify(payload));
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
    }
  }

  allowDrop(event: DragEvent): void {
    event.preventDefault();
  }



















  dragRow(row: DesignerColumn[], event: DragEvent): void {
    event.stopPropagation();

    const rowId = this.rowIdForRow(row);

    event.dataTransfer?.setData(
      'application/json',
      JSON.stringify({ source: 'row', rowId } satisfies DragPayload),
    );

    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
    }
  }

  dropOnRow(targetRow: DesignerColumn[], event: DragEvent): void {
    const raw = event.dataTransfer?.getData('application/json');

    if (!raw) {
      return;
    }

    let payload: DragPayload;

    try {
      payload = JSON.parse(raw) as DragPayload;
    } catch {
      return;
    }

    if (payload.source !== 'row' && payload.source !== 'column') {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const targetRowId = this.rowIdForRow(targetRow);

    if (payload.source === 'row') {
      if (payload.rowId === targetRowId) {
        return;
      }

      this.pushUndoState();
      this.moveRow(payload.rowId, targetRowId);
      this.selection = { kind: 'row', rowId: payload.rowId };
      this.touch();
      return;
    }

    if (payload.source === 'column') {
      this.pushUndoState();
      this.appendColumnToRow(payload.columnId, targetRowId);
      this.selection = { kind: 'column', columnId: payload.columnId };
      this.touch();
    }
  }

  private moveRow(sourceRowId: string, targetRowId: string): void {
    const rows = this.layoutRows.map((row) => ({
      rowId: this.rowIdForRow(row),
      columns: row,
    }));

    const sourceIndex = rows.findIndex((row) => row.rowId === sourceRowId);
    const targetIndex = rows.findIndex((row) => row.rowId === targetRowId);

    if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) {
      return;
    }

    const [sourceRow] = rows.splice(sourceIndex, 1);
    const insertIndex = sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;

    rows.splice(insertIndex, 0, sourceRow);

    this.design.layout.columns = rows.flatMap((row) => row.columns);
  }

  dragColumn(column: DesignerColumn, event: DragEvent): void {
    event.stopPropagation();

    event.dataTransfer?.setData(
      'application/json',
      JSON.stringify({ source: 'column', columnId: column.id } satisfies DragPayload),
    );

    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
    }
  }

  private moveColumnBefore(sourceColumnId: string, targetColumnId: string): void {
    if (sourceColumnId === targetColumnId) {
      return;
    }

    const sourceColumn = this.findColumn(sourceColumnId);
    const targetColumn = this.findColumn(targetColumnId);

    if (!sourceColumn || !targetColumn) {
      return;
    }

    const sourceRowId = this.rowIdForColumn(sourceColumn);
    const targetRowId = this.rowIdForColumn(targetColumn);
    const sourceRowWidthBefore = this.columnsInRow(sourceRowId).reduce((sum, column) => sum + column.width, 0);
    const targetRowWidthBefore = this.columnsInRow(targetRowId).reduce((sum, column) => sum + column.width, 0);

    this.design.layout.columns = this.design.layout.columns.filter((column) => column.id !== sourceColumnId);
    sourceColumn.rowId = targetRowId;

    const targetIndex = this.design.layout.columns.findIndex((column) => column.id === targetColumnId);

    if (targetIndex >= 0) {
      this.design.layout.columns.splice(targetIndex, 0, sourceColumn);
    } else {
      this.design.layout.columns.push(sourceColumn);
    }

    if (sourceRowId === targetRowId) {
      return;
    }

    if (this.columnsInRow(sourceRowId).length) {
      this.distributeWidthAcrossRow(sourceRowId, sourceRowWidthBefore);
    }

    this.distributeWidthAcrossRow(targetRowId, targetRowWidthBefore);
  }

  private appendColumnToRow(sourceColumnId: string, targetRowId: string): void {
    const sourceColumn = this.findColumn(sourceColumnId);

    if (!sourceColumn) {
      return;
    }

    const sourceRowId = this.rowIdForColumn(sourceColumn);

    if (sourceRowId === targetRowId) {
      const columns = this.design.layout.columns.filter((column) => column.id !== sourceColumnId);
      const lastTargetIndex = columns.reduce((lastIndex, column, index) => (
        this.rowIdForColumn(column) === targetRowId ? index : lastIndex
      ), -1);

      sourceColumn.rowId = targetRowId;

      if (lastTargetIndex >= 0) {
        columns.splice(lastTargetIndex + 1, 0, sourceColumn);
      } else {
        columns.push(sourceColumn);
      }

      this.design.layout.columns = columns;
      return;
    }

    const sourceRowWidthBefore = this.columnsInRow(sourceRowId).reduce((sum, column) => sum + column.width, 0);
    const targetRowWidthBefore = this.columnsInRow(targetRowId).reduce((sum, column) => sum + column.width, 0);

    this.design.layout.columns = this.design.layout.columns.filter((column) => column.id !== sourceColumnId);
    sourceColumn.rowId = targetRowId;

    const insertAfterIndex = this.design.layout.columns.reduce((lastIndex, column, index) => (
      this.rowIdForColumn(column) === targetRowId ? index : lastIndex
    ), -1);

    if (insertAfterIndex >= 0) {
      this.design.layout.columns.splice(insertAfterIndex + 1, 0, sourceColumn);
    } else {
      this.design.layout.columns.push(sourceColumn);
    }

    if (this.columnsInRow(sourceRowId).length) {
      this.distributeWidthAcrossRow(sourceRowId, sourceRowWidthBefore);
    }

    this.distributeWidthAcrossRow(targetRowId, targetRowWidthBefore);
  }

  dropOnColumn(targetColumn: DesignerColumn, event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.layoutDropHandled = true;

    const raw = event.dataTransfer?.getData('application/json');

    if (!raw) {
      return;
    }

    let payload: DragPayload;

    try {
      payload = JSON.parse(raw) as DragPayload;
    } catch {
      return;
    }

    if (payload.source === 'row') {
      // Rows are moved by dropOnRow().
      return;
    }

    if (payload.source === 'column') {
      this.pushUndoState();
      this.moveColumnBefore(payload.columnId, targetColumn.id);
      this.selection = { kind: 'column', columnId: payload.columnId };
      this.touch();
      return;
    }

    if (payload.source === 'palette') {
      const panel: DesignerPanel = {
        id: `${payload.type}_${Math.random().toString(36).slice(2, 9)}`,
        type: payload.type,
        title: payload.title,
        expanded: true,
        collapsible: true,
        minHeight: payload.minHeight,
        height: null,
      };

      this.pushUndoState();

      targetColumn.panels.push(panel);
      this.selection = { kind: 'panel', columnId: targetColumn.id, panelId: panel.id };
      this.touch();
      return;
    }

    const sourceColumn = this.findColumn(payload.columnId);
    const panel = this.findPanel(payload.columnId, payload.panelId);

    if (!sourceColumn || !panel) {
      return;
    }

    this.pushUndoState();

    sourceColumn.panels = sourceColumn.panels.filter((p) => p.id !== panel.id);
    targetColumn.panels.push(panel);

    this.selection = { kind: 'panel', columnId: targetColumn.id, panelId: panel.id };
    this.touch();
  }







  dragPanelEnd(column: DesignerColumn, panel: DesignerPanel, event: DragEvent): void {
    const droppedNowhere = !this.layoutDropHandled && event.dataTransfer?.dropEffect === 'none';

    if (droppedNowhere) {
    this.pushUndoState();

      column.panels = column.panels.filter((p) => p.id !== panel.id);

      if (this.selection.kind === 'panel' && this.selection.panelId === panel.id) {
        this.selection = { kind: 'design' };
      }

      this.touch();
      this.runLivePreview();
    }

    this.layoutDropHandled = false;
  }

  toRuntimePanel(column: DesignerColumn, panel: DesignerPanel): PanelInstance {
    return {
      id: `designer-preview-${panel.id}`,
      type: this.toRuntimePanelType(panel.type),
      title: panel.title,
      zone: column.id,
      order: column.panels.findIndex((p) => p.id === panel.id),
      collapsed: !panel.expanded,
      hidden: false,
      sizeMode: column.role === 'main' ? 'fill' : 'auto',
    } as PanelInstance;
  }

  private toRuntimePanelType(type: string): string {
    if (type === 'agents-list') {
      return 'agents';
    }

    if (type === 'flatland-map') {
      return 'flatland-map';
    }

    if (type === 'marey') {
      return 'marey';
    }

    return type;
  }
startColumnResize(column: DesignerColumn, event: PointerEvent): void {
    event.preventDefault();
    event.stopPropagation();

    this.pushUndoState();

    this.resizing = {
      kind: 'column',
      columnId: column.id,
      startX: event.clientX,
      startWidth: column.width,
    };
  }

  startPanelResize(column: DesignerColumn, panel: DesignerPanel, event: PointerEvent): void {
    event.preventDefault();
    event.stopPropagation();

    this.pushUndoState();

    this.resizing = {
      kind: 'panel',
      columnId: column.id,
      panelId: panel.id,
      startY: event.clientY,
      startHeight: panel.height ?? panel.minHeight,
    };
  }

  @HostListener('window:pointermove', ['$event'])
  @HostListener('window:pointermove', ['$event'])
  @HostListener('window:pointermove', ['$event'])
  onPointerMove(event: PointerEvent): void {
    if (!this.resizing) {
      return;
    }

    if (this.resizing.kind === 'column') {
      const column = this.findColumn(this.resizing.columnId);
      if (!column) {
        return;
      }

      column.width = Math.max(160, this.resizing.startWidth + event.clientX - this.resizing.startX);
      this.touch();
      return;
    }

    if (this.resizing.kind === 'panel') {
      const panel = this.findPanel(this.resizing.columnId, this.resizing.panelId);
      if (!panel) {
        return;
      }

      panel.height = Math.max(panel.minHeight, this.resizing.startHeight + event.clientY - this.resizing.startY);
      this.touch();
    }
  }



  @HostListener('window:pointerup')
  onPointerUp(): void {
    this.resizing = null;
  }



  private pushUndoState(): void {
    this.undoStack.push(structuredClone(this.design));

    if (this.undoStack.length > this.maxUndoSteps) {
      this.undoStack.shift();
    }
  }

  undoLastLayoutChange(): void {
    const previous = this.undoStack.pop();

    if (!previous) {
      const feedback = (this as any).showDesignerFeedback;

      if (typeof feedback === 'function') {
        feedback.call(this, 'Nothing to undo', 'info', 'undo');
      }

      return;
    }

    this.design = previous;
    this.selection = { kind: 'design' };
    this.runLivePreview();

    const feedback = (this as any).showDesignerFeedback;

    if (typeof feedback === 'function') {
      feedback.call(this, 'Layout change undone', 'success', 'undo');
    }
  }


  deleteSelected(): void {
    if (this.selection.kind === 'panel') {
      this.removeSelectedPanel();
      this.runLivePreview();
      return;
    }

    if (this.selection.kind === 'column') {
      this.removeSelectedColumn();
      this.runLivePreview();
    }
  }

  @HostListener('window:keydown', ['$event'])
  onKeyDown(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();

      if (
        tag === 'input' ||
        tag === 'textarea' ||
        tag === 'select' ||
        target?.isContentEditable
      ) {
        return;
      }

      event.preventDefault();
      this.undoLastLayoutChange();
      return;
    }

    const target = event.target as HTMLElement | null;
    const tag = target?.tagName?.toLowerCase();

    if (
      tag === 'input' ||
      tag === 'textarea' ||
      tag === 'select' ||
      target?.isContentEditable
    ) {
      return;
    }

    if ((event.key === 'Delete' || event.key === 'Backspace') && this.selection.kind !== 'design') {
      event.preventDefault();
      this.deleteSelected();
    }
  }


  onSessionChanged(): void {
    this.touch();
    this.runLivePreview();
  }







  private showDesignerFeedback(
    message: string,
    tone: 'success' | 'info' | 'warn' = 'success',
    actionId: string | null = null,
  ): void {
    this.designerFeedbackMessage = message;
    this.designerFeedbackTone = tone;
    this.buttonFeedbackId = actionId;

    if (this.designerFeedbackTimer) {
      window.clearTimeout(this.designerFeedbackTimer);
    }

    this.designerFeedbackTimer = window.setTimeout(() => {
      this.designerFeedbackMessage = '';
      this.buttonFeedbackId = null;
      this.designerFeedbackTimer = null;
    }, 1800);
  }

  private callDesignerMethod(names: string[], args: any[] = []): void {
    for (const name of names) {
      const fn = (this as any)[name];

      if (typeof fn === 'function') {
        fn.apply(this, args);
        return;
      }
    }
  }



  private cloneDesignerDesign(design: FlatlandDesign): FlatlandDesign {
    return typeof structuredClone === 'function'
      ? structuredClone(design)
      : JSON.parse(JSON.stringify(design));
  }

  private readDesignerStorage(key: string): string | null {
    try {
      return typeof localStorage === 'undefined' ? null : localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  private writeDesignerStorage(key: string, value: string): void {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(key, value);
      }
    } catch {
      // Ignore local storage errors.
    }
  }

  private removeDesignerStorage(key: string): void {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem(key);
      }
    } catch {
      // Ignore local storage errors.
    }
  }

  private setDesignerFooterStatus(
    message: string,
    tone: 'saved' | 'dirty' | 'info' | 'warn' = 'info',
  ): void {
    this.designerFooterStatusMessage = message;
    this.designerFooterStatusTone = tone;
  }

  private markDesignerDirty(message = 'Unsaved changes'): void {
    this.isDirty = true;
    this.setDesignerFooterStatus(message, 'dirty');
  }

  private markDesignerSaved(message = 'Layout saved'): void {
    this.isDirty = false;
    this.setDesignerFooterStatus(message, 'saved');
  }



  refreshDesignerLayoutList(): void {
    const next = this.loadDesignerLayoutsFromStorage();
    const current = JSON.stringify(this.designs ?? []);
    const incoming = JSON.stringify(next);

    if (current !== incoming) {
      this.designs = next;
    }
  }



  designerLayoutOptions(): FlatlandDesign[] {
    return this.designs;
  }

  private loadDesignerLayoutsFromStorage(): FlatlandDesign[] {
    const keys = [
      'flatland.designer.designs.v1',
      'flatland.layoutDesigner.designs.v1',
      'flatland.layouts.v1',
    ];

    const result: FlatlandDesign[] = [];
    const seen = new Set<string>();

    for (const key of keys) {
      try {
        const raw = this.readDesignerStorage(key);
        const parsed = raw ? JSON.parse(raw) : [];

        if (!Array.isArray(parsed)) {
          continue;
        }

        for (const item of parsed) {
          if (!item?.id || !item?.layout?.columns || seen.has(String(item.id))) {
            continue;
          }

          seen.add(String(item.id));
          result.push(item as FlatlandDesign);
        }
      } catch {
        // Ignore invalid storage entries.
      }
    }

    return result.sort((a, b) =>
      String(a.name || '').localeCompare(String(b.name || ''))
    );
  }


  private persistCurrentDesignerLayout(): void {
    const now = new Date().toISOString();
    const current = this.cloneDesignerDesign({
      ...this.design,
      updatedAt: now,
    });

    const layouts = this.loadDesignerLayoutsFromStorage();
    const index = layouts.findIndex((layout) => layout.id === current.id);

    if (index >= 0) {
      layouts[index] = current;
    } else {
      layouts.push(current);
    }

    layouts.sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')));

    this.design = current;
    this.designs = layouts;

    this.writeDesignerStorage('flatland.designer.designs.v1', JSON.stringify(layouts));
    this.writeDesignerStorage('flatland.designer.active.v1', current.id);
  }




  saveWithFeedback(): void {
    this.persistCurrentDesignerLayout();
    this.refreshDesignerLayoutList();

    const originalSave = (this as any).save;
    if (typeof originalSave === 'function') {
      try {
        originalSave.call(this);
      } catch {
        // Local persistence above is authoritative for designer user layouts.
      }
    }

    this.markDesignerSaved('Layout saved');

    const feedback = (this as any).showDesignerFeedback;
    if (typeof feedback === 'function') {
      feedback.call(this, 'Layout saved', 'success', 'save');
    }
  }


  saveAsWithPrompt(): void {
    const proposed = `${this.design.name || 'Layout'} Copy`;
    const name = window.prompt('Save layout as…', proposed);

    if (name === null) {
      this.setDesignerFooterStatus('Save As cancelled', 'info');
      return;
    }

    const cleanName = name.trim();

    if (!cleanName) {
      this.setDesignerFooterStatus('Save As cancelled: name is empty', 'warn');
      return;
    }

    const now = new Date().toISOString();
    const suffix = Date.now().toString(36);

    this.design = this.cloneDesignerDesign({
      ...this.design,
      id: `layout-${suffix}`,
      name: cleanName,
      createdAt: now,
      updatedAt: now,
    });

    this.selection = { kind: 'design' };
    this.persistCurrentDesignerLayout();
    this.refreshDesignerLayoutList();
    this.runLivePreview();
    this.markDesignerSaved(`Layout saved as “${cleanName}”`);

    const feedback = (this as any).showDesignerFeedback;
    if (typeof feedback === 'function') {
      feedback.call(this, `Saved as “${cleanName}”`, 'success', 'save-as');
    }
  }

  renameCurrentLayout(): void {
    const name = window.prompt('Rename layout', this.design.name || 'Layout');

    if (name === null) {
      this.setDesignerFooterStatus('Rename cancelled', 'info');
      return;
    }

    const cleanName = name.trim();

    if (!cleanName) {
      this.setDesignerFooterStatus('Rename cancelled: name is empty', 'warn');
      return;
    }

    this.design = {
      ...this.design,
      name: cleanName,
      updatedAt: new Date().toISOString(),
    };

    this.persistCurrentDesignerLayout();
    this.refreshDesignerLayoutList();
    this.markDesignerSaved(`Layout renamed to “${cleanName}”`);

    const feedback = (this as any).showDesignerFeedback;
    if (typeof feedback === 'function') {
      feedback.call(this, `Renamed to “${cleanName}”`, 'success', 'rename');
    }
  }

  loadDesignerLayout(id: string): void {
    if (!id || id === this.design.id) {
      return;
    }

    if (this.isDirty) {
      const confirmed = window.confirm('Discard unsaved changes and load another layout?');

      if (!confirmed) {
        return;
      }
    }

    const layout = this.loadDesignerLayoutsFromStorage().find((item) => item.id === id);

    if (!layout) {
      this.setDesignerFooterStatus('Layout not found', 'warn');
      return;
    }

    this.design = this.cloneDesignerDesign(layout);
    this.selection = { kind: 'design' };
    this.writeDesignerStorage('flatland.designer.active.v1', this.design.id);
    this.runLivePreview();
    this.markDesignerSaved(`Loaded “${this.design.name}”`);

    const feedback = (this as any).showDesignerFeedback;
    if (typeof feedback === 'function') {
      feedback.call(this, `Loaded “${this.design.name}”`, 'success', 'load');
    }
  }

  clearAllUserLayoutsClean(): void {
    const confirmed = window.confirm(
      'Delete all saved user layouts? The hardcoded default layout will stay available.'
    );

    if (!confirmed) {
      this.setDesignerFooterStatus('Clear all cancelled', 'info');
      return;
    }

    const keys = [
      'flatland.designer.designs.v1',
      'flatland.designer.active.v1',
      'flatland.layoutDesigner.designs.v1',
      'flatland.layoutDesigner.active.v1',
      'flatland.layouts.v1',
      'flatland.runtime.selectedLayoutId.v1',
    ];

    for (const key of keys) {
      this.removeDesignerStorage(key);
    }


    const createDefault = (this as any).createHardcodedRuntimeDesign;
    if (typeof createDefault === 'function') {
      this.design = createDefault.call(this);
    }

    this.designs = [this.cloneDesignerDesign(this.design)];
    this.selection = { kind: 'design' };
    this.runLivePreview();
    this.markDesignerDirty('All user layouts cleared. Default copy ready to save.');

    const feedback = (this as any).showDesignerFeedback;
    if (typeof feedback === 'function') {
      feedback.call(this, 'All user layouts cleared', 'warn', 'clear-layouts');
    }
  }


  createNewLayoutFromDefault(): void {
    this.design = this.createHardcodedRuntimeDesign();
    this.storage.save(this.design);
    this.designs = this.storage.list();
    this.storage.setActive(this.design.id);
    this.selection = { kind: 'design' };
    this.isDirty = false;
    this.designerFooterStatusMessage = 'New 2×3 layout created';
    this.designerFooterStatusTone = 'saved';
    this.runLivePreview();
  }



  clearAllUserLayouts(): void {
    this.clearAllUserLayoutsClean();
  }

  private createHardcodedRuntimeDesign(): FlatlandDesign {
    const now = new Date().toISOString();
    const suffix = Math.random().toString(36).slice(2, 10);

    const panel = (
      type: string,
      title: string,
      minHeight: number,
      height: number | null = null,
    ): DesignerPanel => ({
      id: `${type}_${Math.random().toString(36).slice(2, 9)}`,
      type,
      title,
      expanded: true,
      collapsible: true,
      minHeight,
      height,
    });

    const column = (
      rowId: string,
      id: string,
      name: string,
      width: number,
      panels: DesignerPanel[],
    ): DesignerColumn => ({
      id,
      rowId,
      rowHeight: null,
      name,
      width,
      role: 'custom',
      panels,
    });

    return {
      id: `layout-2x3-${suffix}`,
      name: `Layout ${new Date().toLocaleString()}`,
      sessionId: this.activeSessionId,
      scale: 0.7,
      createdAt: now,
      updatedAt: now,
      layout: {
        columns: [
          column('row-1', 'row1_col1_toolbar', 'Row 1 · Toolbar', 520, [
            panel('toolbar', 'Toolbar', 74, 90),
          ]),
          column('row-1', 'row1_col2_layers', 'Row 1 · Layers', 520, [
            panel('layer-visibility', 'Layer Visibility', 80, 100),
          ]),
          column('row-1', 'row1_col3_goal', 'Row 1 · Goal', 520, [
            panel('goal-achievement', 'Goal Achievement', 140, 160),
          ]),
          column('row-2', 'row2_col1_agents', 'Row 2 · Left', 280, [
            panel('agents-list', 'Agents List', 180, 260),
          ]),
          column('row-2', 'row2_col2_visuals', 'Row 2 · Center', 720, [
            panel('toggle-view', 'Toggle View', 520, 640),
          ]),
          column('row-2', 'row2_col3_details', 'Row 2 · Right', 320, [
            panel('agent-inspector', 'Agent Inspector', 180, 220),
            panel('impact', 'Impact', 160, 180),
            panel('timeline', 'Timeline', 130, 150),
            panel('validation', 'Validation', 130, 150),
          ]),
        ],
      },
    };
  }






  saveAsWithFeedback(): void {
    this.saveAsWithPrompt();
  }

  exportJsonWithFeedback(): void {
    this.callDesignerMethod(['exportJson', 'exportJSON', 'exportDesign', 'downloadJson']);
    this.showDesignerFeedback('Layout JSON exported', 'success', 'export');
  }

  importJsonWithFeedback(event: Event): void {
    this.callDesignerMethod(['importJson', 'importJSON', 'importDesign', 'loadJson'], [event]);
    this.showDesignerFeedback('Layout JSON imported', 'success', 'import');
  }

  goHomeWithFeedback(): void {
    this.showDesignerFeedback('Opening Home…', 'info', 'home');

    window.setTimeout(() => {
      const fn = (this as any).goHome;

      if (typeof fn === 'function') {
        fn.call(this);
      } else {
        window.location.href = '/';
      }
    }, 120);
  }


  goHome(): void {
    window.location.href = '/';
  }

  runLivePreview(): void {
    this.syncActiveSession();
    const sessionId = this.activeSessionId;
    const label = sessionId || 'local-designer-session';

    this.livePreviewConnected = !!sessionId;
    this.livePreviewRunning = true;
    this.livePreviewLog = [];

    for (let step = 1; step <= this.livePreviewSteps; step++) {
      this.livePreviewLog.push(`Step ${step}: preview updated for ${label}`);
    }

    this.livePreviewLastRun = new Date().toLocaleTimeString();
    this.livePreviewRunning = false;
  }

  onDesignerChanged(): void {
    this.touch();
    this.runLivePreview();
  }

  panelStyle(panel: DesignerPanel): Record<string, string> {
    const height = panel.height ? `${panel.height}px` : 'auto';
    return {
      minHeight: `${panel.minHeight}px`,
      height,
    };
  }

  trackByColumn(_: number, column: DesignerColumn): string {
    return column.id;
  }

  trackByRow(index: number, row: DesignerColumn[]): string {
    return row?.[0]?.rowId || `row-${index}`;
  }

  trackByPanel(_: number, panel: DesignerPanel): string {
    return panel.id;
  }

  deleteRow(row: DesignerColumn[], event?: Event): void {
    event?.preventDefault();
    event?.stopPropagation();

    if (!row?.length) {
      return;
    }

    const rowId = this.rowIdForRow(row);

    const confirmed = window.confirm(
      `Delete this row and all ${row.length} column(s) in it?`
    );

    if (!confirmed) {
      return;
    }

    this.design.layout.columns = this.design.layout.columns.filter(
      (column) => column.rowId !== rowId
    );

    // Reset selection safely after deleting selected row/column/panel.
    (this as any).selection = { kind: 'design' };
    (this as any).selectedRowId = undefined;

    // Keep designer usable if the last row was removed.
    if (!this.design.layout.columns.length) {
      this.addRow();
    } else {
      this.onDesignerChanged();
    }
  }

  @HostListener('document:keydown', ['$event'])
  handleSelectedRowDeleteKey(event: KeyboardEvent): void {
    if (event.key !== 'Delete' && event.key !== 'Backspace') {
      return;
    }

    const target = event.target as HTMLElement | null;

    if (target) {
      const tag = target.tagName?.toLowerCase();

      if (
        tag === 'input' ||
        tag === 'textarea' ||
        tag === 'select' ||
        target.isContentEditable
      ) {
        return;
      }
    }

    const currentSelection = (this as any).selection;

    if (currentSelection?.kind !== 'row') {
      return;
    }

    const rowId = String(
      (this as any).selectedRowId ??
      currentSelection.rowId ??
      ''
    );

    if (!rowId) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    (event as any).stopImmediatePropagation?.();

    this.deleteSelectedRowById(rowId);
  }

  private deleteSelectedRowById(rowId: string): void {
    const before = this.design.layout.columns.length;

    this.design.layout.columns = this.design.layout.columns.filter(
      (column) => column.rowId !== rowId
    );

    if (this.design.layout.columns.length === before) {
      return;
    }

    (this as any).selection = { kind: 'design' };
    (this as any).selectedRowId = undefined;

    if (!this.design.layout.columns.length) {
      this.addRow();
      return;
    }

    this.onDesignerChanged();
  }

  startRowEdgeResizeIfNearBottom(row: DesignerColumn[], event: PointerEvent): void {
    const target = event.target as HTMLElement | null;

    // Do not start row-resize from buttons, inputs, headers, panels or columns.
    if (
      target?.closest('button, input, textarea, select, .canvas__row-head, .canvas__column, .panel-card')
    ) {
      return;
    }

    const rowElement = (event.currentTarget as HTMLElement | null)?.closest('.canvas__row') as HTMLElement | null;

    if (!rowElement) {
      return;
    }

    const rect = rowElement.getBoundingClientRect();
    const distanceFromBottom = rect.bottom - event.clientY;

    // Bottom edge hit zone: lower 16px of the row.
    if (distanceFromBottom < 0 || distanceFromBottom > 16) {
      return;
    }

    this.startRowResize(row, event);
  }

  private rowResizeV2State: {
    row: DesignerColumn[];
    rowElement: HTMLElement;
    startY: number;
    startHeight: number;
  } | null = null;

  startRowResizeFromBottomEdgeIfNeeded(row: DesignerColumn[], event: PointerEvent): void {
    const target = event.target as HTMLElement | null;

    if (target?.closest('button, input, textarea, select, a, .canvas__row-head')) {
      return;
    }

    const rowElement = event.currentTarget as HTMLElement | null;

    if (!rowElement?.classList.contains('canvas__row')) {
      return;
    }

    const rect = rowElement.getBoundingClientRect();
    const distanceFromBottom = rect.bottom - event.clientY;

    // The lower 28px of the row are the resize hit-zone.
    if (distanceFromBottom < 0 || distanceFromBottom > 28) {
      return;
    }

    this.startBottomEdgeRowResize(row, event);
  }

  startBottomEdgeRowResize(row: DesignerColumn[], event: PointerEvent): void {
    if (!row?.length) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const eventTarget = event.currentTarget as HTMLElement | null;
    const rowElement =
      eventTarget?.classList.contains('canvas__row')
        ? eventTarget
        : eventTarget?.closest('.canvas__row') as HTMLElement | null;

    if (!rowElement) {
      return;
    }

    eventTarget?.setPointerCapture?.(event.pointerId);

    const measuredHeight = rowElement.getBoundingClientRect().height;
    const currentHeight = this.rowHeightPx(row) ?? measuredHeight;
    const startHeight = Math.max(this.rowMinHeightPx(row), Math.round(currentHeight));

    this.rowResizeV2State = {
      row,
      rowElement,
      startY: event.clientY,
      startHeight,
    };

    document.body.classList.add('canvas-row-resizing');

    window.addEventListener('pointermove', this.onBottomEdgeRowResizeMove, { passive: false });
    window.addEventListener('pointerup', this.stopBottomEdgeRowResize, { once: true });
    window.addEventListener('pointercancel', this.stopBottomEdgeRowResize, { once: true });
  }

  private readonly onBottomEdgeRowResizeMove = (event: PointerEvent): void => {
    const state = this.rowResizeV2State;

    if (!state) {
      return;
    }

    event.preventDefault();

    const delta = event.clientY - state.startY;
    const nextHeight = Math.max(
      this.rowMinHeightPx(state.row),
      Math.round(state.startHeight + delta)
    );

    // Immediate visual feedback.
    state.rowElement.style.height = `${nextHeight}px`;
    state.rowElement.style.minHeight = `${this.rowMinHeightPx(state.row)}px`;

    // Persist on every column in this row, because current model stores rows via rowId on columns.
    for (const column of state.row) {
      (column as any).rowHeightPx = nextHeight;
      (column as any).rowHeight = nextHeight;
    }
  };

  readonly stopBottomEdgeRowResize = (): void => {
    if (!this.rowResizeV2State) {
      return;
    }

    this.rowResizeV2State = null;
    document.body.classList.remove('canvas-row-resizing');

    window.removeEventListener('pointermove', this.onBottomEdgeRowResizeMove);
    window.removeEventListener('pointerup', this.stopBottomEdgeRowResize);
    window.removeEventListener('pointercancel', this.stopBottomEdgeRowResize);

    this.onDesignerChanged();
  };


  private loadInitialDesign(): FlatlandDesign {
    const activeId = this.storage.activeId();
    const active = activeId ? this.storage.get(activeId) : undefined;
    const first = active ?? this.storage.list()[0];

    if (first) {
      const next = structuredClone(first);
      this.normalizeDesign(next);
      return next;
    }

    const created = this.storage.createDefault();
    this.storage.save(created);
    this.designs = this.storage.list();
    return structuredClone(created);
  }


  private normalizeLegacyRowIds(design: FlatlandDesign): void {
    for (const [index, column] of (design.layout.columns ?? []).entries()) {
      column.rowId = column.rowId || `legacy-row-${Math.floor(index / 3)}`;
    }
  }

  private normalizeDesign(design: FlatlandDesign): void {
    /* LEGACY_ROW_ID_NORMALIZATION_START */
    this.normalizeLegacyRowIds(design);
    /* LEGACY_ROW_ID_NORMALIZATION_END */
    for (const column of design.layout.columns) {
      for (const panel of column.panels) {
        if (panel.type === 'flatland-map') {
          panel.type = 'flatland-map';
          panel.title = 'Flatland Map';
          panel.minHeight = Math.max(panel.minHeight ?? 0, 320);
          panel.height = panel.height ?? 360;
        }
      }
    }
  }

  private findColumn(id: string): DesignerColumn | undefined {
    return this.design.layout.columns.find((c) => c.id === id);
  }

  private findPanel(columnId: string, panelId: string): DesignerPanel | undefined {
    return this.findColumn(columnId)?.panels.find((p) => p.id === panelId);
  }

  private touch(): void {
    this.markDesignerDirty();
    this.design.updatedAt = new Date().toISOString();
    this.runLivePreview();
  }

  private readonly rowResizeDefaultMinHeight = 120;
  private rowResizeState: {
    row: DesignerColumn[];
    startY: number;
    startHeight: number;
  } | null = null;

  rowMinHeightPx(row: DesignerColumn[] | null | undefined): number {
    const firstColumn = row?.[0] as any;
    const configured = Number(
      firstColumn?.rowMinHeightPx ??
      firstColumn?.rowMinHeight ??
      this.rowResizeDefaultMinHeight
    );

    return Number.isFinite(configured) && configured > 0
      ? Math.max(72, Math.round(configured))
      : this.rowResizeDefaultMinHeight;
  }

  rowHeightPx(row: DesignerColumn[] | null | undefined): number | null {
    const firstColumn = row?.[0] as any;
    const raw = firstColumn?.rowHeightPx ?? firstColumn?.rowHeight;
    const height = Number(raw);

    if (!Number.isFinite(height) || height <= 0) {
      return null;
    }

    return Math.max(this.rowMinHeightPx(row), Math.round(height));
  }

  startRowResize(row: DesignerColumn[], event: PointerEvent): void {
    if (!row?.length) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const handle = event.currentTarget as HTMLElement | null;
    handle?.setPointerCapture?.(event.pointerId);

    const rowElement = handle?.closest('.canvas__row') as HTMLElement | null;
    const measuredHeight = rowElement?.getBoundingClientRect().height ?? this.rowResizeDefaultMinHeight;
    const currentHeight = this.rowHeightPx(row) ?? measuredHeight;

    this.rowResizeState = {
      row,
      startY: event.clientY,
      startHeight: Math.max(this.rowMinHeightPx(row), Math.round(currentHeight)),
    };

    document.body.classList.add('canvas-row-resizing');

    window.addEventListener('pointermove', this.onRowResizeMove, { passive: false });
    window.addEventListener('pointerup', this.stopRowResize, { once: true });
    window.addEventListener('pointercancel', this.stopRowResize, { once: true });
  }

  private readonly onRowResizeMove = (event: PointerEvent): void => {
    const state = this.rowResizeState;

    if (!state) {
      return;
    }

    event.preventDefault();

    const delta = event.clientY - state.startY;
    const nextHeight = Math.max(
      this.rowMinHeightPx(state.row),
      Math.round(state.startHeight + delta)
    );

    for (const column of state.row) {
      (column as any).rowHeightPx = nextHeight;
      (column as any).rowHeight = nextHeight;
    }
  };

  readonly stopRowResize = (): void => {
    if (!this.rowResizeState) {
      return;
    }

    this.rowResizeState = null;
    document.body.classList.remove('canvas-row-resizing');

    window.removeEventListener('pointermove', this.onRowResizeMove);
    window.removeEventListener('pointerup', this.stopRowResize);
    window.removeEventListener('pointercancel', this.stopRowResize);

    this.onDesignerChanged();
  };

}
