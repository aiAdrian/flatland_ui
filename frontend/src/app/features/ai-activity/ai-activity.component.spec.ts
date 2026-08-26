import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DirectorActivity } from '../../core/api.service';
import { SessionStore } from '../../core/session.store';
import { AiActivityComponent } from './ai-activity.component';

function activity(over: Partial<DirectorActivity> = {}): DirectorActivity {
  return {
    session_id: 's1',
    step: 40,
    source: 'search',
    totalDecisions: 12,
    totalReplans: 1,
    replans: [],
    recent: [],
    upcoming: [],
    ...over,
  };
}

describe('AiActivityComponent', () => {
  let fixture: ComponentFixture<AiActivityComponent>;
  let cmp: AiActivityComponent;
  let store: SessionStore;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [AiActivityComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(AiActivityComponent);
    cmp = fixture.componentInstance;
    store = TestBed.inject(SessionStore);
    http = TestBed.inject(HttpTestingController);
    store.interactionMode.set('director');
    store.session.set({ id: 's1' } as never);
    fixture.detectChanges();
  });

  afterEach(() => {
    store.session.set(null);
    store.notifications.set([]);
  });

  function flush(body: Partial<DirectorActivity> = {}): void {
    http.expectOne((r) => r.url.endsWith('/director/activity')).flush(activity(body));
  }

  it('says what to do instead of showing an empty box before planning', () => {
    flush({ totalDecisions: 0, totalReplans: 0, source: null });
    fixture.detectChanges();
    expect(cmp.hasAnything()).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain('Starte den autonomen Lauf');
  });

  it('names the plan provenance in plain words', () => {
    flush({ source: 'search' });
    expect(cmp.sourceLabel()).toBe('modellgeführte Suche');

    // The remaining mappings are set directly: only one poll has fired, so a
    // second flush would have no request to answer.
    cmp.activity.set(activity({ source: 'avoidance (no models)' }));
    expect(cmp.sourceLabel()).toBe('Fallback: keine Modelle installiert');
    cmp.activity.set(activity({ source: 'lines' }));
    expect(cmp.sourceLabel()).toBe('Baseline: Linienplan');
    cmp.activity.set(activity({ source: null }));
    expect(cmp.sourceLabel()).toBeNull();
  });

  it('reads a decision as what the AI did, including a hold', () => {
    expect(
      cmp.line({ kind: 'decision', step: 12, handle: 4, wait: 0, toNode: 91, optionCount: 10 }),
    ).toBe('Zug 4: weiter über Knoten 91');
    expect(
      cmp.line({ kind: 'decision', step: 12, handle: 4, wait: 3, toNode: 91, optionCount: 10 }),
    ).toBe('Zug 4: 3 min halten, weiter über Knoten 91');
    expect(cmp.detail({ kind: 'decision', step: 1, optionCount: 10 })).toBe('10 Optionen geprüft');
  });

  it('reports a train the planner could not route', () => {
    const e = { kind: 'decision' as const, step: 8, handle: 2, stuck: true };
    expect(cmp.line(e)).toBe('Zug 2: kein befahrbarer Zweig');
    // No "options weighed" claim when there was no viable branch.
    expect(cmp.detail(e)).toBeNull();
  });

  it('gives re-plans their own group so they cannot scroll out of the history', () => {
    // Measured problem: with a shared 6-entry window the single most informative
    // event of a run vanished within a few steps.
    flush({
      replans: [
        {
          kind: 'replan',
          step: 85,
          reason: 'malfunction on train 4 until t=23',
          verdict: 'continue',
          gate: 'rollout-veto',
          changed: 4,
          scoreResearch: 0.0795,
          scoreContinue: 0.0686,
        },
      ],
      recent: Array.from({ length: 6 }, (_, i) => ({
        kind: 'decision' as const,
        step: 90 + i,
        handle: i,
        wait: 0,
        toNode: 10 + i,
        optionCount: 9,
      })),
    });
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Umplanungen');
    expect(text).toContain('Störung an Zug 4');
    // The backend's "until t=23" is the malfunction counter, not the sim step —
    // dropped so it cannot read as "ended 60 steps ago" next to t=85.
    expect(text).not.toContain('until t=');
    expect(text).toContain('Simulation hat den Wechsel abgelehnt');
    // The scores are the evidence for the verdict, not decoration.
    expect(text).toContain('0.080');
    expect(text).toContain('0.069');
  });

  it('translates the re-plan trigger and passes unknown ones through', () => {
    expect(
      cmp.line({ kind: 'replan', step: 9, reason: 'malfunction on train 3 until t=16', verdict: 'research', changed: 2 }),
    ).toBe('Störung an Zug 3: 2 Zug/Züge umgeplant');
    expect(
      cmp.line({ kind: 'replan', step: 9, reason: 'weights change', verdict: 'research', changed: 1 }),
    ).toContain('Zielvorgabe geändert');
    expect(
      cmp.line({ kind: 'replan', step: 9, reason: 'something new', verdict: 'research', changed: 1 }),
    ).toContain('something new');
    expect(
      cmp.line({ kind: 'replan', step: 9, reason: null, verdict: 'research', changed: 1 }),
    ).toContain('Auslöser unbekannt');
  });

  it('distinguishes a re-plan that replaced the plan from one that was vetoed', () => {
    expect(
      cmp.line({ kind: 'replan', step: 42, reason: 'malfunction', verdict: 'research', changed: 4 }),
    ).toContain('4 Zug/Züge umgeplant');
    expect(
      cmp.line({
        kind: 'replan',
        step: 42,
        reason: 'malfunction',
        verdict: 'continue',
        gate: 'rollout-veto',
        changed: 0,
      }),
    ).toContain('Simulation hat den Wechsel abgelehnt');
    expect(
      cmp.line({ kind: 'replan', step: 42, reason: 'malfunction', verdict: 'continue', changed: 0 }),
    ).toContain('nicht besser');
  });

  it('shows disruptions as the trigger, only the real ones', () => {
    store.notifications.set([
      { id: 'n1', kind: 'error', title: 'Malfunction', message: 'Train 3 is malfunctioning (7 steps remaining).', timestamp: 10 },
      { id: 'n2', kind: 'info', title: 'Decision pending', message: 'noise', timestamp: 10 },
    ] as never);
    flush();
    fixture.detectChanges();

    expect(cmp.disruptions().length).toBe(1);
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Train 3 is malfunctioning');
    expect(text).not.toContain('noise');
  });

  it('keeps the plan ahead visually and structurally apart from history', () => {
    flush({
      recent: [{ kind: 'decision', step: 30, handle: 1, wait: 0, toNode: 5, optionCount: 8 }],
      upcoming: [{ kind: 'decision', step: 55, handle: 2, wait: 2, toNode: 9, optionCount: 8 }],
    });
    fixture.detectChanges();

    expect(cmp.recent().length).toBe(1);
    expect(cmp.upcoming().length).toBe(1);
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Zuletzt entschieden');
    expect(text).toContain('Als nächstes geplant');
    expect(fixture.nativeElement.querySelectorAll('.aa-item--planned').length).toBe(1);
  });

  it('publishes the plan next decision as the operator deadline', () => {
    // Director has no artificial countdown — nothing expires. But it is not
    // open-ended either, and "how long do I have?" had no answer on screen. The
    // plan's next committed decision is that answer, and it is diegetic.
    flush({
      step: 40,
      upcoming: [
        { kind: 'decision', step: 46, handle: 5, wait: 0, toNode: 12, optionCount: 9 },
        { kind: 'decision', step: 51, handle: 2, wait: 0, toNode: 13, optionCount: 9 },
      ],
    });
    expect(store.directorNextDecision()).toEqual({ step: 46, inSteps: 6, handle: 5 });
  });

  it('clears the deadline when the plan has nothing scheduled ahead', () => {
    flush({ step: 40, upcoming: [] });
    expect(store.directorNextDecision()).toBeNull();
  });

  it('never reports a negative lead time', () => {
    // Defensive: the poll and the step counter can disagree by a tick.
    flush({
      step: 50,
      upcoming: [{ kind: 'decision', step: 48, handle: 1, wait: 0, toNode: 3, optionCount: 4 }],
    });
    expect(store.directorNextDecision()?.inSteps).toBe(0);
  });

  it('marks holds, since waiting is the decision an operator questions most', () => {
    expect(cmp.isHold({ kind: 'decision', step: 1, wait: 2 })).toBeTrue();
    expect(cmp.isHold({ kind: 'decision', step: 1, wait: 0 })).toBeFalse();
    expect(cmp.isHold({ kind: 'replan', step: 1 })).toBeFalse();
  });

  it('collapses without losing its polling', () => {
    flush({ recent: [{ kind: 'decision', step: 30, handle: 1, wait: 0, toNode: 5, optionCount: 8 }] });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Zuletzt entschieden');

    cmp.toggleCollapsed();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('Zuletzt entschieden');
    expect(cmp.recent().length).toBe(1);
  });
});
