import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, effect, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { ApiService } from '../../core/api.service';
import { EventBusService } from '../../core/events/event-bus.service';
import { PolicyName } from '../../core/models';

/**
 * Zentrale Zeit-Steuerung der Simulation:
 * - Play / Pause / Reset / Step-Buttons
 * - Speed-Slider
 * - Time-Slider (zeigt aktuelle Position, in Phase F1 auch Reverse-Replay)
 *
 * Emittiert SIMULATION_TIME_CHANGED bei Bewegung.
 */
@Component({
  selector: 'app-simulation-slider',
  standalone: true,
  templateUrl: './simulation-slider.component.html',
  styleUrl: './simulation-slider.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class SimulationSliderComponent {
  store = inject(SessionStore);
  api = inject(ApiService);
  bus = inject(EventBusService);

  // local UI state
  speed = signal(5);
  policy = signal<PolicyName>('deadlock_avoidance');

  // Sync simulationTime im Store mit elapsedSteps wenn Sim laeuft
  constructor() {
    effect(() => {
      const elapsed = this.store.elapsedSteps();
      this.store.simulationTime.set(elapsed);
    });
  }

  pct = computed(() => {
    const max = Math.max(1, this.store.maxSteps());
    return (this.store.elapsedSteps() / max) * 100;
  });

  togglePlay() {
    if (!this.store.session()) return;
    if (this.store.playing()) {
      this.api.pause(this.store.session()!.id).subscribe();
    } else {
      this.api.play(this.store.session()!.id, {
        policy: this.policy(),
        speed: this.speed(),
      }).subscribe();
    }
  }

  reset() {
    const sess = this.store.session();
    if (!sess) return;
    this.api.reset(sess.id).subscribe();
  }

  step(n: number) {
    const sess = this.store.session();
    if (!sess) return;
    this.api.step(sess.id, this.policy(), n).subscribe();
  }

  onSpeedChange(event: Event) {
    const v = +(event.target as HTMLInputElement).value;
    this.speed.set(v);
    if (this.store.playing()) {
      this.api.play(this.store.session()!.id, {
        policy: this.policy(),
        speed: v,
      }).subscribe();
    }
  }

  onTimeChange(event: Event) {
    const v = +(event.target as HTMLInputElement).value;
    this.store.simulationTime.set(v);
    this.bus.emit({ type: 'SIMULATION_TIME_CHANGED', time: v });
    // Phase F1: hier waere Reverse-Replay - aktuell nur visuelle Anzeige
  }

  onPolicyChange(p: PolicyName) {
    this.policy.set(p);
  }

  formatTime(steps: number): string {
    // einfaches mapping: 1 step = 1 sek
    const mm = Math.floor(steps / 60).toString().padStart(2, '0');
    const ss = Math.floor(steps % 60).toString().padStart(2, '0');
    return `${mm}:${ss}`;
  }
}
