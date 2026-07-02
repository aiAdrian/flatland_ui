import { Component, HostBinding, Input, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { PanelInstance } from '../../../../core/layout';

import { NotificationsPanelComponent } from '../../../notifications-panel/notifications-panel.component';
import { AgentsPanelComponent } from '../../../agents-panel/agents-panel.component';
import { KpiFilterComponent } from '../../../kpi-filter/kpi-filter.component';
import { ScenarioPanelComponent } from '../../../scenario-panel/scenario-panel.component';
import { RecommendationsPanelComponent } from '../../../recommendations-panel/recommendations-panel.component';
import { ImpactPanelComponent } from '../../../impact-panel/impact-panel.component';
import { FlatlandMapComponent } from '../../../flatland-map/flatland-map.component';
import { GraphicTimetableComponent } from '../../../graphic-timetable/graphic-timetable.component';
import { SituationSummaryComponent } from '../../../situation-summary/situation-summary.component';

import { AgentInspectorComponent } from '../../../agent-inspector/agent-inspector.component';
import { GoalAchievementPanelComponent } from '../../../../shared/layout/panels/goal-achievement-panel/goal-achievement-panel.component';
import { LayoutViewToggleService } from '../../../../core/layout-view-toggle.service';
import { LayoutViewTogglePanelComponent } from '../../../../shared/layout/panels/layout-view-toggle-panel/layout-view-toggle-panel.component';
import { LayerVisibilityComponent } from '../../../layer-visibility/layer-visibility.component';
import { ToolbarComponent } from '../../../toolbar/toolbar.component';
import { ViewToggleComponent } from '../../../view-toggle/view-toggle.component';

import { SessionStore } from '../../../../core/session.store';

type ViewMode = 'only-map' | 'only-marey' | 'split';
@Component({
  selector: 'app-panel-plugin-host',
  standalone: true,
  imports: [
    ViewToggleComponent,ToolbarComponent,
    LayerVisibilityComponent,
    LayoutViewTogglePanelComponent,
    GoalAchievementPanelComponent, 
    AgentInspectorComponent,
    NotificationsPanelComponent,
    AgentsPanelComponent,
    KpiFilterComponent,
    ScenarioPanelComponent,
    RecommendationsPanelComponent,
    ImpactPanelComponent,
    FlatlandMapComponent,
    GraphicTimetableComponent,
    SituationSummaryComponent,
  ],
  templateUrl: './panel-plugin-host.component.html',
  styleUrl: './panel-plugin-host.component.scss',
})
export class PanelPluginHostComponent implements OnInit, OnDestroy {
  toggleSplitOrientation(): 'vertical' | 'horizontal' {
    const panelAny = this.panel as any;

    const value =
      panelAny?.settings?.toggleSplitOrientation ??
      panelAny?.settings?.splitOrientation ??
      panelAny?.toggleSplitOrientation ??
      panelAny?.splitOrientation ??
      'vertical';

    return value === 'horizontal' ? 'horizontal' : 'vertical';
  }

  readonly store = inject(SessionStore);

  
  // >>> toggle-view-marey-update

  readonly viewMode = signal<ViewMode>('split');

  readonly showMap = computed(() => {
    const mode = this.viewMode();
    return mode === 'only-map' || mode === 'split';
  });

  readonly showMarey = computed(() => {
    const mode = this.viewMode();
    return mode === 'only-marey' || mode === 'split';
  });

  setViewMode(mode: ViewMode): void {
    this.viewMode.set(mode);
  }

  setShowMap(value: boolean): void {
    const currentlyMarey = this.showMarey();

    if (value && currentlyMarey) {
      this.viewMode.set('split');
      return;
    }

    if (value && !currentlyMarey) {
      this.viewMode.set('only-map');
      return;
    }

    if (!value && currentlyMarey) {
      this.viewMode.set('only-marey');
      return;
    }

    this.viewMode.set('only-marey');
  }

  setShowMarey(value: boolean): void {
    const currentlyMap = this.showMap();

    if (value && currentlyMap) {
      this.viewMode.set('split');
      return;
    }

    if (value && !currentlyMap) {
      this.viewMode.set('only-marey');
      return;
    }

    if (!value && currentlyMap) {
      this.viewMode.set('only-map');
      return;
    }

    this.viewMode.set('only-map');
  }

  // <<< toggle-view-marey-update


  private readonly runtimeCompositeShowMapState = signal(true);
  private readonly runtimeCompositeShowMareyState = signal(false);


  private readonly runtimeCompositeViewToggle = inject(LayoutViewToggleService);

  private readonly layoutViewToggle = inject(LayoutViewToggleService);
  private unregisterPanelType?: () => void;


  ngOnInit(): void {
    this.unregisterPanelType = this.layoutViewToggle.registerPanelType(this.panel?.type);
  }

  ngOnDestroy(): void {
    this.unregisterPanelType?.();
  }

  isViewVisible(panelType: string): boolean {
    return this.layoutViewToggle.isPanelTypeVisible(panelType);
  }

  @Input({ required: true }) panel!: PanelInstance;

  @HostBinding('attr.data-panel-type')
  get hostPanelType(): string | null {
    return this.panel?.type ?? null;
  }

  get isCanvasPanel(): boolean {
    return this.panel?.type === 'toggle-view'
      || this.panel?.type === 'flatland-map'
      || this.panel?.type === 'simulation-map'
      || this.panel?.type === 'marey'
      || this.panel?.type === 'marey-chart'
      || this.panel?.type === 'graphic-timetable';
  }

  private readonly nonCollapsiblePanelTypes = new Set<string>([
    'toggle-view',
    'layout-view-toggle',
    'layout-view-toggle-panel',
    'view-toggle',
  ]);

  isNonCollapsiblePanel(panel?: any): boolean {
    const candidate =
      panel ??
      (this as any).panel ??
      (this as any).runtimePanel ??
      (this as any).selectedPanel ??
      (this as any).currentPanel ??
      (this as any).item ??
      null;

    const type = String(
      candidate?.type ??
      candidate?.panelType ??
      candidate?.id ??
      (this as any).panelType ??
      (this as any).type ??
      ''
    ).toLowerCase();

    return this.nonCollapsiblePanelTypes.has(type);
  }

  private runtimeCompositeServiceFlag(kind: 'map' | 'marey'): boolean | null {
    const service = (this as any).runtimeCompositeViewToggle;

    if (!service) {
      return null;
    }

    const keys = kind === 'map'
      ? ['map', 'showMap', 'mapVisible', 'flatlandMap', 'flatlandMapVisible', 'isMapVisible', 'showFlatlandMap']
      : ['marey', 'showMarey', 'mareyVisible', 'graphicTimetable', 'graphicTimetableVisible', 'isMareyVisible', 'showGraphicTimetable'];

    const candidates: any[] = [service];

    for (const source of [service?.state, service?.value, service?.visibleViews, service?.viewState]) {
      try {
        const resolved = typeof source === 'function'
          ? source.call(service)
          : source;

        if (resolved && typeof resolved === 'object') {
          candidates.push(resolved);
        }
      } catch {
        // Ignore.
      }
    }

    for (const candidate of candidates) {
      if (!candidate || typeof candidate !== 'object') {
        continue;
      }

      for (const key of keys) {
        try {
          const raw = candidate[key];
          const value = typeof raw === 'function' && raw.length === 0
            ? raw.call(candidate)
            : raw;

          if (typeof value === 'boolean') {
            return value;
          }
        } catch {
          // Ignore.
        }
      }

      for (const [key, raw] of Object.entries(candidate)) {
        const normalizedKey = key.toLowerCase();
        const relevant = kind === 'map'
          ? normalizedKey.includes('map') || normalizedKey.includes('flatland')
          : normalizedKey.includes('marey') || normalizedKey.includes('graphic') || normalizedKey.includes('timetable');

        if (!relevant) {
          continue;
        }

        try {
          const value = typeof raw === 'function' && (raw as Function).length === 0
            ? (raw as Function).call(candidate)
            : raw;

          if (typeof value === 'boolean') {
            return value;
          }
        } catch {
          // Ignore.
        }
      }
    }

    return null;
  }

  onRuntimeCompositeViewToggleClick(event: Event): void {
    const path = typeof event.composedPath === 'function'
      ? event.composedPath()
      : [];

    const targetTextParts: string[] = [];

    for (const entry of path) {
      const element = entry as HTMLElement;

      if (!element || typeof element.textContent !== 'string') {
        continue;
      }

      const tagName = String(element.tagName ?? '').toLowerCase();

      if (
        tagName === 'sbb-checkbox' ||
        tagName === 'button' ||
        tagName === 'label' ||
        element.classList?.contains('view-toggle') ||
        element.classList?.contains('layout-view-toggle-panel__check')
      ) {
        targetTextParts.push(element.textContent);
      }
    }

    if (!targetTextParts.length) {
      targetTextParts.push(String((event.target as HTMLElement | null)?.textContent ?? ''));
    }

    const text = targetTextParts.join(' ').toLowerCase();

    if (text.includes('marey') || text.includes('graphic') || text.includes('timetable')) {
      this.runtimeCompositeShowMareyState.update((value) => !value);
      return;
    }

    if (text.includes('map') || text.includes('flatland')) {
      this.runtimeCompositeShowMapState.update((value) => !value);
    }
  }

  onRuntimeCompositeViewToggleChange(event: Event): void {
    this.onRuntimeCompositeViewToggleClick(event);
  }

  showToggleCompositeMap(): boolean {
    const serviceValue = this.runtimeCompositeServiceFlag('map');

    if (serviceValue !== null) {
      return serviceValue || this.runtimeCompositeShowMapState();
    }

    return this.runtimeCompositeShowMapState();
  }

  showToggleCompositeMarey(): boolean {
    const serviceValue = this.runtimeCompositeServiceFlag('marey');

    if (serviceValue !== null) {
      return serviceValue || this.runtimeCompositeShowMareyState();
    }

    return this.runtimeCompositeShowMareyState();
  }

  toggleCompositeViewsClass(): string {
    const map = this.showToggleCompositeMap();
    const marey = this.showToggleCompositeMarey();

    if (map && marey) {
      return 'panel-plugin-host__toggle-views split';
    }

    if (marey) {
      return 'panel-plugin-host__toggle-views only-marey';
    }

    return 'panel-plugin-host__toggle-views only-map';
  }

}
