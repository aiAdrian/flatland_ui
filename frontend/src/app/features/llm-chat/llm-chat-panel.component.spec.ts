import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { LlmChatPanelComponent } from './llm-chat-panel.component';

describe('LlmChatPanelComponent', () => {
  let fixture: ComponentFixture<LlmChatPanelComponent>;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LlmChatPanelComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(LlmChatPanelComponent);
    http = TestBed.inject(HttpTestingController);
    fixture.componentInstance.embedded = true;
  });

  afterEach(() => http.verify());

  /** Probe health on mount, so the panel can say *why* it's dead. */
  function flushHealth(reachable = true): void {
    fixture.detectChanges();
    http.expectOne((r) => r.url.endsWith('/llm/health')).flush({
      provider: 'ollama',
      model: 'qwen3.5:4b',
      reachable,
      detail: reachable ? null : 'Connection refused',
    });
    fixture.detectChanges();
  }

  function type(text: string): void {
    const input: HTMLInputElement = fixture.nativeElement.querySelector('.llm-chat__input');
    input.value = text;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  it('shows which model is live', () => {
    flushHealth();
    expect(fixture.nativeElement.textContent).toContain('qwen3.5:4b');
  });

  it('sends the message and renders the reply', () => {
    flushHealth();
    type('What does a dispatcher do?');
    fixture.nativeElement.querySelector('sbb-button').dispatchEvent(new Event('click'));
    fixture.detectChanges();

    const req = http.expectOne((r) => r.url.endsWith('/llm/chat'));
    expect(req.request.body.messages).toEqual([
      { role: 'user', content: 'What does a dispatcher do?' },
    ]);

    req.flush({ text: 'They route trains.', provider: 'ollama', model: 'qwen3.5:4b' });
    fixture.detectChanges();

    const rendered = fixture.nativeElement.textContent;
    expect(rendered).toContain('What does a dispatcher do?');
    expect(rendered).toContain('They route trains.');
  });

  it('resends the whole transcript so the model has context', () => {
    flushHealth();

    type('first');
    fixture.componentInstance.send();
    http.expectOne((r) => r.url.endsWith('/llm/chat'))
      .flush({ text: 'reply one', provider: 'ollama', model: 'qwen3.5:4b' });
    fixture.detectChanges();

    type('second');
    fixture.componentInstance.send();
    const req = http.expectOne((r) => r.url.endsWith('/llm/chat'));

    // The backend is stateless — a follow-up must carry the history with it.
    expect(req.request.body.messages).toEqual([
      { role: 'user', content: 'first' },
      { role: 'assistant', content: 'reply one' },
      { role: 'user', content: 'second' },
    ]);
    req.flush({ text: 'reply two', provider: 'ollama', model: 'qwen3.5:4b' });
  });

  it('shows the reason when the model fails, instead of failing silently', () => {
    flushHealth();
    type('hi');
    fixture.componentInstance.send();

    http.expectOne((r) => r.url.endsWith('/llm/chat')).flush(
      { detail: "ollama: model 'qwen3.5:4b' returned no text (finish_reason=length)" },
      { status: 502, statusText: 'Bad Gateway' },
    );
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.llm-chat__error').textContent)
      .toContain('returned no text');
  });

  it('tells the user when no model is reachable', () => {
    flushHealth(false);
    expect(fixture.nativeElement.querySelector('.llm-chat__offline').textContent)
      .toContain('Connection refused');
  });
});
