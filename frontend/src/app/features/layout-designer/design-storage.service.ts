import { Injectable } from '@angular/core';
import { DesignerExport, DesignerPanel, FlatlandDesign } from './layout-designer.models';

const DESIGNS_KEY = 'flatland.designer.designs.v1';
const ACTIVE_KEY = 'flatland.designer.activeDesignId.v1';

@Injectable({ providedIn: 'root' })
export class DesignStorageService {
  list(): FlatlandDesign[] {
    return this.readAll();
  }

  get(id: string): FlatlandDesign | undefined {
    return this.readAll().find((d) => d.id === id);
  }

  save(design: FlatlandDesign): void {
    const all = this.readAll();
    const now = new Date().toISOString();
    const next = { ...design, updatedAt: now };
    const idx = all.findIndex((d) => d.id === design.id);

    if (idx >= 0) {
      all[idx] = next;
    } else {
      all.push(next);
    }

    localStorage.setItem(DESIGNS_KEY, JSON.stringify(all));
    localStorage.setItem(ACTIVE_KEY, next.id);
  }

  delete(id: string): void {
    const all = this.readAll().filter((d) => d.id !== id);
    localStorage.setItem(DESIGNS_KEY, JSON.stringify(all));

    if (localStorage.getItem(ACTIVE_KEY) === id) {
      localStorage.removeItem(ACTIVE_KEY);
    }
  }

  activeId(): string | null {
    return localStorage.getItem(ACTIVE_KEY);
  }

  setActive(id: string): void {
    localStorage.setItem(ACTIVE_KEY, id);
  }

  exportAll(): DesignerExport {
    return {
      version: 1,
      exportedAt: new Date().toISOString(),
      designs: this.readAll(),
    };
  }

  importMany(payload: DesignerExport | { designs?: FlatlandDesign[] }): number {
    const incoming = Array.isArray(payload.designs) ? payload.designs : [];
    const all = this.readAll();
    let count = 0;

    for (const design of incoming) {
      if (!design?.id || !design?.name || !design?.layout) {
        continue;
      }

      const idx = all.findIndex((d) => d.id === design.id);
      const next = {
        ...design,
        updatedAt: new Date().toISOString(),
      };

      if (idx >= 0) {
        all[idx] = next;
      } else {
        all.push(next);
      }

      count++;
    }

    localStorage.setItem(DESIGNS_KEY, JSON.stringify(all));
    return count;
  }

  createDefault(name = 'Default Dispatch UI'): FlatlandDesign {
    const now = new Date().toISOString();

    const panel = (
      type: string,
      title: string,
      minHeight = 150,
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

    // Mirrors the hardcoded three-column main layout (see app.component.html):
    // LEFT = situation/notifications/trains, CENTER = the map+timetable toggle
    // composite, RIGHT = inspector/impact/scenario/KPI. Uses only panel types
    // the plugin host actually renders. Mode-specific center panels
    // (goal-achievement, co-learning-reflection, director-directive) and the
    // rec-only recommendations panel are intentionally left out of the default —
    // they are available from the palette.
    return {
      id: `design_${Date.now()}`,
      name,
      sessionId: '',
      scale: 0.75,
      createdAt: now,
      updatedAt: now,
      layout: {
        columns: [
          {
            id: 'left',
            name: 'Left',
            width: 280,
            role: 'sidebar',
            panels: [
              panel('situation-summary', 'Situation Summary', 120),
              panel('notifications', 'Notifications', 140),
              panel('agents', 'Trains', 180),
            ],
          },
          {
            id: 'center',
            name: 'Center',
            width: 720,
            role: 'main',
            panels: [
              {
                ...panel('toggle-view', 'Track Layout & Timetable', 520, 600),
                settings: { toggleSplitOrientation: 'vertical', splitOrientation: 'vertical' },
              },
            ],
          },
          {
            id: 'right',
            name: 'Right',
            width: 340,
            role: 'sidebar',
            panels: [
              panel('agent-inspector', 'Agent Inspector', 180),
              panel('impact', 'Impact', 160),
              panel('scenario', 'Scenario', 160),
              panel('kpi-filter', 'KPI Filter', 160),
            ],
          },
        ],
      },
    };
  }

  private readAll(): FlatlandDesign[] {
    try {
      const raw = localStorage.getItem(DESIGNS_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
}
