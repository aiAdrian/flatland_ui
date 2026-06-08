import { Injectable, computed, signal } from '@angular/core';
import { ModuleId, ModuleState } from './module-types';

@Injectable({ providedIn: 'root' })
export class ModuleRegistryService {
  private readonly defaults: Record<ModuleId, ModuleState> = {
    'notifications':       { visible: true,  enabled: true, position: 'left',   title: 'Notifications' },
    'layer-toggles':       { visible: true,  enabled: true, position: 'left',   title: 'Layer Visibility' },
    'agents-list':         { visible: true,  enabled: true, position: 'right',  title: 'Decisions' },
    'track-layout':        { visible: true,  enabled: true, position: 'middle', title: 'Track Layout' },
    'graphic-timetable':   { visible: false, enabled: true, position: 'middle', title: 'Graphic Timetable' },
    'simulation-slider':   { visible: true,  enabled: true, position: 'middle', title: 'Simulation Slider' },
    'scenario-panel':      { visible: true,  enabled: true, position: 'right',  title: 'Scenarios' },
    'kpi-filter':          { visible: true,  enabled: true, position: 'right',  title: 'KPIs' },
    'recommendations':     { visible: true,  enabled: true, position: 'right',  title: 'Recommendations' },
    'inspector':           { visible: true,  enabled: true, position: 'right',  title: 'Inspector' },
  };

  readonly modules = signal<Record<ModuleId, ModuleState>>({ ...this.defaults });

  isVisible(id: ModuleId): boolean {
    return this.modules()[id]?.visible ?? false;
  }

  isEnabled(id: ModuleId): boolean {
    return this.modules()[id]?.enabled ?? false;
  }

  toggle(id: ModuleId): void {
    const cur = this.modules()[id];
    if (!cur || !cur.enabled) return;
    this.modules.update((m) => ({
      ...m,
      [id]: { ...cur, visible: !cur.visible },
    }));
  }

  setVisible(id: ModuleId, v: boolean): void {
    const cur = this.modules()[id];
    if (!cur) return;
    this.modules.update((m) => ({
      ...m,
      [id]: { ...cur, visible: v },
    }));
  }

  modulesByPosition = computed(() => {
    const all = this.modules();
    const out = { left: [] as ModuleId[], middle: [] as ModuleId[], right: [] as ModuleId[] };
    for (const id of Object.keys(all) as ModuleId[]) {
      const m = all[id];
      if (m.visible) out[m.position].push(id);
    }
    return out;
  });
}
