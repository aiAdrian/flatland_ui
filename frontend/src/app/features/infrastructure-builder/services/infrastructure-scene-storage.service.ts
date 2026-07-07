import { Injectable } from '@angular/core';
import { InfrastructureScene, InfrastructureSceneExport, InfrastructureSceneSummary } from '../models/scene.model';

const SCENES_KEY = 'flatland.infrastructure.scenes.v1';
const ACTIVE_SCENE_KEY = 'flatland.infrastructure.activeSceneId.v1';

@Injectable({ providedIn: 'root' })
export class InfrastructureSceneStorageService {
  list(): InfrastructureScene[] {
    return this.readAll();
  }

  get(id: string): InfrastructureScene | undefined {
    return this.readAll().find((scene) => scene.id === id);
  }

  save(scene: InfrastructureScene): void {
    this.saveScene(scene);
  }

  saveScene(scene: InfrastructureScene): void {
    const all = this.readAll();
    const next = { ...scene, updatedAt: new Date().toISOString() };
    const index = all.findIndex((candidate) => candidate.id === scene.id);

    if (index >= 0) {
      all[index] = next;
    } else {
      all.push(next);
    }

    localStorage.setItem(SCENES_KEY, JSON.stringify(all));
    localStorage.setItem(ACTIVE_SCENE_KEY, next.id);
  }

  delete(id: string): void {
    this.deleteScene(id);
  }

  loadScene(id: string): InfrastructureScene | null {
    const scene = this.readAll().find((candidate) => candidate.id === id);
    if (scene) {
      localStorage.setItem(ACTIVE_SCENE_KEY, scene.id);
    }
    return scene ?? null;
  }

  listScenes(): InfrastructureSceneSummary[] {
    return this.readAll().map((scene) => ({
      id: scene.id,
      name: scene.name,
      updatedAt: scene.updatedAt,
      gridWidth: scene.grid.width,
      gridHeight: scene.grid.height,
      agentCount: scene.agents.length,
      stationCount: scene.stations.length,
      valid: scene.validation.valid,
      linkedLayoutId: scene.linkedLayoutId,
    }));
  }

  deleteScene(id: string): void {
    localStorage.setItem(SCENES_KEY, JSON.stringify(this.readAll().filter((scene) => scene.id !== id)));
    if (localStorage.getItem(ACTIVE_SCENE_KEY) === id) {
      localStorage.removeItem(ACTIVE_SCENE_KEY);
    }
  }

  duplicateScene(id: string): InfrastructureScene | null {
    const scene = this.loadScene(id);
    if (!scene) {
      return null;
    }

    const now = new Date().toISOString();
    const copy: InfrastructureScene = {
      ...scene,
      id: `scene_${Date.now()}`,
      name: `${scene.name} Copy`,
      createdAt: now,
      updatedAt: now,
    };

    this.saveScene(copy);
    return copy;
  }

  exportScene(scene: InfrastructureScene): string {
    return JSON.stringify(scene, null, 2);
  }

  exportAll(): InfrastructureSceneExport {
    return {
      version: 1,
      exportedAt: new Date().toISOString(),
      scenes: this.readAll(),
    };
  }

  importMany(payload: InfrastructureSceneExport | { scenes?: InfrastructureScene[] }): number {
    const incoming = Array.isArray(payload.scenes) ? payload.scenes : [];
    const all = this.readAll();
    let count = 0;

    for (const scene of incoming) {
      if (!scene?.id || !scene?.grid || !Array.isArray(scene.cells)) {
        continue;
      }

      const index = all.findIndex((candidate) => candidate.id === scene.id);
      const next = {
        ...scene,
        updatedAt: new Date().toISOString(),
      };

      if (index >= 0) {
        all[index] = next;
      } else {
        all.push(next);
      }

      count++;
    }

    localStorage.setItem(SCENES_KEY, JSON.stringify(all));
    return count;
  }

  importScene(json: string): InfrastructureScene {
    const parsed = JSON.parse(json) as InfrastructureScene;
    if (!parsed?.id || !parsed?.grid || !Array.isArray(parsed.cells)) {
      throw new Error('Invalid infrastructure scene JSON.');
    }
    return parsed;
  }

  activeSceneId(): string | null {
    return localStorage.getItem(ACTIVE_SCENE_KEY);
  }

  activeId(): string | null {
    return this.activeSceneId();
  }

  setActive(id: string): void {
    localStorage.setItem(ACTIVE_SCENE_KEY, id);
  }

  clearAll(): void {
    localStorage.removeItem(SCENES_KEY);
    localStorage.removeItem(ACTIVE_SCENE_KEY);
  }

  private readAll(): InfrastructureScene[] {
    try {
      const raw = localStorage.getItem(SCENES_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
}
