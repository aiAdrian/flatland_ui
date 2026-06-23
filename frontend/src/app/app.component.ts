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
    CoLearningReflectionComponent,
    SituationSummaryComponent,
    GoalAchievementComponent,
    DirectorDirectiveComponent,
    SurveyComponent,
    ImpactPanelComponent,
    AgentInspectorComponent,
    AgentsPanelComponent,
    ViewToggleComponent,
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AppComponent implements OnInit {
  store = inject(SessionStore);
  private api = inject(ApiService);

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

  newWidth = signal(50);
  newHeight = signal(20);
  newAgents = signal(3);
  newMaxSteps = signal(1000);
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

  /** Available survey building blocks + the draft selection edited in Settings. */
  readonly surveyParts = SURVEY_PARTS;
  draftSurveyParts = signal<string[]>([...DEFAULT_SURVEY_PARTS]);
  draftDemoMalfunctionTypes = signal(false);
  draftReflectionLimit = signal(2);

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

    // Important: reset/new session must reuse the currently selected
    // settings, including malfunction config. Do not fall back to defaults.
    this.persistSessionSettings();
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


  ngOnInit(): void {
    this.store.loadPolicies();
  }
}
