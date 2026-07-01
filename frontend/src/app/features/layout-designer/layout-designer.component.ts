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
  | { source: 'layout'; columnId: string; panelId: string };

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
    { type: 'agents-list', title: 'Agents List', minHeight: 150 },
    { type: 'simulation-map', title: 'Simulation Map', minHeight: 260 },
    { type: 'flatland-map', title: 'Flatland Map', minHeight: 320 },
    { type: 'marey-chart', title: 'Marey Chart', minHeight: 260 },
    { type: 'graphic-timetable', title: 'Graphic Timetable', minHeight: 260 },
    { type: 'agent-inspector', title: 'Agent Inspector', minHeight: 170 },
    { type: 'goal-achievement', title: 'Goal Achievement', minHeight: 150 },
    { type: 'impact', title: 'Impact', minHeight: 150 },
    { type: 'timeline', title: 'Timeline', minHeight: 140 },
    { type: 'validation', title: 'Validation', minHeight: 140 },
    { type: 'cell-inspector', title: 'Cell Inspector', minHeight: 150 },
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


  private resizing:
    | {
        kind: 'column';
        columnId: string;
        startX: number;
        startWidth: number;
      }
    | {
        kind: 'panel';
        columnId: string;
        panelId: string;
        startY: number;
        startHeight: number;
      }
    | null = null;


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

  get canvasWidth(): number {
    return this.design.layout.columns.reduce((sum, c) => sum + c.width, 0);
  }

  selectDesign(): void {
    this.selection = { kind: 'design' };
    this.runLivePreview();
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
    const index = this.design.layout.columns.length + 1;
    const col: DesignerColumn = {
      id: `column_${Date.now()}`,
      name: `column ${index}`,
      width: 280,
      role: 'custom',
      panels: [],
    };

    this.design.layout.columns.push(col);
    this.selection = { kind: 'column', columnId: col.id };
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

    if (col.panels.length && !confirm('Column contains panels. Delete anyway?')) {
      return;
    }

    this.pushUndoState();

    this.design.layout.columns = this.design.layout.columns.filter((c) => c.id !== col.id);
    this.selection = { kind: 'design' };
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
    if (!confirm(`Delete layout "${this.design.name}"?`)) {
      return;
    }

    this.storage.delete(this.design.id);
    this.designs = this.storage.list();
    this.design = this.loadInitialDesign();
    this.selection = { kind: 'design' };
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

  dropOnColumn(targetColumn: DesignerColumn, event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.layoutDropHandled = true;

    const raw = event.dataTransfer?.getData('application/json');
    if (!raw) {
      return;
    }

    const payload = JSON.parse(raw) as DragPayload;

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

    if (type === 'simulation-map') {
      return 'flatland-map';
    }

    if (type === 'marey-chart') {
      return 'graphic-timetable';
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

    const panel = this.findPanel(this.resizing.columnId, this.resizing.panelId);
    if (!panel) {
      return;
    }

    panel.height = Math.max(panel.minHeight, this.resizing.startHeight + event.clientY - this.resizing.startY);
    this.touch();
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
    this.selection = { kind: 'design' };

    this.runLivePreview();
    this.markDesignerDirty('New default copy ready to edit');

    const feedback = (this as any).showDesignerFeedback;
    if (typeof feedback === 'function') {
      feedback.call(this, 'Hardcoded default copied. Edit and Save.', 'success', 'new-layout');
    }
  }

  clearAllUserLayouts(): void {
    this.clearAllUserLayoutsClean();
  }

  private createHardcodedRuntimeDesign(): FlatlandDesign {
    const now = new Date().toISOString();
    const suffix = Date.now().toString(36);

    const panel = (
      type: string,
      title: string,
      minHeight = 160,
      height = 220,
    ): DesignerPanel => ({
      id: `panel-${type}-${suffix}-${Math.random().toString(36).slice(2, 7)}`,
      type,
      title,
      minHeight,
      height,
      expanded: true,
      collapsible: true,
    });

    return {
      id: `layout-hardcoded-copy-${suffix}`,
      name: `Default Layout Copy ${new Date().toLocaleTimeString()}`,
      sessionId: '',
      scale: 1,
      createdAt: now,
      updatedAt: now,
      layout: {
        columns: [
          {
            id: `left-${suffix}`,
            name: 'Left',
            role: 'sidebar',
            width: 280,
            panels: [
              panel('situation-summary', 'Situation Summary', 140, 180),
              panel('notifications', 'Notifications', 140, 180),
              panel('agents-list', 'Agents', 220, 320),
            ],
          },
          {
            id: `center-${suffix}`,
            name: 'Center',
            role: 'main',
            width: 720,
            panels: [
              panel('flatland-map', 'Flatland Map', 360, 520),
            ],
          },
          {
            id: `right-${suffix}`,
            name: 'Right',
            role: 'custom',
            width: 320,
            panels: [
              panel('agent-inspector', 'Agent Inspector', 180, 240),
              panel('impact', 'Impact', 150, 200),
              panel('scenario', 'Scenario', 220, 320),
              panel('recommendations', 'Recommendations', 160, 220),
              panel('kpi-filter', 'KPI Filter', 160, 220),
            ],
          },
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

  trackByPanel(_: number, panel: DesignerPanel): string {
    return panel.id;
  }

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


  private normalizeDesign(design: FlatlandDesign): void {
    for (const column of design.layout.columns) {
      for (const panel of column.panels) {
        if (panel.type === 'simulation-map') {
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
}
