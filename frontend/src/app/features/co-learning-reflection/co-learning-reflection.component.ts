import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, effect, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { AgentDTO } from '../../core/models';

interface ReflectionQuestion {
  key: string;
  text: string;
  /** Supportive-AI mode this prompt embodies (Waefler et al. 2025). */
  mode: 'MR' | 'AM' | 'TP';
}

/**
 * Co-Learning reflection (WP 3.3), grounded in Hamouche et al.,
 * "A methodical approach to AI-supported human learning" (AI4REALNET / FHNW):
 * Kolb phase 2 (reflection), Endsley decision-making level, using the
 * Supportive-AI support modes — here Mirroring [MR] (a statistical recap that
 * reflects the operator's own behaviour back) and Animation [AM] (Socratic
 * prompts). Frontend-only; answers stay in component state for now.
 */
@Component({
  selector: 'app-co-learning-reflection',
  standalone: true,
  templateUrl: './co-learning-reflection.component.html',
  styleUrl: './co-learning-reflection.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class CoLearningReflectionComponent {
  store = inject(SessionStore);

  readonly dismissed = signal(false);

  // ── Mirroring [MR]: the operator's own run, reflected back ──────────
  readonly interventions = computed(() => this.store.coLearningFeedback());
  readonly interventionCount = computed(() => this.interventions().length);
  /** Interventions made while an AI recommendation was on the table. */
  readonly overridesDespiteAi = computed(() =>
    this.interventions().filter((e) => e.aiSuggestion != null).length,
  );

  private isMalfunctioning(a: AgentDTO): boolean {
    return !!a.is_malfunctioning
      || (a.malfunction_remaining ?? 0) > 0
      || String(a.state ?? '').toUpperCase().includes('MALFUNCTION');
  }

  readonly total = computed(() => this.store.agents().length);
  readonly arrived = computed(() => this.store.agents().filter((a) => String(a.state).toUpperCase() === 'DONE').length);
  readonly totalDelay = computed(() => this.store.agents().reduce((s, a) => s + Math.max(0, a.delay ?? 0), 0));
  readonly malfunctions = computed(() => this.store.agents().filter((a) => this.isMalfunctioning(a)).length);

  // ── Animation [AM]: Socratic prompts (context-aware) ────────────────
  readonly questions = computed<ReflectionQuestion[]>(() => {
    const n = this.interventionCount();
    return [
      {
        key: 'cues',
        mode: 'AM',
        text: n > 0
          ? `You intervened ${n} time${n === 1 ? '' : 's'}. Which signals made you step in?`
          : 'You let the AI run without intervening. Which signals were you watching?',
      },
      { key: 'expected', mode: 'TP', text: 'Where did the outcome differ from what you expected — and why?' },
      { key: 'rule', mode: 'AM', text: 'What if-then rule would you draw for a similar situation next time?' },
      { key: 'trust', mode: 'MR', text: 'When did you trust the AI, and when did you override it? What drove that?' },
      { key: 'success', mode: 'TP', text: 'How would you measure whether this run went well?' },
    ];
  });

  /** Only the first N questions are shown (Samira: 2 of 5), configurable. */
  readonly visibleQuestions = computed<ReflectionQuestion[]>(() =>
    this.questions().slice(0, this.store.reflectionQuestionLimit()),
  );

  readonly answers = signal<Record<string, string>>({});

  private static readonly STORAGE_PREFIX = 'flatland_colearning_reflection_';

  constructor() {
    // Load any persisted answers when the session becomes known / changes.
    let lastKey: string | null = null;
    effect(() => {
      const key = this.storageKey();
      if (key === lastKey) return;
      lastKey = key;
      this.answers.set(key ? this.loadAnswers(key) : {});
    });
  }

  private storageKey(): string | null {
    const id = this.store.session()?.id;
    return id ? CoLearningReflectionComponent.STORAGE_PREFIX + id : null;
  }

  private loadAnswers(key: string): Record<string, string> {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  private persistAnswers(value: Record<string, string>): void {
    const key = this.storageKey();
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // localStorage may be unavailable (private mode / tests).
    }
  }

  modeLabel(mode: 'MR' | 'AM' | 'TP'): string {
    return mode === 'MR' ? 'Mirroring' : mode === 'AM' ? 'Animation' : 'Transparency';
  }

  setAnswer(key: string, value: string): void {
    this.answers.update((a) => {
      const next = { ...a, [key]: value };
      this.persistAnswers(next);
      return next;
    });
  }

  finish(): void {
    this.dismissed.set(true);
  }
}
