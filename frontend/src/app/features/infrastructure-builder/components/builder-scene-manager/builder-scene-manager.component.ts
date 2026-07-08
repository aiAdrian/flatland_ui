import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { InfrastructureBuilderStoreService } from '../../services/infrastructure-builder-store.service';
import { InfrastructureSceneStorageService } from '../../services/infrastructure-scene-storage.service';

@Component({
  selector: 'app-builder-scene-manager',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './builder-scene-manager.component.html',
  styleUrl: './builder-scene-manager.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class BuilderSceneManagerComponent {
  private readonly storage = inject(InfrastructureSceneStorageService);
  readonly store = inject(InfrastructureBuilderStoreService);
  readonly scenes = signal(this.storage.listScenes());
  buttonFeedbackId: string | null = null;
  feedbackMessage = 'Ready';
  feedbackTone: 'saved' | 'dirty' | 'info' | 'warn' = 'info';
  private feedbackTimer: ReturnType<typeof setTimeout> | null = null;

  get isDirty(): boolean {
    const saved = this.storage.get(this.store.scene().id);
    return this.sceneComparable(saved) !== this.sceneComparable(this.store.scene());
  }

  get hasSavedCurrentScene(): boolean {
    return !!this.storage.get(this.store.scene().id);
  }

  newScene(): void {
    const grid = this.store.scene().grid;
    this.store.newScene(grid.width, grid.height);
    this.markDirty('New scene ready to save');
    this.flash('new-scene');
  }

  save(): void {
    this.storage.save(this.store.scene());
    this.refresh();
    this.markSaved('Scene saved');
    this.flash('save');
  }

  saveAs(): void {
    const proposed = `${this.store.scene().name || 'Infrastructure Scene'} Copy`;
    const name = window.prompt('Save scene as...', proposed);

    if (name === null) {
      this.setFeedback('Save As cancelled', 'info');
      return;
    }

    const cleanName = name.trim();
    if (!cleanName) {
      this.setFeedback('Save As cancelled: name is empty', 'warn');
      return;
    }

    const now = new Date().toISOString();
    this.store.loadScene({
      ...structuredClone(this.store.scene()),
      id: `scene_${Date.now()}`,
      name: cleanName,
      createdAt: now,
      updatedAt: now,
    });
    this.storage.save(this.store.scene());
    this.refresh();
    this.markSaved(`Saved as "${cleanName}"`);
    this.flash('save-as');
  }

  load(id: string): void {
    if (!id || id === this.store.scene().id) {
      return;
    }

    if (this.isDirty && !window.confirm('Discard unsaved changes and load another scene?')) {
      return;
    }

    const scene = this.storage.loadScene(id);
    if (scene) {
      this.store.loadScene(scene);
      this.refresh();
      this.markSaved(`Loaded "${scene.name}"`);
    }
  }

  duplicate(id: string): void {
    const scene = this.storage.duplicateScene(id);
    if (scene) {
      this.store.loadScene(scene);
      this.refresh();
    }
  }

  delete(id: string): void {
    if (!window.confirm('Delete this saved infrastructure scene?')) {
      this.setFeedback('Delete cancelled', 'info');
      return;
    }

    this.storage.deleteScene(id);
    this.refresh();

    if (this.store.scene().id === id) {
      this.newScene();
    }

    this.setFeedback('Scene deleted', 'info');
  }

  deleteCurrentScene(): void {
    if (!this.hasSavedCurrentScene) {
      this.setFeedback('Delete unavailable: scene is not saved yet', 'warn');
      return;
    }

    this.delete(this.store.scene().id);
    this.flash('delete-scene');
  }

  exportJson(): void {
    const blob = new Blob([JSON.stringify(this.storage.exportAll(), null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'flatland-infrastructure-scenes.json';
    link.click();
    URL.revokeObjectURL(url);
    this.setFeedback('Scene JSON exported', 'saved');
    this.flash('export');
  }

  async importJson(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];

    if (!file) {
      return;
    }

    try {
      const payload = JSON.parse(await file.text());
      const count = this.storage.importMany(payload);
      this.refresh();

      const latest = this.storage.list().at(-1);
      if (latest) {
        this.store.loadScene(latest);
        this.storage.setActive(latest.id);
      }

      this.setFeedback(`Imported ${count} scene(s)`, count > 0 ? 'saved' : 'warn');
      this.flash('import');
    } catch {
      this.setFeedback('Import failed: invalid JSON', 'warn');
    } finally {
      input.value = '';
    }
  }

  clearAllScenes(): void {
    if (!window.confirm('Delete all saved infrastructure scenes?')) {
      this.setFeedback('Clear all cancelled', 'info');
      return;
    }

    this.storage.clearAll();
    this.refresh();
    const grid = this.store.scene().grid;
    this.store.newScene(grid.width, grid.height);
    this.markDirty('All scenes cleared. New scene ready to save.');
    this.flash('clear-scenes');
  }

  refresh(): void {
    this.scenes.set(this.storage.listScenes());
  }

  onSceneChanged(): void {
    this.markDirty('Unsaved scene changes');
  }

  private sceneComparable(scene: unknown): string {
    if (!scene) {
      return '';
    }

    const copy = structuredClone(scene) as Record<string, unknown>;
    delete copy['updatedAt'];
    delete copy['validation'];
    return JSON.stringify(copy);
  }

  private setFeedback(message: string, tone: 'saved' | 'dirty' | 'info' | 'warn'): void {
    this.feedbackMessage = message;
    this.feedbackTone = tone;
  }

  private markDirty(message: string): void {
    this.setFeedback(message, 'dirty');
  }

  private markSaved(message: string): void {
    this.setFeedback(message, 'saved');
  }

  private flash(actionId: string): void {
    this.buttonFeedbackId = actionId;

    if (this.feedbackTimer) {
      clearTimeout(this.feedbackTimer);
    }

    this.feedbackTimer = setTimeout(() => {
      this.buttonFeedbackId = null;
    }, 260);
  }
}
