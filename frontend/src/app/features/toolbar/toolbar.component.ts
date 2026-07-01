import '@sbb-esta/lyne-elements/toggle-check.js';
import { Component, CUSTOM_ELEMENTS_SCHEMA, EventEmitter, Input, Output, computed, effect, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { PolicyName } from '../../core/models';
import { ApiService } from '../../core/api.service';

@Component({
  selector: 'app-toolbar',
  standalone: true,
  templateUrl: './toolbar.component.html',
  styleUrl: './toolbar.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ToolbarComponent {
  @Input() settingsActive = false;
  @Input() scenarioPolicyActive = false;
  @Input() demoActive = false;
  @Input() demoIsLast = false;
  @Output() openSettings = new EventEmitter<void>();
  @Output() openScenarioPolicy = new EventEmitter<void>();
  @Output() resetRequested = new EventEmitter<void>();
  @Output() finishDemoMode = new EventEmitter<void>();
  @Output() exitDemoRequested = new EventEmitter<void>();
  store = inject(SessionStore);
  private api = inject(ApiService);
  newWidth = signal(50);
  newHeight = signal(20);
  newAgents = signal(3);

  policy = signal<PolicyName>('deadlock_avoidance');
  enabledPolicyIds = signal<string[]>([]);
  speed = signal(1);

  readonly selectablePolicies = computed(() => {
    const enabled = new Set(this.enabledPolicyIds());
    return this.store.availablePolicies().filter((p) => enabled.has(p.id));
  });

  constructor() {
    // Mirror backend/session active policy into the toolbar, but never
    // re-select a policy that has just been disabled in Settings.
    effect(() => {
      const active = this.store.activePolicy();
      const enabled = this.enabledPolicyIds();
      if (!active) return;
      if (enabled.length > 0 && !enabled.includes(active)) return;
      if (active !== this.policy()) {
        this.policy.set(active);
      }
    });

    effect(() => {
      const ids = this.store.enabledControlPolicyIds();
      if (ids.length > 0) {
        this.enabledPolicyIds.set(ids);
        if (!ids.includes(this.policy()) && ids.length > 0) {
          this.policy.set(ids[0] as PolicyName);
        }
      }
    });

    effect(() => {
      const sid = this.store.session()?.id;
      if (!sid) {
        this.enabledPolicyIds.set([]);
        return;
      }
      this.api.getScenarioPolicies(sid).subscribe({
        next: (cfg) => {
          const controlIds = cfg.enabled_policy_ids ?? cfg.enabled_ids;
          this.enabledPolicyIds.set(controlIds);
          this.store.setEnabledScenarioPolicyIds(cfg.enabled_ids);
          this.store.setEnabledControlPolicyIds(controlIds);
          if (!controlIds.includes(this.policy()) && controlIds.length > 0) {
            this.policy.set(controlIds[0] as PolicyName);
          }
        },
        error: () => this.enabledPolicyIds.set([]),
      });
    });
  }


  newSession() {
    this.store.newSession({
      width: this.newWidth(),
      height: this.newHeight(),
      agents: this.newAgents(),
    });
  }

  showSettings() {
    this.openSettings.emit();
  }

  showScenarioPolicy() {
    this.openScenarioPolicy.emit();
  }

  requestReset() {
    this.resetRequested.emit();
  }

  requestFinishDemoMode() {
    this.finishDemoMode.emit();
  }

  requestExitDemo() {
    this.exitDemoRequested.emit();
  }

  step(n: number) {
    this.store.step(this.currentPolicy(), n);
  }

  onPolicyChange(event: Event) {
    const target = event.target as HTMLInputElement;
    if (!target?.value) return;
    const p = target.value as PolicyName;
    this.policy.set(p);

    const sess = this.store.session();
    if (!sess) return;
    this.api.setPolicy(sess.id, p).subscribe({
      next: () => {
        this.store.setActivePolicy(p);
        this.store.previewScenarioId.set(null);
        this.store.refreshForecasts();
      },
      error: (e) => this.store.error.set(`Set policy failed: ${e.message}`),
    });
  }

  togglePlay() {
    this.store.togglePlay(this.currentPolicy(), this.speed());
  }

  onSpeedChange(ev: Event) {
    const v = +(ev.target as HTMLInputElement).value;
    this.speed.set(v);
    if (this.store.playing()) {
      // Restart play with new speed
      this.store.play(this.currentPolicy(), v);
    }
  }

  private currentPolicy(): PolicyName {
    return this.policy();
  }
}
