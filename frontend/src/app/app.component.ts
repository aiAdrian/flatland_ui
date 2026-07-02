import '@sbb-esta/lyne-elements/toggle-check.js';
import { Component, OnInit, CUSTOM_ELEMENTS_SCHEMA, HostListener, effect, inject, signal } from '@angular/core';
import { ToolbarComponent } from './features/toolbar/toolbar.component';
import { AgentInspectorComponent } from './features/agent-inspector/agent-inspector.component';
import { AgentsPanelComponent } from './features/agents-panel/agents-panel.component';
import { ViewToggleComponent } from './features/view-toggle/view-toggle.component';
import { TrackLayoutComponent } from './features/track-layout/track-layout.component';
import { GraphicTimetableComponent } from './features/graphic-timetable/graphic-timetable.component';
import { LayerVisibilityComponent } from './features/layer-visibility/layer-visibility.component';
import { NotificationsPanelComponent } from './features/notifications-panel/notifications-panel.component';
import { ScenarioPanelComponent } from './features/scenario-panel/scenario-panel.component';
import { KpiFilterComponent } from './features/kpi-filter/kpi-filter.component';
import { RecommendationsPanelComponent } from './features/recommendations-panel/recommendations-panel.component';
import { CoLearningReflectionComponent } from './features/co-learning-reflection/co-learning-reflection.component';
import { SituationSummaryComponent } from './features/situation-summary/situation-summary.component';
import { GoalAchievementComponent } from './features/goal-achievement/goal-achievement.component';
import { DirectorDirectiveComponent } from './features/director-directive/director-directive.component';
import { SurveyComponent } from './features/survey/survey.component';
import { ImpactPanelComponent } from './features/impact-panel/impact-panel.component';
import { SURVEY_PARTS, DEFAULT_SURVEY_PARTS } from './core/survey/survey-configs';
import { ApiService } from './core/api.service';
import { SessionStore } from './core/session.store';
import { InteractionMode } from './core/events/event-types';
import { PanelInstance } from './core/layout';
import { PanelShellComponent } from './features/layout/components/panel-shell/panel-shell.component';

import { LayoutDesignerComponent } from './features/layout-designer/layout-designer.component';
import { PanelPluginHostComponent } from './features/layout/components/panel-plugin-host/panel-plugin-host.component';
type RuntimeLayoutOption = {
  id: string;
  name: string;
  kind: 'system' | 'user';
  design?: any;
};

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    PanelPluginHostComponent,
    LayoutDesignerComponent,
    ToolbarComponent,
    TrackLayoutComponent,
    GraphicTimetableComponent,
    LayerVisibilityComponent,
    NotificationsPanelComponent,
    ScenarioPanelComponent,
    KpiFilterComponent,
    RecommendationsPanelComponent,
    CoLearningReflectionComponent,
    SituationSummaryComponent,
    GoalAchievementComponent,
    DirectorDirectiveComponent,
    SurveyComponent,
    ImpactPanelComponent,
    AgentInspectorComponent,
    AgentsPanelComponent,
    ViewToggleComponent,
