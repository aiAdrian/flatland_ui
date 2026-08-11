import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { OperatorModelService, OperatorProfile, ValueAxis } from '../../core/operator-model.service';
import { LearningStore } from '../../core/learning-store.service';
import { SessionStore } from '../../core/session.store';
import { StrategyReflectionComponent } from './strategy-reflection.component';

function profileFixture(dominant: ValueAxis | null, evidenceCount = 5): OperatorProfile {
  return {
    operatorId: 'operator1',
    isWarm: true,
    priorSessions: 2,
    evidenceCount,
    passiveCount: 0,
    trustRatio: 0.5,
    valueWeights: {},
    valueProfile: { dominant, label: '—', dominantPct: 70, distribution: [], total: evidenceCount },
    confirmedLearnings: [],
    optionPresentation: 'recommend',
    suggestedDirectorWeights: { punctuality: 1, connections: 1, stability: 1 },
  };
}

describe('StrategyReflectionComponent', () => {
  let fixture: ComponentFixture<StrategyReflectionComponent>;
  let cmp: StrategyReflectionComponent;
  let store: SessionStore;
  let model: OperatorModelService;
  let learning: LearningStore;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [StrategyReflectionComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(StrategyReflectionComponent);
    cmp = fixture.componentInstance;
    store = TestBed.inject(SessionStore);
    model = TestBed.inject(OperatorModelService);
    http = TestBed.inject(HttpTestingController);
    learning = TestBed.inject(LearningStore);
    // Confirmed preferences persist to localStorage by design, so they survive
    // between specs; start each one from a clean slate.
    learning.clear();
    store.interactionMode.set('director');
  });

  afterEach(() => {
    store.dismissStrategyReflection();
    store.clearDecisionLog();
    learning.clear();
    model.profile.set(null);
  });

  function choose(axis: 'connection' | 'punctuality' | 'stability' = 'connection'): void {
    store.recordStrategyChoice({
      title: 'Anschlüsse halten',
      ident: 'B',
      axis,
      tradedAway: '-31 Pünktlichkeit',
      hypothesis: 'Bei Zielkonflikten priorisierst du Anschlüsse — auch um den Preis von -31 Pünktlichkeit.',
    });
  }

  it('stays invisible until a strategy is committed', () => {
    fixture.detectChanges();
    expect(cmp.pending()).toBeNull();
    expect(fixture.nativeElement.textContent.trim()).toBe('');
  });

  it('mirrors the choice back together with its price', () => {
    choose();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('B · Anschlüsse halten');
    expect(text).toContain('-31 Pünktlichkeit');
    expect(text).toContain('Bei Zielkonflikten priorisierst du Anschlüsse');
  });

  it('logs the choice as deliberate evidence with an explicit axis', () => {
    choose();
    const entry = store.decisionLog().at(-1)!;
    expect(entry.action).toBe('strategy');
    expect(entry.accountableOwner).toBe('human');
    expect(entry.valueAxis).toBe('connection');
    expect(entry.tradedAway).toBe('-31 Pünktlichkeit');
  });

  it('promotes a confirmed hypothesis to a learning record', () => {
    choose();
    cmp.answer('yes');
    http.expectOne((r) => r.url.includes('/operator/')).flush({});

    const entry = store.decisionLog().at(-1)!;
    expect(entry.hypothesisResponse).toBe('yes');
    expect(store.confirmedPreferenceCount()).toBe(1);
    expect(cmp.pending()).toBeNull();
  });

  it('keeps a one-off out of the confirmed preferences', () => {
    choose();
    cmp.answer('once');
    http.expectOne((r) => r.url.includes('/operator/')).flush({});

    const entry = store.decisionLog().at(-1)!;
    expect(entry.hypothesisResponse).toBe('once');
    // Recorded, but explicitly not a rule the AI may generalise.
    expect(store.confirmedPreferenceCount()).toBe(0);
  });

  it('records nothing beyond the decision when the hypothesis is rejected', () => {
    choose();
    cmp.answer('no');
    http.expectOne((r) => r.url.includes('/operator/')).flush({});

    expect(store.decisionLog().at(-1)!.hypothesisResponse).toBe('no');
    expect(store.confirmedPreferenceCount()).toBe(0);
  });

  it('asks about a choice that contradicts the carried-over profile', () => {
    model.profile.set(profileFixture('punctuality'));
    choose('connection');
    fixture.detectChanges();

    expect(cmp.contradiction()).toEqual({ was: 'punctuality', now: 'connection' });
    const text = fixture.nativeElement.textContent as string;
    // Framed as a question, not a correction.
    expect(text).toContain('soll ich meine Annahme über dich ändern?');
  });

  it('confirms a choice that matches the profile instead of questioning it', () => {
    model.profile.set(profileFixture('connection'));
    choose('connection');
    fixture.detectChanges();

    expect(cmp.contradiction()).toBeNull();
    expect(cmp.consistent()).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Passt zu deinem bisherigen Muster');
  });

  it('stays quiet about patterns while the profile is too thin to claim one', () => {
    model.profile.set(profileFixture('punctuality', 2));
    choose('connection');
    fixture.detectChanges();

    expect(cmp.profileAxis()).toBeNull();
    expect(cmp.contradiction()).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('Bisher hast du');
  });

  it('offers reason chips and free text, like the override prompt does', () => {
    choose();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Warum jetzt?');
    expect(text).toContain('Schützt Anschluss');
    expect(text).toContain('Eigener Grund');
    // Optional on purpose: answering without a reason stays possible, it is just
    // weaker evidence.
    expect(text).toContain('optional');
    expect(cmp.hasReason()).toBeFalse();
  });

  it('records the stated situation as the condition of the preference', () => {
    choose();
    cmp.toggleChip('connection');
    cmp.toggleChip('disruption');
    cmp.setNote('Umleitung über Nord war frei');
    expect(cmp.hasReason()).toBeTrue();

    cmp.answer('yes');
    http.expectOne((r) => r.url.includes('/operator/')).flush({});

    const entry = store.decisionLog().at(-1)!;
    expect(entry.rationale).toContain('Anschlüsse halten');
    expect(entry.rationale).toContain('Schützt Anschluss');
    expect(entry.rationale).toContain('Störung im Netz');
    expect(entry.rationale).toContain('Umleitung über Nord war frei');
  });

  it('keeps a chip label the axis mapping understands', () => {
    // 'Schützt Anschluss' is the same label the override prompt uses, so
    // RATIONALE_AXIS_BY_LABEL keeps resolving it to the connection axis.
    expect(cmp.chips.map((c) => c.label)).toContain('Schützt Anschluss');
  });

  it('resets the reason after answering, so it cannot leak into the next choice', () => {
    choose();
    cmp.toggleChip('connection');
    cmp.answer('once');
    http.expectOne((r) => r.url.includes('/operator/')).flush({});

    expect(cmp.hasReason()).toBeFalse();
    expect(cmp.isSelected('connection')).toBeFalse();
  });

  it('leaves the choice logged when the prompt is dismissed unanswered', () => {
    choose();
    const seq = store.decisionLog().at(-1)!.seq;
    cmp.dismiss();
    expect(cmp.pending()).toBeNull();
    const entry = store.decisionLog().find((e) => e.seq === seq)!;
    expect(entry).toBeTruthy();
    expect(entry.hypothesisResponse).toBeUndefined();
  });
});
