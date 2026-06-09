import {
  Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
import { AgentColorService } from '../../core/agent-color.service';

interface AgentLine {
  handle: number;
  color: string;
  pastD: string;
  futureD: string;
  isActive: boolean;
}

@Component({
  selector: 'app-marey-chart',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './marey-chart.component.html',
  styleUrls: ['./marey-chart.component.scss'],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class MareyChartComponent {
  private readonly store = inject(SessionStore);
  private readonly colors = inject(AgentColorService);

  readonly W = 1200;
  readonly H = 700;
  readonly PAD = { top: 32, right: 24, bottom: 36, left: 56 };

  readonly activeHandle = this.store.activeHandle;
  readonly elapsed = computed(() => this.store.state()?.elapsed_steps ?? 0);
  readonly maxSteps = computed(() => this.store.maxSteps() || 1);
  readonly scenarios = this.store.scenarios;

  readonly forecastScenarioId = signal<string | null>(null);

  readonly forecastScenario = computed(() => {
    const id = this.forecastScenarioId();
    const all = this.scenarios();
    if (!all || all.length === 0) return null;
    if (id) {
      const found = all.find(s => s.id === id);
      if (found) return found;
    }
    return all.find(s => s.isBaseline) ?? all[0];
  });

  readonly pathCells = computed<string[]>(() => {
    const sc = this.forecastScenario();
    const handle = this.activeHandle();
    if (!sc || handle == null || !sc.trajectories) return [];
    const traj = sc.trajectories[String(handle)] ?? [];
    const seen = new Set<string>();
    const out: string[] = [];
    for (const p of traj) {
      const key = `${p.row},${p.col}`;
      if (!seen.has(key)) { seen.add(key); out.push(key); }
    }
    return out;
  });

  readonly pathIndex = computed<Map<string, number>>(() => {
    const m = new Map<string, number>();
    this.pathCells().forEach((k, i) => m.set(k, i));
    return m;
  });

  readonly agentLines = computed<AgentLine[]>(() => {
    const sc = this.forecastScenario();
    const active = this.activeHandle();
    const idx = this.pathIndex();
    if (!sc || active == null || idx.size === 0 || !sc.trajectories) return [];

    const now = this.elapsed();
    const lines: AgentLine[] = [];

    for (const [handleStr, traj] of Object.entries(sc.trajectories)) {
      const handle = Number(handleStr);
      const isActive = handle === active;
      const past: { x: number; y: number }[] = [];
      const future: { x: number; y: number }[] = [];

      for (const p of traj) {
        const key = `${p.row},${p.col}`;
        const xIdx = idx.get(key);
        if (xIdx === undefined) continue;
        const sx = this.xCoord(xIdx);
        const sy = this.yCoord(p.step);
        (p.step <= now ? past : future).push({ x: sx, y: sy });
      }

      const pastD = past.length > 1 ? this.toPathD(past) : '';
      const futureD = future.length > 1 ? this.toPathD(future) : '';
      if (!pastD && !futureD) continue;

      lines.push({
        handle, color: this.colors.getColorSolid(handle),
        pastD, futureD, isActive,
      });
    }
    lines.sort((a, b) => Number(a.isActive) - Number(b.isActive));
    return lines;
  });

  xCoord(i: number): number {
    const cells = this.pathCells().length || 1;
    const inner = this.W - this.PAD.left - this.PAD.right;
    return this.PAD.left + (i / Math.max(1, cells - 1)) * inner;
  }
  yCoord(step: number): number {
    const m = this.maxSteps();
    const inner = this.H - this.PAD.top - this.PAD.bottom;
    return this.PAD.top + (step / m) * inner;
  }
  toPathD(pts: { x: number; y: number }[]): string {
    return pts.map((p, i) =>
      `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`
    ).join(' ');
  }

  readonly yTicks = computed(() => {
    const m = this.maxSteps();
    const step = m <= 200 ? 50 : m <= 500 ? 100 : 200;
    const out: { v: number; y: number }[] = [];
    for (let v = 0; v <= m; v += step) out.push({ v, y: this.yCoord(v) });
    return out;
  });
  readonly nowY = computed(() => this.yCoord(this.elapsed()));

  setForecastScenario(id: string | null): void {
    this.forecastScenarioId.set(id);
  }
}
