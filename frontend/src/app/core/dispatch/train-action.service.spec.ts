import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { SessionStore } from '../session.store';
import { AgentDTO, SessionInfo, SessionState } from '../models';
import { TrainActionService } from './train-action.service';

function agent(handle: number, override: number | null = null): AgentDTO {
  return { handle, override_action: override } as AgentDTO;
}

describe('TrainActionService — the single doorway for acting on a train', () => {
  let svc: TrainActionService;
  let store: SessionStore;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    svc = TestBed.inject(TrainActionService);
    store = TestBed.inject(SessionStore);
    // `agents` is computed from `state`, so seed the state.
    store.state.set({ agents: [agent(3), agent(7, 4)] } as SessionState);
  });

  it('sets an override for a train that has none, stamped with its origin', () => {
    const spy = spyOn(store, 'setOverride');
    svc.toggle(3, 2, 'map');
    expect(spy).toHaveBeenCalledWith(3, 2, 'human', 'map');
  });

  it('clears the override when the same action is clicked again', () => {
    // Train 7 already has override 4 — the toggle rule that used to be copied
    // into five components lives here now.
    const clear = spyOn(store, 'clearOverride');
    const set = spyOn(store, 'setOverride');
    svc.toggle(7, 4, 'roster');
    expect(clear).toHaveBeenCalledWith(7, 'human', 'roster');
    expect(set).not.toHaveBeenCalled();
  });

  it('sets, not clears, when a different action is clicked on the same train', () => {
    const set = spyOn(store, 'setOverride');
    svc.toggle(7, 2, 'table');
    expect(set).toHaveBeenCalledWith(7, 2, 'human', 'table');
  });

  it('keeps the AI/human attribution the caller passes', () => {
    const spy = spyOn(store, 'setOverride');
    svc.set(3, 4, 'impact', 'ai');
    expect(spy).toHaveBeenCalledWith(3, 4, 'ai', 'impact');
  });

  it('reports whether an action is the standing override', () => {
    expect(svc.isActive(7, 4)).toBeTrue();
    expect(svc.isActive(7, 2)).toBeFalse();
    expect(svc.isActive(3, 4)).toBeFalse();
  });

  it('does nothing surprising for an unknown train', () => {
    expect(svc.isActive(99, 2)).toBeFalse();
  });

  // The point of the origin is that it survives all the way into the audit
  // trail — a stamp that stops at the service boundary would be decoration.
  it('lands the origin in the decision log, not just in the call', () => {
    store.session.set({ id: 'sess-1' } as SessionInfo);
    svc.toggle(3, 2, 'map');

    const entry = store.decisionLog().at(-1);
    expect(entry).toBeDefined();
    expect(entry!.handle).toBe(3);
    expect(entry!.origin).toBe('map');
    expect(entry!.accountableOwner).toBe('human');
  });

  it('records the origin of a release too', () => {
    store.session.set({ id: 'sess-1' } as SessionInfo);
    svc.toggle(7, 4, 'inspector'); // 7 already holds override 4 → clears it

    const entry = store.decisionLog().at(-1);
    expect(entry!.action).toBe('proceed');
    expect(entry!.origin).toBe('inspector');
  });
});
