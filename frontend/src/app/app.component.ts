import { Component, OnInit, CUSTOM_ELEMENTS_SCHEMA, inject, signal } from '@angular/core';
import { ToolbarComponent } from './features/toolbar/toolbar.component';
import { AgentInspectorComponent } from './features/agent-inspector/agent-inspector.component';
import { LeftSidebarComponent } from './features/left-sidebar/left-sidebar.component';
import { ViewToggleComponent } from './features/view-toggle/view-toggle.component';
import { TrackLayoutComponent } from './features/track-layout/track-layout.component';
import { GraphicTimetableComponent } from './features/graphic-timetable/graphic-timetable.component';
import { LayerVisibilityComponent } from './features/layer-visibility/layer-visibility.component';
import { NotificationsPanelComponent } from './features/notifications-panel/notifications-panel.component';
import { ScenarioPanelComponent } from './features/scenario-panel/scenario-panel.component';
import { KpiFilterComponent } from './features/kpi-filter/kpi-filter.component';
import { RecommendationsPanelComponent } from './features/recommendations-panel/recommendations-panel.component';
import { SessionStore } from './core/session.store';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    ToolbarComponent,
    TrackLayoutComponent,
    GraphicTimetableComponent,
    LayerVisibilityComponent,
    NotificationsPanelComponent,
    ScenarioPanelComponent,
    KpiFilterComponent,
    RecommendationsPanelComponent,
    AgentInspectorComponent,
    LeftSidebarComponent,
    ViewToggleComponent,
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AppComponent implements OnInit {
  store = inject(SessionStore);

  newWidth = signal(50);
  newHeight = signal(20);
  newAgents = signal(3);

  onNewSession() {
    this.store.newSession({
      width: this.newWidth(),
      height: this.newHeight(),
      agents: this.newAgents(),
    });
  }

  ngOnInit(): void {
    this.store.loadPolicies();
  }
}