PanelShellComponent,
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AppComponent implements OnInit {

  get showLayoutDesigner(): boolean {
    return (
      window.location.pathname === '/designer' ||
      window.location.hash === '#/designer' ||
      window.location.hash.endsWith('/designer')
    );
  }


  private ensureDesignerSession(): void {
    if (!this.showLayoutDesigner || this.designerSessionRequested) {
      return;
    }

    this.designerSessionRequested = true;

    queueMicrotask(() => {
      try {
        Promise.resolve(this.onNewSession() as unknown).catch((error) => {
          console.error('Designer session creation failed', error);
        });
      } catch (error) {
        console.error('Designer session creation failed', error);
      }
    });
  }


  openLayoutDesigner(): void {
    window.location.href = '/designer';
  }

  store = inject(SessionStore);
  private api = inject(ApiService);

  readonly systemRuntimeLayoutId = 'system-default-runtime-layout';

  readonly selectedRuntimeLayoutId = signal<string>(this.systemRuntimeLayoutId);

  readonly runtimeLayoutOptions = signal<RuntimeLayoutOption[]>(this.loadRuntimeLayoutOptions());

  private designerSessionRequested = false;

  // layout-runtime-bridge: panel shell based runtime layout
  // These are the first static runtime panel definitions. The later designer
  // will write equivalent configs dynamically.
  readonly panelSituationSummary: PanelInstance = {
    id: 'runtime-situation-summary',
    type: 'situation-summary',
    title: 'Situation Summary',
    zone: 'left',
    order: 10,
    collapsed: false,
    hidden: false,
    sizeMode: 'auto',
  };

  readonly panelNotifications: PanelInstance = {
    id: 'runtime-notifications',
    type: 'notifications',
    title: 'Notifications',
    zone: 'left',
    order: 20,
    collapsed: false,
    hidden: false,
    sizeMode: 'auto',
  };

  readonly panelAgents: PanelInstance = {
    id: 'runtime-agents',
    type: 'agents',
    title: 'Agents',
    zone: 'left',
    order: 30,
    collapsed: false,
    hidden: false,
    sizeMode: 'auto',
  };

  readonly panelFlatlandMap: PanelInstance = {
    id: 'runtime-flatland-map',
    type: 'flatland-map',
    title: 'Flatland Map',
    zone: 'center',
    order: 10,
    collapsed: false,
    hidden: false,
    sizeMode: 'fill',
  };

  readonly panelGraphicTimetable: PanelInstance = {
    id: 'runtime-graphic-timetable',
    type: 'graphic-timetable',
    title: 'Graphic Timetable',
    zone: 'center',
    order: 20,
    collapsed: false,
    hidden: false,
    sizeMode: 'fill',
  };

  readonly panelImpact: PanelInstance = {
    id: 'runtime-impact',
    type: 'impact',
    title: 'Impact',
    zone: 'right',
    order: 10,
    collapsed: false,
    hidden: false,
    sizeMode: 'auto',
  };

  readonly panelScenario: PanelInstance = {
    id: 'runtime-scenario',
    type: 'scenario',
    title: 'Scenario',
    zone: 'right',
    order: 20,
    collapsed: false,
    hidden: false,
    sizeMode: 'auto',
  };

  readonly panelRecommendations: PanelInstance = {
    id: 'runtime-recommendations',
    type: 'recommendations',
    title: 'Recommendations',
    zone: 'right',
    order: 30,
    collapsed: false,
    hidden: false,
    sizeMode: 'auto',
  };

  readonly panelKpiFilter: PanelInstance = {
    id: 'runtime-kpi-filter',
    type: 'kpi-filter',
    title: 'KPI Filter',
    zone: 'right',
    order: 40,
    collapsed: false,
    hidden: false,
    sizeMode: 'auto',
  };

  /** Human-AI collaboration modes shown in the header switcher (WP 3.1/3.3/3.4). */
  readonly interactionModes: { id: InteractionMode; label: string; wp: string; description: string }[] = [
    { id: 'recommendation', label: 'Recommendation', wp: 'WP 3.1', description: 'AI suggests, you decide.' },
    { id: 'co-learning', label: 'Co-Learning', wp: 'WP 3.3', description: 'You and the AI adapt to each other.' },
    { id: 'director', label: 'Director', wp: 'WP 3.4', description: 'AI acts autonomously on your high-level directives.' },
  ];

  /** Label of the currently active collaboration mode (for the header dropdown). */
  currentModeLabel(): string {
    const id = this.store.interactionMode();
    return this.interactionModes.find((m) => m.id === id)?.label ?? id;
  }

  // Defaults match the conflict-tuned guided-demo env so an untouched
  // "Guided Demo" reliably produces conflicts; users can still change them.
  newWidth = signal(36);
  newHeight = signal(24);
  newAgents = signal(8);
  newMaxSteps = signal(400);
  newSeed = signal(42);
  newLatestDepartureMax = signal(20);
  newSpeedProfile = signal('uniform_1_0');
  newMaxNumCities = signal(4);
  newMaxRailsBetweenCities = signal(2);
  newMaxRailPairsInCity = signal(2);
  newLineLength = signal(4);
  newMalfunctionsEnabled = signal(false);
  newMalfunctionRate = signal(0.001);
  newMalfunctionMinDuration = signal(5);
  newMalfunctionMaxDuration = signal(20);

  settingsMode = signal(false);
  scenarioPolicyMode = signal(false);
  surveyActive = signal(false);
  demoComplete = signal(false);
  showLayoutSandbox = signal(false);

  toggleLayoutSandbox(): void {
    this.showLayoutSandbox.update((value) => !value);
  }

  /** Demo environment. The conflict-tuning (bottlenecked corridors via few
   *  rails/pairs + real malfunctions) stays fixed so conflicts reliably
   *  emerge, but the four user-facing fields from the welcome page / Settings
   *  (grid size, #agents, max steps) are respected — picking "Guided Demo"
   *  no longer silently ignores them. Their defaults (see newWidth/etc.) are
   *  set to the conflict-prone values, so an untouched demo stays tuned. */
  private demoSessionOpts() {
    return {
      width: this.newWidth(), height: this.newHeight(),
      agents: this.newAgents(), maxSteps: this.newMaxSteps(),
      seed: 42,
      maxNumCities: 3, maxRailsBetweenCities: 2, maxRailPairsInCity: 1,
      latestDepartureMax: 35, speedProfile: 'uniform_1_0', lineLength: 4,
      // Slightly higher than before (0.012) so a blocking malfunction — and
      // thus an impact-driven decision moment — surfaces more reliably within
      // a run. Scripted events (Phase 1) will later guarantee this.
      malfunctionRate: 0.02, malfunctionMinDuration: 10, malfunctionMaxDuration: 22,
      scenarioPolicyIds: this.welcomeScenarioPolicyIds(),
      policyControlIds: this.welcomeControlPolicyIds(),
    };
  }

  /** Start the guided demo: one fixed env, modes run in sequence. */
  startDemoSession() {
    this.store.stopDemo();
    this.demoComplete.set(false);
    this.store.newSession(this.demoSessionOpts());
    this.store.startDemo();
  }

  /** Finish the current demo mode → open its survey (advance happens on close). */
  finishDemoMode() {
    this.openSurvey();
  }

  exitDemo() {
    this.store.stopDemo();
    this.demoComplete.set(false);
  }

  /** Available survey building blocks + the draft selection edited in Settings. */
  readonly surveyParts = SURVEY_PARTS;
  draftSurveyParts = signal<string[]>([...DEFAULT_SURVEY_PARTS]);
  draftDemoMalfunctionTypes = signal(false);
  draftReflectionLimit = signal(2);
  draftDecisionCountdown = signal(10);
  draftRecommendationDuration = signal(0);
  draftAutoPauseOnConflict = signal(true);

  isDraftSurveyPartEnabled(id: string): boolean {
    return this.draftSurveyParts().includes(id);
  }

  toggleDraftSurveyPart(id: string, enabled: boolean) {
    const cur = this.draftSurveyParts();
    const next = enabled
      ? Array.from(new Set([...cur, id]))
      : cur.filter((x) => x !== id);
    this.draftSurveyParts.set(next);
  }

  openSurvey() {
    this.surveyActive.set(true);
    this.blurActiveElement();
  }

  closeSurvey() {
    this.surveyActive.set(false);
    // In the guided demo, submitting a mode's survey advances to the next mode
    // (replaying the SAME environment) or finishes the demo.
    if (this.store.demoActive()) {
      const more = this.store.advanceDemo();
      if (more) {
        this.store.reset(); // same env, fresh start for the next mode
      } else {
        this.demoComplete.set(true);
      }
    }
  }
  draftWidth = signal(50);
  draftHeight = signal(20);
  draftAgents = signal(3);
  draftMaxSteps = signal(1000);
  draftSeed = signal(42);
  draftLatestDepartureMax = signal(20);
  draftSpeedProfile = signal('uniform_1_0');
  draftMaxNumCities = signal(4);
  draftMaxRailsBetweenCities = signal(2);
  draftMaxRailPairsInCity = signal(2);
  draftLineLength = signal(4);
  draftMalfunctionsEnabled = signal(false);
  draftMalfunctionRate = signal(0.001);
  draftMalfunctionMinDuration = signal(5);
  draftMalfunctionMaxDuration = signal(20);
  draftScenarioPolicyIds = signal<string[]>([]);
  draftControlPolicyIds = signal<string[]>([]);

  welcomeScenarioPolicyIds = signal<string[]>([]);
  welcomeControlPolicyIds = signal<string[]>([]);
  pendingScenarioPolicyIds = signal<string[] | null>(null);
  pendingScenarioPreviousSessionId = signal<string | null>(null);

  private readonly sessionSettingsStorageKey = 'flatland_ui_session_settings_v1';

  private normalizedMalfunctionMinDuration(): number {
    return Math.max(1, Math.floor(this.newMalfunctionMinDuration() || 1));
  }

  private normalizedMalfunctionMaxDuration(): number {
    return Math.max(
      this.normalizedMalfunctionMinDuration(),
      Math.floor(this.newMalfunctionMaxDuration() || this.normalizedMalfunctionMinDuration()),
    );
  }

  private effectiveMalfunctionRate(): number {
    if (!this.newMalfunctionsEnabled()) return 0;
    const rate = Number(this.newMalfunctionRate() || 0);
    return Math.max(0, Math.min(1, rate));
  }

  private persistSessionSettings(): void {
    try {
      localStorage.setItem(this.sessionSettingsStorageKey, JSON.stringify({
        width: this.newWidth(),
        height: this.newHeight(),
        agents: this.newAgents(),
        maxSteps: this.newMaxSteps(),
        seed: this.newSeed(),
        latestDepartureMax: this.newLatestDepartureMax(),
        speedProfile: this.newSpeedProfile(),
        maxNumCities: this.newMaxNumCities(),
        maxRailsBetweenCities: this.newMaxRailsBetweenCities(),
        maxRailPairsInCity: this.newMaxRailPairsInCity(),
        lineLength: this.newLineLength(),
        malfunctionsEnabled: this.newMalfunctionsEnabled(),
        malfunctionRate: this.newMalfunctionRate(),
        malfunctionMinDuration: this.newMalfunctionMinDuration(),
        malfunctionMaxDuration: this.newMalfunctionMaxDuration(),
        surveyParts: this.store.enabledSurveyParts(),
        demoMalfunctionTypes: this.store.demoMalfunctionTypes(),
        reflectionLimit: this.store.reflectionQuestionLimit(),
        decisionCountdown: this.store.decisionCountdownSeconds(),
        recommendationDuration: this.store.recommendationDurationSeconds(),
        autoPauseOnConflict: this.store.autoPauseOnConflict(),
      }));
    } catch {
      // localStorage can be unavailable in tests / private mode.
    }
  }

  private loadPersistedSessionSettings(): void {
    try {
      const raw = localStorage.getItem(this.sessionSettingsStorageKey);
      if (!raw) return;
      const cfg = JSON.parse(raw);

      if (cfg.width != null) this.newWidth.set(Number(cfg.width));
      if (cfg.height != null) this.newHeight.set(Number(cfg.height));
      if (cfg.agents != null) this.newAgents.set(Number(cfg.agents));
      if (cfg.maxSteps != null) this.newMaxSteps.set(Number(cfg.maxSteps));
      if (cfg.seed != null) this.newSeed.set(Number(cfg.seed));
      if (cfg.latestDepartureMax != null) this.newLatestDepartureMax.set(Number(cfg.latestDepartureMax));
      if (cfg.speedProfile != null) this.newSpeedProfile.set(String(cfg.speedProfile));
      if (cfg.maxNumCities != null) this.newMaxNumCities.set(Number(cfg.maxNumCities));
      if (cfg.maxRailsBetweenCities != null) this.newMaxRailsBetweenCities.set(Number(cfg.maxRailsBetweenCities));
      if (cfg.maxRailPairsInCity != null) this.newMaxRailPairsInCity.set(Number(cfg.maxRailPairsInCity));
      if (cfg.lineLength != null) this.newLineLength.set(Number(cfg.lineLength));

      if (cfg.malfunctionsEnabled != null) this.newMalfunctionsEnabled.set(Boolean(cfg.malfunctionsEnabled));
      if (cfg.malfunctionRate != null) this.newMalfunctionRate.set(Number(cfg.malfunctionRate));
      if (cfg.malfunctionMinDuration != null) this.newMalfunctionMinDuration.set(Number(cfg.malfunctionMinDuration));
      if (cfg.malfunctionMaxDuration != null) this.newMalfunctionMaxDuration.set(Number(cfg.malfunctionMaxDuration));
      if (Array.isArray(cfg.surveyParts)) this.store.setEnabledSurveyParts(cfg.surveyParts.map(String));
      if (cfg.demoMalfunctionTypes != null) this.store.setDemoMalfunctionTypes(Boolean(cfg.demoMalfunctionTypes));
      if (cfg.reflectionLimit != null) this.store.setReflectionQuestionLimit(Number(cfg.reflectionLimit));
      if (cfg.decisionCountdown != null) this.store.setDecisionCountdownSeconds(Number(cfg.decisionCountdown));
      if (cfg.recommendationDuration != null) this.store.setRecommendationDurationSeconds(Number(cfg.recommendationDuration));
      if (cfg.autoPauseOnConflict != null) this.store.setAutoPauseOnConflict(Boolean(cfg.autoPauseOnConflict));
    } catch {
      // Ignore malformed persisted settings.
    }
  }

  constructor() {
    this.loadPersistedSessionSettings();
    effect(() => {
      const available = this.store.availablePolicies();
      if (available.length > 0 && this.welcomeScenarioPolicyIds().length === 0) {
        this.welcomeScenarioPolicyIds.set(available.filter((p) => p.supports_scenarios).map((p) => p.id));
      }
      if (available.length > 0 && this.welcomeControlPolicyIds().length === 0) {
        this.welcomeControlPolicyIds.set(available.filter((p) => p.show_in_ui).map((p) => p.id));
      }
    });

    effect(() => {
      const sid = this.store.session()?.id;
      const pending = this.pendingScenarioPolicyIds();
      const previousSid = this.pendingScenarioPreviousSessionId();
      if (!sid || !pending) return;

      // When resetting/recreating from an existing session, do not apply
      // pending settings to the old session. Wait until SessionStore exposes
      // the newly-created session id.
      if (previousSid !== null && sid === previousSid) return;

      this.pendingScenarioPolicyIds.set(null);
      this.pendingScenarioPreviousSessionId.set(null);
      this.api.setScenarioPolicies(sid, pending).subscribe({
        next: () => this.store.refreshForecasts(),
        error: (e) => this.store.error.set(`Set scenario policies failed: ${e.message}`),
      });
    });
  }

  onNewSession() {
    this.persistSessionSettings();
    this.pendingScenarioPreviousSessionId.set(null);
    this.pendingScenarioPolicyIds.set(null);
    this.store.newSession({
      width: this.newWidth(),
      height: this.newHeight(),
      agents: this.newAgents(),
      maxSteps: this.newMaxSteps(),
      seed: this.newSeed(),
      maxNumCities: this.newMaxNumCities(),
      maxRailsBetweenCities: this.newMaxRailsBetweenCities(),
      maxRailPairsInCity: this.newMaxRailPairsInCity(),
      latestDepartureMax: this.newLatestDepartureMax(),
      speedProfile: this.newSpeedProfile(),
      lineLength: this.newLineLength(),
      malfunctionRate: this.effectiveMalfunctionRate(),
      malfunctionMinDuration: this.normalizedMalfunctionMinDuration(),
      malfunctionMaxDuration: this.normalizedMalfunctionMaxDuration(),
      scenarioPolicyIds: this.welcomeScenarioPolicyIds(),
      policyControlIds: this.welcomeControlPolicyIds(),
    });
  }


  private blurActiveElement() {
    setTimeout(() => {
      const el = document.activeElement as HTMLElement | null;
      el?.blur?.();
    });
  }

  openSettings() {
    this.draftWidth.set(this.newWidth());
    this.draftHeight.set(this.newHeight());
    this.draftAgents.set(this.newAgents());
    this.draftMaxSteps.set(this.newMaxSteps());
    this.draftSeed.set(this.newSeed());
    this.draftLatestDepartureMax.set(this.newLatestDepartureMax());
    this.draftSpeedProfile.set(this.newSpeedProfile());
    this.draftMaxNumCities.set(this.newMaxNumCities());
    this.draftMaxRailsBetweenCities.set(this.newMaxRailsBetweenCities());
    this.draftMaxRailPairsInCity.set(this.newMaxRailPairsInCity());
    this.draftLineLength.set(this.newLineLength());
    this.draftMalfunctionsEnabled.set(this.newMalfunctionsEnabled());
    this.draftMalfunctionRate.set(this.newMalfunctionRate());
    this.draftMalfunctionMinDuration.set(this.newMalfunctionMinDuration());
    this.draftMalfunctionMaxDuration.set(this.newMalfunctionMaxDuration());
    this.draftScenarioPolicyIds.set([...this.welcomeScenarioPolicyIds()]);
    this.draftSurveyParts.set([...this.store.enabledSurveyParts()]);
    this.draftDemoMalfunctionTypes.set(this.store.demoMalfunctionTypes());
    this.draftReflectionLimit.set(this.store.reflectionQuestionLimit());
    this.draftDecisionCountdown.set(this.store.decisionCountdownSeconds());
    this.draftRecommendationDuration.set(this.store.recommendationDurationSeconds());
    this.draftAutoPauseOnConflict.set(this.store.autoPauseOnConflict());
    this.scenarioPolicyMode.set(false);
    this.settingsMode.set(true);
    this.blurActiveElement();
  }

  cancelSettings() {
    this.settingsMode.set(false);
    this.blurActiveElement();
  }

  applySettings() {
    this.newWidth.set(this.draftWidth());
    this.newHeight.set(this.draftHeight());
    this.newAgents.set(this.draftAgents());
    this.newMaxSteps.set(this.draftMaxSteps());
    this.newSeed.set(this.draftSeed());
    this.newLatestDepartureMax.set(this.draftLatestDepartureMax());
    this.newSpeedProfile.set(this.draftSpeedProfile());
    this.newMaxNumCities.set(this.draftMaxNumCities());
    this.newMaxRailsBetweenCities.set(this.draftMaxRailsBetweenCities());
    this.newMaxRailPairsInCity.set(this.draftMaxRailPairsInCity());
    this.newLineLength.set(this.draftLineLength());
    this.newMalfunctionsEnabled.set(this.draftMalfunctionsEnabled());
    this.newMalfunctionRate.set(this.draftMalfunctionRate());
    this.newMalfunctionMinDuration.set(Math.max(1, Math.floor(this.draftMalfunctionMinDuration() || 1)));
    this.newMalfunctionMaxDuration.set(Math.max(this.newMalfunctionMinDuration(), Math.floor(this.draftMalfunctionMaxDuration() || this.newMalfunctionMinDuration())));
    this.store.setEnabledSurveyParts(this.draftSurveyParts());
    this.store.setDemoMalfunctionTypes(this.draftDemoMalfunctionTypes());
    this.store.setReflectionQuestionLimit(this.draftReflectionLimit());
    this.store.setDecisionCountdownSeconds(this.draftDecisionCountdown());
    this.store.setRecommendationDurationSeconds(this.draftRecommendationDuration());
    this.store.setAutoPauseOnConflict(this.draftAutoPauseOnConflict());
    this.persistSessionSettings();
    this.settingsMode.set(false);
    this.blurActiveElement();
  }


  openScenarioPolicySettings() {
    this.draftScenarioPolicyIds.set([...this.welcomeScenarioPolicyIds()]);
    this.draftControlPolicyIds.set([...this.welcomeControlPolicyIds()]);
    this.settingsMode.set(false);
    this.scenarioPolicyMode.set(true);
    this.blurActiveElement();
  }

  cancelScenarioPolicySettings() {
    this.scenarioPolicyMode.set(false);
    this.blurActiveElement();
  }

  applyScenarioPolicySettings() {
    const enabledScenarios = [...this.draftScenarioPolicyIds()];
    const enabledControls = [...this.draftControlPolicyIds()];

    this.welcomeScenarioPolicyIds.set(enabledScenarios);
    this.welcomeControlPolicyIds.set(enabledControls);

    this.store.setEnabledScenarioPolicyIds(enabledScenarios);
    this.store.setEnabledControlPolicyIds(enabledControls);
    this.store.previewScenarioId.set(null);
    this.scenarioPolicyMode.set(false);
    this.blurActiveElement();

    const sid = this.store.session()?.id;
    if (!sid) return;

    const active = this.store.activePolicy();
    const fallbackPolicy =
      this.store.availablePolicies().find((p) => p.is_default && enabledControls.includes(p.id))?.id ??
      this.store.availablePolicies().find((p) => enabledControls.includes(p.id))?.id ??
      enabledControls[0];

    const activeWasRemoved = !enabledControls.includes(active);
    const nextPolicy = activeWasRemoved ? fallbackPolicy : active;

    if (activeWasRemoved && nextPolicy) {
      this.store.setActivePolicy(nextPolicy as any);
    }

    this.api.setScenarioPolicies(sid, enabledScenarios, enabledControls).subscribe({
      next: () => {
        if (activeWasRemoved && nextPolicy) {
          this.api.setPolicy(sid, nextPolicy as any).subscribe({
            next: () => {
              this.store.setActivePolicy(nextPolicy as any);
              this.store.refreshForecasts();
            },
            error: (e) => this.store.error.set(`Set policy failed: ${e.message}`),
          });
        } else {
          this.store.refreshForecasts();
        }
      },
      error: (e) => this.store.error.set(`Set scenario policies failed: ${e.message}`),
    });
  }

  resetWithSettings() {
    if (this.settingsMode()) this.applySettings();
    if (this.scenarioPolicyMode()) this.applyScenarioPolicySettings();
    this.onNewSession();
  }

  isWelcomeScenarioPolicyEnabled(policyId: string): boolean {
    return this.welcomeScenarioPolicyIds().includes(policyId);
  }

  toggleWelcomeScenarioPolicy(policyId: string, enabled: boolean) {
    const current = this.welcomeScenarioPolicyIds();
    const next = enabled
      ? Array.from(new Set([...current, policyId]))
      : current.filter((id) => id !== policyId);
    if (next.length === 0) return;
    this.welcomeScenarioPolicyIds.set(next);
  }

  isDraftScenarioPolicyEnabled(policyId: string): boolean {
    return this.draftScenarioPolicyIds().includes(policyId);
  }

  toggleDraftScenarioPolicy(policyId: string, enabled: boolean) {
    const current = this.draftScenarioPolicyIds();
    const next = enabled
      ? Array.from(new Set([...current, policyId]))
      : current.filter((id) => id !== policyId);
    if (next.length === 0) return;
    this.draftScenarioPolicyIds.set(next);
  }

  isDraftControlPolicyEnabled(policyId: string): boolean {
    return this.draftControlPolicyIds().includes(policyId);
  }

  toggleDraftControlPolicy(policyId: string, enabled: boolean) {
    const current = this.draftControlPolicyIds();
    const next = enabled
      ? Array.from(new Set([...current, policyId]))
      : current.filter((id) => id !== policyId);
    if (next.length === 0) return;
    this.draftControlPolicyIds.set(next);
  }
  @HostListener('window:keydown.escape', ['$event'])
  onEscapeDeselectAgent(event: Event): void {
    // ESC priority:
    // 1) close open settings dialogs/panels
    // 2) only if no dialog/panel was open, deselect selected agent

    if (this.surveyActive()) {
      this.closeSurvey();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (this.settingsMode()) {
      this.cancelSettings();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (this.scenarioPolicyMode()) {
      this.cancelScenarioPolicySettings();
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    if (this.store.selectedHandle() != null) {
      this.store.selectedHandle.set(null);
      event.preventDefault();
      event.stopPropagation();
    }
  }

  private readLocalStorage(key: string): string | null {
    try {
      return typeof localStorage === 'undefined' ? null : localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  private writeLocalStorage(key: string, value: string): void {
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(key, value);
      }
    } catch {
      // Ignore local storage errors.
    }
  }

  loadRuntimeLayoutOptions(): RuntimeLayoutOption[] {
    const options: RuntimeLayoutOption[] = [
      {
        id: this.systemRuntimeLayoutId,
        name: 'Default Layout ✓ hardcoded',
        kind: 'system',
      },
    ];

    const candidateKeys = [
      'flatland.designer.designs.v1',
      'flatland.layoutDesigner.designs.v1',
      'flatland.layouts.v1',
    ];

    for (const key of candidateKeys) {
      try {
        const raw = this.readLocalStorage(key);
        const designs = raw ? JSON.parse(raw) : [];

        if (!Array.isArray(designs)) {
          continue;
        }

        for (const design of designs) {
          if (!design?.id || !design?.layout?.columns) {
            continue;
          }

          if (options.some((option) => option.id === String(design.id))) {
            continue;
          }

          options.push({
            id: String(design.id),
            name: String(design.name || 'User Layout'),
            kind: 'user',
            design,
          });
        }
      } catch {
        // Ignore invalid storage entries.
      }
    }

    return options;
  }

  refreshRuntimeLayouts(): void {
    this.runtimeLayoutOptions.set(this.loadRuntimeLayoutOptions());

    const selectedExists = this.runtimeLayoutOptions().some(
      (layout) => layout.id === this.selectedRuntimeLayoutId()
    );

    if (!selectedExists) {
      this.setRuntimeLayout(this.systemRuntimeLayoutId);
    }
  }

  setRuntimeLayout(id: string): void {
    this.selectedRuntimeLayoutId.set(id || this.systemRuntimeLayoutId);
  }

  activeRuntimeDesign(): any | null {
    const selectedId = this.selectedRuntimeLayoutId();

    // Important: the system/default layout is the hardcoded AppComponent layout.
    // It must never be loaded from designer storage.
    if (!selectedId || selectedId === this.systemRuntimeLayoutId) {
      return null;
    }

    const option = this.runtimeLayoutOptions().find((layout) => layout.id === selectedId);

    if (!option || option.kind === 'system') {
      return null;
    }

    return option.design ?? null;
  }

  useSavedRuntimeLayout(): boolean {
    return this.selectedRuntimeLayoutId() !== this.systemRuntimeLayoutId && !!this.activeRuntimeDesign();
  }

  runtimeGridTemplate(): string {
    const columns = this.activeRuntimeDesign()?.layout?.columns ?? [];

    if (!Array.isArray(columns) || !columns.length) {
      return '280px minmax(0, 1fr) 320px';
    }

    return columns
      .map((column: any) => {
        const width = Math.max(160, Number(column?.width ?? 280));
        return `minmax(160px, ${width}fr)`;
      })
      .join(' ');
  }

  runtimeColumnClass(column: any, index: number): string {
    const role = String(column?.role || column?.name || '').toLowerCase();

    if (role.includes('right')) {
      return 'right-pane runtime-design__column runtime-design__column--right';
    }

    if (role.includes('main') || role.includes('center') || role.includes('map') || index === 1) {
      return 'center-pane runtime-design__column runtime-design__column--center';
    }

    return 'left-pane runtime-design__column runtime-design__column--left';
  }

  toRuntimePanel(column: any, panel: any, order: number): PanelInstance {
    const type = this.toRuntimePanelType(String(panel?.type ?? 'unknown'));
    const zone = this.toRuntimeZone(column);

    return {
      id: `runtime-user-${panel?.id ?? order}`,
      type,
      title: String(panel?.title ?? type),
      zone,
      order,
      collapsed: panel?.expanded === false,
      hidden: false,
      sizeMode: zone === 'center' ? 'fill' : 'auto',
    } as PanelInstance;
  }

  private toRuntimeZone(column: any): 'left' | 'center' | 'right' {
    const role = String(column?.role || column?.name || '').toLowerCase();

    if (role.includes('right')) {
      return 'right';
    }

    if (role.includes('main') || role.includes('center') || role.includes('map')) {
      return 'center';
    }

    return 'left';
  }

  private toRuntimePanelType(type: string): string {
    if (type === 'agents-list') {
      return 'agents';
    }

    if (type === 'flatland-map') {
      return 'flatland-map';
    }

    if (type === 'marey-chart') {
      return 'graphic-timetable';
    }

    return type;
  }




  ngOnInit(): void {
    this.ensureDesignerSession();
    this.store.loadPolicies();
  }

  runtimePanelZone(column: { id?: string; zone?: string } | null | undefined): string {
    const zone = String(column?.zone ?? column?.id ?? '').trim();
    return zone || 'custom';
  }

  runtimeColumnClassString(column: { id?: string; zone?: string } | null | undefined): string {
    const raw = this.runtimePanelZone(column).toLowerCase();

    const isLeft = raw === 'left';
    const isCenter = raw === 'center' || raw === 'middle' || raw === 'main';
    const isRight = raw === 'right';
    const isKnown = isLeft || isCenter || isRight;

    const classes = ['runtime-design__column'];

    if (isLeft) {
      classes.push('left-pane', 'runtime-design__column--left');
    } else if (isCenter) {
      classes.push('center-pane', 'runtime-design__column--center');
    } else if (isRight) {
      classes.push('right-pane', 'runtime-design__column--right');
    } else {
      classes.push('runtime-design__column--custom');
    }

    if (!isKnown) {
      classes.push('runtime-design__column--custom');
    }

    return Array.from(new Set(classes)).join(' ');
  }

  runtimeLayoutActive(): boolean {
    const self = this as any;
    return !!(
      self.activeLayout ||
      self.activeRuntimeLayout ||
      self.runtimeLayout ||
      self.selectedLayout ||
      self.currentLayout
    );
  }

  runtimeColumns(): any[] {
    const self = this as any;

    const candidateNames = [
      'activeRuntimeLayout',
      'selectedRuntimeLayout',
      'currentRuntimeLayout',
      'runtimeLayout',
      'savedRuntimeLayout',
      'activeLayout',
      'selectedLayout',
      'currentLayout',
      'userLayout',
      'design',
    ];

    for (const name of candidateNames) {
      const value = self[name];

      try {
        const resolved = typeof value === 'function' && value.length === 0
          ? value.call(this)
          : value;

        const columns = this.runtimeColumnsFrom(resolved);

        if (columns.length) {
          return columns;
        }
      } catch {
        // Ignore non-runtime candidates.
      }
    }

    const activeId = this.runtimeActiveLayoutId();

    const listCandidateNames = [
      'runtimeLayoutOptions',
      'designerLayoutOptions',
      'layoutOptions',
      'designs',
      'layouts',
    ];

    for (const name of listCandidateNames) {
      const value = self[name];

      try {
        const resolved = typeof value === 'function' && value.length === 0
          ? value.call(this)
          : value;

        if (!Array.isArray(resolved)) {
          continue;
        }

        const selected = activeId
          ? resolved.find((item: any) => String(item?.id) === activeId)
          : resolved.find((item: any) => item?.active || item?.selected) ?? resolved[0];

        const columns = this.runtimeColumnsFrom(selected);

        if (columns.length) {
          return columns;
        }
      } catch {
        // Ignore non-runtime candidates.
      }
    }

    return this.runtimeColumnsFromLocalStorage();
  }

  private runtimeActiveLayoutId(): string {
    const self = this as any;

    const idCandidateNames = [
      'activeRuntimeLayoutId',
      'selectedRuntimeLayoutId',
      'currentRuntimeLayoutId',
      'runtimeLayoutId',
      'selectedLayoutId',
      'activeLayoutId',
      'currentLayoutId',
    ];

    for (const name of idCandidateNames) {
      const value = self[name];

      try {
        const resolved = typeof value === 'function' && value.length === 0
          ? value.call(this)
          : value;

        if (resolved !== undefined && resolved !== null && String(resolved).trim()) {
          return String(resolved);
        }
      } catch {
        // Ignore.
      }
    }

    return '';
  }

  private runtimeColumnsFrom(value: any): any[] {
    const candidates = [
      value,
      value?.columns,
      value?.layout?.columns,
      value?.design?.layout?.columns,
      value?.runtimeLayout?.columns,
      value?.runtimeLayout?.layout?.columns,
      value?.selectedLayout?.columns,
      value?.selectedLayout?.layout?.columns,
    ];

    for (const candidate of candidates) {
      if (this.isRuntimeColumnArray(candidate)) {
        return candidate;
      }
    }

    if (Array.isArray(value)) {
      for (const item of value) {
        const columns = this.runtimeColumnsFrom(item);

        if (columns.length) {
          return columns;
        }
      }
    }

    return [];
  }

  private isRuntimeColumnArray(value: any): value is any[] {
    return Array.isArray(value)
      && value.length > 0
      && value.some((item: any) =>
        item &&
        typeof item === 'object' &&
        (
          Array.isArray(item.panels) ||
          item.rowId !== undefined ||
          item.width !== undefined ||
          item.widthPx !== undefined
        )
      );
  }

  private runtimeColumnsFromLocalStorage(): any[] {
    try {
      const storage = globalThis.localStorage;

      if (!storage) {
        return [];
      }

      const activeId = this.runtimeActiveLayoutId();
      const parsedValues: any[] = [];

      for (let index = 0; index < storage.length; index++) {
        const key = storage.key(index);

        if (!key) {
          continue;
        }

        const raw = storage.getItem(key);

        if (!raw || (!raw.includes('columns') && !raw.includes('layout'))) {
          continue;
        }

        try {
          parsedValues.push(JSON.parse(raw));
        } catch {
          // Ignore non-json values.
        }
      }

      if (activeId) {
        for (const value of parsedValues) {
          const match = this.findRuntimeLayoutById(value, activeId);
          const columns = this.runtimeColumnsFrom(match);

          if (columns.length) {
            return columns;
          }
        }
      }

      for (const value of parsedValues) {
        const columns = this.runtimeColumnsFrom(value);

        if (columns.length) {
          return columns;
        }
      }
    } catch {
      // localStorage may be unavailable.
    }

    return [];
  }

  private findRuntimeLayoutById(value: any, id: string): any {
    if (!value || typeof value !== 'object') {
      return null;
    }

    if (String(value?.id ?? '') === id) {
      return value;
    }

    if (Array.isArray(value)) {
      for (const item of value) {
        const found = this.findRuntimeLayoutById(item, id);

        if (found) {
          return found;
        }
      }

      return null;
    }

    for (const child of Object.values(value)) {
      const found = this.findRuntimeLayoutById(child, id);

      if (found) {
        return found;
      }
    }

    return null;
  }

  isToggleCompositeRuntimePanel(panel: any): boolean {
    const type = String(panel?.type ?? panel?.panelType ?? panel?.id ?? '').toLowerCase();

    return type === 'toggle-view'
      || type === 'layout-view-toggle'
      || type === 'layout-view-toggle-panel'
      || type === 'view-toggle';
  }


  runtimeRows(layoutOrColumns: any): Array<{ id: string; columns: any[]; heightPx: number | null }> {
    const columns: any[] = Array.isArray(layoutOrColumns)
      ? layoutOrColumns
      : Array.isArray(layoutOrColumns?.columns)
        ? layoutOrColumns.columns
        : Array.isArray(layoutOrColumns?.layout?.columns)
          ? layoutOrColumns.layout.columns
          : [];

    const rows: Array<{ id: string; columns: any[]; heightPx: number | null; order: number }> = [];
    const byId = new Map<string, { id: string; columns: any[]; heightPx: number | null; order: number }>();

    for (const [index, column] of columns.entries()) {
      const rowId = String(column?.rowId ?? column?.row ?? column?.rowKey ?? 'row-1');

      let row = byId.get(rowId);

      if (!row) {
        row = {
          id: rowId,
          columns: [],
          heightPx: this.runtimeColumnRowHeightPx(column),
          order: index,
        };

        byId.set(rowId, row);
        rows.push(row);
      }

      this.normalizeNonCollapsibleRuntimePanels(column);
      row.columns.push(column);

      const columnRowHeight = this.runtimeColumnRowHeightPx(column);

      if (columnRowHeight !== null) {
        row.heightPx = columnRowHeight;
      }
    }

    return rows.sort((a, b) => a.order - b.order);
  }

  runtimeColumnRowHeightPx(column: any): number | null {
    const raw =
      column?.rowHeightPx ??
      column?.rowHeight ??
      column?.heightPx ??
      null;

    const value = Number(raw);

    if (!Number.isFinite(value) || value <= 0) {
      return null;
    }

    return Math.max(72, Math.round(value));
  }

  runtimeRowHeightPx(row: { heightPx?: number | null } | null | undefined): number | null {
    const value = Number(row?.heightPx);

    if (!Number.isFinite(value) || value <= 0) {
      return null;
    }

    return Math.max(72, Math.round(value));
  }

  runtimeRowGridTemplate(row: { columns?: any[] } | null | undefined): string {
    const columns = row?.columns ?? [];

    if (!columns.length) {
      return 'minmax(0, 1fr)';
    }

    if (columns.length === 1) {
      return 'minmax(0, 100%)';
    }

    const bases: number[] = columns.map((column: any) => {
      const explicitPercent =
        column?.widthPercent ??
        column?.widthPct ??
        column?.percentWidth ??
        column?.percentageWidth;

      if (explicitPercent !== undefined && explicitPercent !== null) {
        const value = Number(explicitPercent);

        if (Number.isFinite(value) && value > 0) {
          return value;
        }
      }

      const width = Number(column?.width ?? column?.widthPx ?? column?.basis ?? 0);
      return Number.isFinite(width) && width > 0 ? width : 1;
    });

    const total = bases.reduce((sum: number, value: number) => sum + value, 0);

    if (!Number.isFinite(total) || total <= 0) {
      const equal = 100 / columns.length;
      return columns.map(() => `minmax(0, ${equal.toFixed(4)}%)`).join(' ');
    }

    let used = 0;

    return bases
      .map((basis: number, index: number) => {
        const percent =
          index === bases.length - 1
            ? Math.max(0, 100 - used)
            : Math.max(0, (basis / total) * 100);

        if (index !== bases.length - 1) {
          used += percent;
        }

        return `minmax(0, ${percent.toFixed(4)}%)`;
      })
      .join(' ');
  }

  private readonly nonCollapsibleRuntimePanelTypes = new Set<string>([
    'toggle-view',
    'layout-view-toggle',
    'layout-view-toggle-panel',
    'view-toggle',
  ]);

  isNonCollapsibleRuntimePanel(panel: any): boolean {
    const type = String(panel?.type ?? panel?.panelType ?? panel?.id ?? '').toLowerCase();
    return this.nonCollapsibleRuntimePanelTypes.has(type);
  }

  normalizeNonCollapsibleRuntimePanels(column: any): void {
    for (const panel of column?.panels ?? []) {
      if (!this.isNonCollapsibleRuntimePanel(panel)) {
        continue;
      }

      panel.collapsed = false;
      panel.isCollapsed = false;
      panel.expanded = true;
      panel.collapsible = false;
      panel.canCollapse = false;
    }
  }

}
