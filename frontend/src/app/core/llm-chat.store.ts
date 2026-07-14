import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';

import { ApiService, ChatTurn } from './api.service';

/** The backend grounds each question in the repo docs and appends its own
 *  retrieval instructions to this prompt. The panel still has no access to the
 *  live session — see docs/reference/llm-setup.md (Design decisions → Known
 *  limits) before wiring it into the simulation. */
const SYSTEM_PROMPT =
  'You are an assistant embedded in the Flatland railway dispatcher HMI, a research ' +
  'playground for human-AI teaming. Answer briefly and plainly. If you are asked ' +
  'about the current simulation, say that you cannot see it yet.';

/** A transcript turn plus display-only metadata (not resent to the backend). */
export interface ChatDisplayTurn extends ChatTurn {
  sources?: string[];
}

/**
 * Chat transcript for the LLM panel.
 *
 * Root-provided (not part of SessionStore) so the conversation survives the panel
 * being collapsed, remounted or moved between layout zones — the same reason
 * LearningStore is separate. It is also independent of the Flatland session:
 * clearing or restarting a run does not wipe the chat.
 */
@Injectable({ providedIn: 'root' })
export class LlmChatStore {
  private api = inject(ApiService);

  readonly messages = signal<ChatDisplayTurn[]>([]);
  readonly pending = signal(false);
  /** Provider-side failure (model down, out of tokens, …), shown in the panel. */
  readonly error = signal<string | null>(null);

  /** null = not probed yet. */
  readonly reachable = signal<boolean | null>(null);
  readonly model = signal<string | null>(null);
  readonly provider = signal<string | null>(null);
  readonly healthDetail = signal<string | null>(null);

  readonly isEmpty = computed(() => this.messages().length === 0);
  readonly canSend = computed(() => !this.pending());

  /** Cheap liveness probe — spends no tokens. Safe to call on every panel mount. */
  checkHealth(): void {
    this.api.llmHealth().subscribe({
      next: (health) => {
        this.reachable.set(health.reachable);
        this.model.set(health.model);
        this.provider.set(health.provider);
        this.healthDetail.set(health.detail ?? null);
      },
      error: () => {
        // The backend itself is unreachable (not just the model).
        this.reachable.set(false);
        this.healthDetail.set('backend not reachable — is it running on :8000?');
      },
    });
  }

  send(text: string): void {
    const content = text.trim();
    if (!content || this.pending()) return;

    // Optimistically show the user's turn, then send the whole transcript: the
    // backend is stateless, so the model only has the context we resend.
    const history: ChatDisplayTurn[] = [...this.messages(), { role: 'user', content }];
    this.messages.set(history);
    this.pending.set(true);
    this.error.set(null);

    const transcript: ChatTurn[] = history.map(({ role, content: c }) => ({ role, content: c }));
    this.api.llmChat(transcript, SYSTEM_PROMPT).subscribe({
      next: (response) => {
        this.messages.update((turns) => [
          ...turns,
          { role: 'assistant', content: response.text, sources: response.sources ?? undefined },
        ]);
        this.model.set(response.model);
        this.provider.set(response.provider);
        this.reachable.set(true);
        this.pending.set(false);
      },
      error: (err: HttpErrorResponse) => {
        // The backend returns 502 + a human-readable detail when the model fails.
        this.error.set(String(err.error?.detail ?? err.message ?? 'request failed'));
        this.pending.set(false);
        this.reachable.set(false);
      },
    });
  }

  clear(): void {
    this.messages.set([]);
    this.error.set(null);
  }
}
