import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { LearningStore } from '../../core/learning-store.service';
import { OperatorModelService, OperatorProfile } from '../../core/operator-model.service';
import { SessionStore } from '../../core/session.store';
import { ShiftReviewComponent } from './shift-review.component';

function profileFixture(over: Partial<OperatorProfile> = {}): OperatorProfile {
  return {
    operatorId: 'operator1',
    isWarm: false,
    priorSessions: 0,
    evidenceCount: 3,
    passiveCount: 0,
    trustRatio: 0,
    valueWeights: {},
    valueProfile: {
      dominant: 'connection',
      label: 'Connection-first',
      dominantPct: 67,
      distribution: [],
      total: 3,
    },
    confirmedLearnings: [],
    optionPresentation: 'recommend',
    suggestedDirectorWeights: { punctuality: 0.83, connections: 1.33, stability: 0.83 },
    ...over,
  };
}

describe('ShiftReviewComponent', () => {
  let fixture: ComponentFixture<ShiftReviewComponent>;
  let cmp: ShiftReviewComponent;
  let store: SessionStore;
  let model: OperatorModelService;
  let learning: LearningStore;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ShiftReviewComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(ShiftReviewComponent);
    cmp = fixture.componentInstance;
    store = TestBed.inject(SessionStore);
    model = TestBed.inject(OperatorModelService);
    learning = TestBed.inject(LearningStore);
    learning.clear();
    store.interactionMode.set('director');
    store.state.set({
      elapsed_steps: 200,
      agents: [],
    } as never);
  });

  afterEach(() => {
    learning.clear();
    model.profile.set(null);
    store.clearDecisionLog();
    store.state.set(null);
    store.directorAiWorkload.set(null);
  });

  function withAgents(): void {
    store.state.set({
      elapsed_steps: 200,
      agents: [
        { handle: 0, state: 'DONE', delay: 0 },
        { handle: 1, state: 'DONE', delay: 0 },
        { handle: 2, state: 'MOVING', delay: 12 },
        { handle: 3, state: 'MALFUNCTION', delay: 30, is_malfunctioning: true },
      ],
    } as never);
  }

  function chooseStrategy(axis: 'connection' | 'punctuality', response: 'yes' | 'once' | 'no' = 'yes'): void {
    store.recordStrategyChoice({
      title: axis === 'connection' ? 'Anschlüsse halten' : 'Verspätung minimieren',
      ident: axis === 'connection' ? 'B' : 'A',
      axis,
      tradedAway: '31 Punkte Pünktlichkeit',
      hypothesis: `Bei Zielkonflikten priorisierst du ${axis}.`,
    });
    store.answerStrategyReflection(response, 'Schützt Anschluss');
  }

  it('reports the closing balance from the fleet state', () => {
    withAgents();
    fixture.detectChanges();

    expect(cmp.kpis()).toEqual({
      total: 4,
      arrived: 2,
      delayed: 2,
      malfunctions: 1,
      totalDelay: 42,
    });
    expect(cmp.arrivedPct()).toBe(50);
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('2/4 Züge am Ziel (50 %)');
  });

  it('says the AI ran alone when no goal was ever set', () => {
    withAgents();
    store.directorAiWorkload.set({ decisions: 64, replans: 2 });
    fixture.detectChanges();

    expect(cmp.review().ranUnattended).toBeTrue();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('kein Ziel gesetzt');
    // The planner's own workload is part of the balance, not a footnote.
    expect(text).toContain('64');
    expect(text).toContain('umgeplant');
  });

  it('lists the moments with the reason, the price and the scoring trace', () => {
    withAgents();
    chooseStrategy('connection');
    fixture.detectChanges();

    const r = cmp.review();
    expect(r.ranUnattended).toBeFalse();
    expect(r.moments.length).toBe(1);

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Worüber es sich zu sprechen lohnt');
    expect(text).toContain('Schützt Anschluss');
    expect(text).toContain('31 Punkte Pünktlichkeit');
    // Selection is a heuristic, so it has to be arguable.
    expect(text).toContain('Ausgewählt weil');
    expect(text).toContain('als Regel bestätigt');
  });

  it('shows a confirmed preference as learned', () => {
    withAgents();
    chooseStrategy('connection');
    fixture.detectChanges();

    expect(cmp.review().confirmed.length).toBe(1);
    expect(fixture.nativeElement.textContent).toContain('Was ich über dich gelernt habe');
    expect(fixture.nativeElement.textContent).toContain('bestätigt');
  });

  it('keeps a one-off apart instead of presenting it as a rule', () => {
    withAgents();
    chooseStrategy('connection', 'once');
    fixture.detectChanges();

    const r = cmp.review();
    expect(r.confirmed.length).toBe(0);
    expect(r.oneOffs.length).toBe(1);
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('als Einzelfall markiert');
    expect(text).toContain('nicht');
  });

  it('asks about two different priorities rather than resolving them', () => {
    withAgents();
    chooseStrategy('connection');
    chooseStrategy('connection');
    chooseStrategy('punctuality');
    fixture.detectChanges();

    expect(cmp.review().contradiction).not.toBeNull();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('2× Anschluss');
    expect(text).toContain('Was war in der Lage anders');
  });

  it('reports the inferred weights only once they carry a preference', () => {
    withAgents();
    model.profile.set(profileFixture());
    fixture.detectChanges();
    expect(cmp.weights()).not.toBeNull();
    expect(fixture.nativeElement.textContent).toContain('1.33');

    model.profile.set(
      profileFixture({ suggestedDirectorWeights: { punctuality: 1, connections: 1, stability: 1 } }),
    );
    fixture.detectChanges();
    // Neutral weights say nothing; claiming them as a finding would be noise.
    expect(cmp.weights()).toBeNull();
  });

  it('names the value pattern with its evidence base', () => {
    withAgents();
    model.profile.set(profileFixture());
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Connection-first');
    expect(text).toContain('67 %');
    expect(text).toContain('3 bewussten Entscheidungen');
  });

  it('states that it is rule-based, not a language model', () => {
    withAgents();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('kein Sprachmodell');
  });

  // ── carrying the shift over ───────────────────────────────────────────────
  describe('saving the preferences', () => {
    let http: HttpTestingController;

    beforeEach(() => {
      http = TestBed.inject(HttpTestingController);
    });

    afterEach(() => {
      store.shiftEnded.set(false);
      http.verify();
    });

    it('folds the shift into the long-term profile exactly once', () => {
      withAgents();
      chooseStrategy('connection');
      model.profile.set(profileFixture({ evidenceCount: 1 }));
      fixture.detectChanges();

      const btn: HTMLButtonElement = fixture.nativeElement.querySelector('.sv-btn--primary');
      expect(btn.textContent).toContain('Präferenzen für die nächste Schicht speichern');
      btn.click();
      // A double click must not count the shift twice.
      cmp.savePreferences();

      const req = http.expectOne((r) => r.url.endsWith('/end-session'));
      req.flush(profileFixture({ priorSessions: 1, isWarm: true, evidenceCount: 0 }));
      fixture.detectChanges();

      expect(cmp.saveState()).toBe('saved');
      const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
      expect(text).toContain('Gespeichert');
      // The proof it stuck, and the promise kept modest.
      expect(text).toContain('1 abgeschlossene(n) Schicht(en)');
      expect(text).toContain('Startvorschlag');
    });

    it('says what is carried over and what is not, before the click', () => {
      withAgents();
      chooseStrategy('connection', 'once');
      model.profile.set(profileFixture({ evidenceCount: 2 }));
      fixture.detectChanges();

      const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
      // Counted from this shift's decision log, not from the backend profile:
      // that one accumulates signals across sessions in the same process and
      // reported six for a shift with one goal choice.
      expect(cmp.decisionsThisShift()).toBe(1);
      expect(text).toContain('1 Zielentscheidung(en) dieser Schicht');
      expect(text).toContain('nur diesmal');
      expect(text).toContain('startet die nächste Schicht kalt');
      // First shift: no claim about earlier ones.
      expect(text).toContain('deine erste');
    });

    it('ignores profile evidence carried in from an earlier session', () => {
      // The backend keys raw signals by operator, not by session, so its count
      // is not a statement about this shift.
      withAgents();
      chooseStrategy('connection');
      model.profile.set(profileFixture({ evidenceCount: 9 }));
      fixture.detectChanges();

      expect(cmp.decisionsThisShift()).toBe(1);
      expect(fixture.nativeElement.textContent).not.toContain('9 ');
    });

    it('counts finished shifts, not a rule confirmed minutes ago', () => {
      // `isWarm` also turns true from this shift's own confirmed rule, which
      // produced "es enthält bereits 0 frühere Schicht(en)".
      withAgents();
      chooseStrategy('connection');
      model.profile.set(profileFixture({ isWarm: true, priorSessions: 0, evidenceCount: 1 }));
      fixture.detectChanges();
      expect(cmp.wasWarm()).toBeFalse();

      model.profile.set(profileFixture({ isWarm: true, priorSessions: 3, evidenceCount: 1 }));
      fixture.detectChanges();
      expect(cmp.wasWarm()).toBeTrue();
      expect(fixture.nativeElement.textContent).toContain('3 frühere Schicht(en)');
    });

    it('reports a failed save instead of claiming success', () => {
      withAgents();
      chooseStrategy('connection');
      model.profile.set(profileFixture({ evidenceCount: 1 }));
      fixture.detectChanges();

      cmp.savePreferences();
      http.expectOne((r) => r.url.endsWith('/end-session')).error(
        new ProgressEvent('error'),
        { status: 500, statusText: 'boom' },
      );
      fixture.detectChanges();

      expect(cmp.saveState()).toBe('error');
      expect(fixture.nativeElement.textContent).toContain('Nichts wurde übernommen');
    });

    it('credits a rule from an earlier shift instead of denying it', () => {
      // "Noch keine bestätigte Präferenz" above "Muster: Connection-first" read
      // as a contradiction, and contradicted the badge on the tiles.
      withAgents();
      model.profile.set(
        profileFixture({
          priorSessions: 1,
          isWarm: true,
          evidenceCount: 0,
          confirmedLearnings: [
            { statement: 'Bei Zielkonflikten priorisierst du Anschlüsse.', targetValue: 'connection' },
          ],
        }),
      );
      fixture.detectChanges();

      const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
      expect(text).not.toContain('Noch keine bestätigte Präferenz');
      expect(text).toContain('früher bestätigt');
      expect(text).toContain('Bei Zielkonflikten priorisierst du Anschlüsse.');
      // And the pattern says where it comes from.
      expect(cmp.patternIsCarried()).toBeTrue();
      expect(text).toContain('aus früheren Schichten');
    });

    it('offers no save when there is nothing to carry over', () => {
      withAgents();
      fixture.detectChanges();

      expect(cmp.hasCarryOver()).toBeFalse();
      expect(fixture.nativeElement.querySelector('.sv-btn--primary')).toBeNull();
      expect(fixture.nativeElement.textContent).toContain('nichts zu übernehmen');
    });
  });

  describe('leaving the review', () => {
    it('lets a manually ended shift be resumed', () => {
      withAgents();
      store.shiftEnded.set(true);
      fixture.detectChanges();

      expect(cmp.canReopen()).toBeTrue();
      cmp.reopenShift();
      expect(store.shiftEnded()).toBeFalse();
      expect(store.shiftReviewOpen()).toBeFalse();
    });

    it('offers no way back when the episode really ended', () => {
      store.state.set({
        elapsed_steps: 400,
        episode_done: true,
        agents: [],
      } as never);
      fixture.detectChanges();
      expect(cmp.canReopen()).toBeFalse();
    });
  });
});
