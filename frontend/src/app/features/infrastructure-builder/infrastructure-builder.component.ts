import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, EventEmitter, HostListener, Input, OnChanges, Output, SimpleChanges, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { BuilderCanvasComponent } from './components/builder-canvas/builder-canvas.component';
import { BuilderInspectorComponent } from './components/builder-inspector/builder-inspector.component';
import { BuilderLeftSidebarComponent } from './components/builder-left-sidebar/builder-left-sidebar.component';
import { BuilderSceneManagerComponent } from './components/builder-scene-manager/builder-scene-manager.component';
import { ConfigShellComponent } from '../config-shell/config-shell.component';
import { InfrastructureBuilderStoreService } from './services/infrastructure-builder-store.service';
import { InfrastructureSceneStorageService } from './services/infrastructure-scene-storage.service';

@Component({
  selector: 'app-infrastructure-builder',
  standalone: true,
  imports: [CommonModule, FormsModule, ConfigShellComponent, BuilderCanvasComponent, BuilderInspectorComponent, BuilderLeftSidebarComponent, BuilderSceneManagerComponent],
  templateUrl: './infrastructure-builder.component.html',
  styleUrl: './infrastructure-builder.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class InfrastructureBuilderComponent implements OnChanges {
  readonly store = inject(InfrastructureBuilderStoreService);
  private readonly storage = inject(InfrastructureSceneStorageService);
  readonly startChoiceOpen = signal(false);
  readonly savedInfrastructureScenes = signal(this.storage.listScenes());
  selectedInfrastructureId = '';
  private sessionGridApplied = false;

  @Input() sessionGridWidth = 20;
  @Input() sessionGridHeight = 12;

  @Output() openSettingsRequested = new EventEmitter<void>();
  @Output() newSessionRequested = new EventEmitter<void>();

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['sessionGridWidth'] && !changes['sessionGridHeight']) {
      return;
    }

    const scene = this.store.scene();
    const isEmptyScene = scene.cells.length === 0 && scene.agents.length === 0 && scene.stations.length === 0;
    if (!this.sessionGridApplied || isEmptyScene) {
      this.store.newScene(this.sessionGridWidth, this.sessionGridHeight);
      this.sessionGridApplied = true;
    }
  }

  useSessionGrid(): void {
    this.store.updateGrid(this.sessionGridWidth, this.sessionGridHeight);
  }

  openInfrastructureStartChoice(): void {
    const scenes = this.storage.listScenes();
    this.savedInfrastructureScenes.set(scenes);
    this.selectedInfrastructureId = scenes[0]?.id ?? '';
    this.startChoiceOpen.set(true);
  }

  closeInfrastructureStartChoice(): void {
    this.startChoiceOpen.set(false);
  }

  startRandomInfrastructure(): void {
    this.store.newRandomScene(this.sessionGridWidth, this.sessionGridHeight);
    this.startChoiceOpen.set(false);
  }

  loadSelectedInfrastructure(): void {
    const scene = this.selectedInfrastructureId ? this.storage.loadScene(this.selectedInfrastructureId) : null;
    if (!scene) {
      return;
    }

    this.store.loadScene(scene);
    this.startChoiceOpen.set(false);
  }

  goHome(): void {
    window.location.href = '/';
  }

  @HostListener('document:keydown', ['$event'])
  onDocumentKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Delete' && event.key !== 'Backspace') {
      return;
    }

    if (this.isEditableTarget(event.target)) {
      return;
    }

    event.preventDefault();
    this.store.deleteSelectedElement();
  }

  private isEditableTarget(target: EventTarget | null): boolean {
    const element = target as HTMLElement | null;
    if (!element) {
      return false;
    }

    return !!element.closest('input, textarea, select, [contenteditable="true"]');
  }
}
