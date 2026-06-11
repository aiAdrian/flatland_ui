import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, effect, inject, signal } from '@angular/core';
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
  store = inject(SessionStore);
  private api = inject(ApiService);
  newWidth = signal(50);
  newHeight = signal(20);
  newAgents = signal(3);

  policy = signal<PolicyName>('deadlock_avoidance');
  enabledPolicyIds = signal<string[]>([]);
  speed = signal(5);

  readonly selectablePolicies = computed(() => {
    const enabled = new Set(this.enabledPolicyIds());
    return this.store.availablePolicies().filter((p) => enabled.has(p.id));
  });

  constructor() {
    // When backend session-policy changes (e.g. via scenario Confirm),
    // mirror it into the local toolbar selection so the radios reflect it.
    effect(() => {
      const active = this.store.activePolicy();
      if (active && active !== this.policy()) {
        this.policy.set(active);
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
          this.enabledPolicyIds.set(cfg.enabled_ids);
          if (!cfg.enabled_ids.includes(this.policy()) && cfg.enabled_ids.length > 0) {
            this.policy.set(cfg.enabled_ids[0] as PolicyName);
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

  reset() {
    this.store.reset();
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
