import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';

import { SessionStore } from './session.store';
import { CoordinatedDecision } from './decision-log';

/**
 * The one seam both Combined Actions variants write through. What is asserted
 * here is the *format*, not either widget: if the two surfaces ever record the
 * same kind of choice differently, a study comparing them compares its own
 * bookkeeping instead of the interfaces.
 */
function decision(over: Partial<CoordinatedDecision> = {}): CoordinatedDecision {
  return {
    variant: 'packages',
    label: 'Action A',
    aiOrder: ['IC_703', 'ICE_42', 'RE_18'],
    appliedOrder: ['IC_703', 'ICE_42', 'RE_18'],
    handles: [0, 1, 2],
    aiImpact: { delayReductionMin: 14, transfersKept: 2, transfersTotal: 3 },
    appliedImpact: { delayReductionMin: 14, transfersKept: 2, transfersTotal: 3 },
    committed: false,
    ...over,
  };
}

describe('recordCoordinatedAction', () => {
  let store: SessionStore;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(SessionStore);
  });

  it('records taking the AI order unchanged as an acceptance', () => {
    store.recordCoordinatedAction(decision());
    const entry = store.decisionLog().at(-1)!;

    expect(entry.action).toBe('accept');
    expect(entry.accountableOwner).toBe('human');
  });

  it('records a reordered sequence as an override', () => {
    store.recordCoordinatedAction(
      decision({ appliedOrder: ['ICE_42', 'IC_703', 'RE_18'] }),
    );
    expect(store.decisionLog().at(-1)!.action).toBe('override');
  });

  it('keeps both orders, so the log can answer whose answer was applied', () => {
    store.recordCoordinatedAction(
      decision({ appliedOrder: ['RE_18', 'IC_703', 'ICE_42'] }),
    );
    const c = store.decisionLog().at(-1)!.coordinated!;

    expect(c.aiOrder).toEqual(['IC_703', 'ICE_42', 'RE_18']);
    expect(c.appliedOrder).toEqual(['RE_18', 'IC_703', 'ICE_42']);
  });

  it('is not about one train, and does not pretend to be', () => {
    store.recordCoordinatedAction(decision());
    // Same convention `action: 'strategy'` uses: -1 keeps the per-train schema
    // intact without claiming a handle was the subject.
    expect(store.decisionLog().at(-1)!.handle).toBe(-1);
  });

  it('says the order was not committed, because no planner ran', () => {
    store.recordCoordinatedAction(decision());
    expect(store.decisionLog().at(-1)!.coordinated!.committed).toBeFalse();
  });

  it('carries the variant, so records from the two surfaces stay tellable apart', () => {
    store.recordCoordinatedAction(decision({ variant: 'packages' }));
    store.recordCoordinatedAction(
      decision({
        variant: 'package',
        aiImpact: { delayReductionMin: 12, affectedTrains: 6 },
        appliedImpact: { delayReductionMin: 9, affectedTrains: 6 },
      }),
    );
    const log = store.decisionLog();

    expect(log.at(-2)!.coordinated!.variant).toBe('packages');
    expect(log.at(-1)!.coordinated!.variant).toBe('package');
    // Each surface reports what it measures; the absent field is absent rather
    // than a fabricated zero.
    expect(log.at(-2)!.coordinated!.appliedImpact.transfersTotal).toBe(3);
    expect(log.at(-1)!.coordinated!.appliedImpact.transfersTotal).toBeUndefined();
    expect(log.at(-1)!.coordinated!.appliedImpact.affectedTrains).toBe(6);
  });

  it('fills the schema the existing readers already rely on', () => {
    // `coordinated` is additive: an entry still carries everything a per-train
    // reader expects, so the decision-log strip needs no change to show one.
    store.recordCoordinatedAction(decision(), 4200);
    const entry = store.decisionLog().at(-1)!;

    expect(entry.seq).toBeGreaterThan(0);
    expect(entry.t).toBeGreaterThan(0);
    expect(entry.mode).toBeTruthy();
    expect(entry.aiSuggestion).toBe('Action A');
    expect(entry.decisionTimeMs).toBe(4200);
  });
});
