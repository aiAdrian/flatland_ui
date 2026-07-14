import { CommonModule } from '@angular/common';
import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  ElementRef,
  HostBinding,
  Input,
  OnInit,
  ViewChild,
  effect,
  inject,
  signal,
} from '@angular/core';

import { LlmChatStore } from '../../core/llm-chat.store';

/**
 * Chat window for the local LLM.
 *
 * The purpose is to make the LLM seam (docs/reference/llm-setup.md) testable from
 * the running UI: pick a provider in backend/.env, open this panel, talk to it.
 * It calls POST /llm/chat, so it works unchanged against the local Ollama model,
 * Claude, or a cloud-hosted endpoint — the panel never knows which.
 */
@Component({
  selector: 'app-llm-chat-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './llm-chat-panel.component.html',
  styleUrl: './llm-chat-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class LlmChatPanelComponent implements OnInit {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  readonly chat = inject(LlmChatStore);
  readonly draft = signal('');

  @ViewChild('scroller') private scroller?: ElementRef<HTMLElement>;

  constructor() {
    // Keep the newest turn in view as the transcript grows.
    effect(() => {
      this.chat.messages();
      this.chat.pending();
      queueMicrotask(() => {
        const el = this.scroller?.nativeElement;
        if (el) el.scrollTop = el.scrollHeight;
      });
    });
  }

  ngOnInit(): void {
    // Tells the user *why* nothing works, before they type into a dead panel.
    this.chat.checkHealth();
  }

  onInput(event: Event): void {
    this.draft.set((event.target as HTMLInputElement).value);
  }

  send(): void {
    const text = this.draft().trim();
    if (!text || this.chat.pending()) return;
    this.chat.send(text);
    this.draft.set('');
  }

  clear(): void {
    this.chat.clear();
    this.draft.set('');
  }
}
