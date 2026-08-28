import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SessionStore } from '../../core/session.store';
import { TrainActionService } from '../../core/dispatch/train-action.service';
import { AgentDTO, SessionState } from '../../core/models';
import { ImpactItem } from '../../core/events/event-types';
import { AgentsTableComponent } from './agents-table.component';

const MERGING_OPTIONS = [
  { action: 2, action_name: 'MOVE_FORWARD', label: '↑ Forward', target_position: [1, 4] },
  { action: 4, action_name: 'STOP_MOVING', label: '■ Stop', target_position: [1, 3] },
];

const SWITCH_OPTIONS = [
  { action: 1, action_name: 'MOVE_LEFT', label: '← Left', target_position: [2, 4] },
  { action: 2, action_name: 'MOVE_FORWARD', label: '↑ Forward', target_position: [2, 7] },
];

function agent(handle: number, over: Partial<AgentDTO> = {}): AgentDTO {
  return {
    handle,
    state: 'MOVING',
    position: [1, 2],
    latest_arrival: 150,
    time_to_deadline: 40,
    delay: 0,
    malfunction_remaining: 0,
    is_malfunctioning: false,
    override_action: null,
    next_decision: null,
    ...over,
  } as AgentDTO;
}

function impactItem(handle: number, over: Partial<ImpactItem> = {}): ImpactItem {
  return {
    handle,
    blocked_by: 9,
    blocked_cell: [1, 3],
    eta_steps: 4,
    clears_in_steps: 12,
    can_reroute: false,
    reroute_action: null,
    recommended_action: 'hold',
    severity: 'high',
    ...over,
  } as ImpactItem;
}

describe('AgentsTableComponent — Trains v2 (Dispositionstabelle)', () => {
  let fixture: ComponentFixture<AgentsTableComponent>;
  let cmp: AgentsTableComponent;
  let store: SessionStore;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [AgentsTableComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(AgentsTableComponent);
    cmp = fixture.componentInstance;
    store = TestBed.inject(SessionStore);

    store.interactionMode.set('recommendation');
    store.state.set({
      agents: [
        agent(0, { next_decision: { cell_type: 'MERGING', options: MERGING_OPTIONS } as never }),
        agent(1, {
          next_decision: { cell_type: 'SWITCH', options: SWITCH_OPTIONS } as never,
          time_to_deadline: -19,
          is_malfunctioning: true,
          malfunction_remaining: 12,
        }),
        agent(2, { state: 'DONE' }),
      ],
    } as SessionState);
    store.impact.set([impactItem(0, { blocked_by: 1, recommended_action: 'hold' })]);
  });

  // ── per-mode framing (spec §3) ──────────────────────────────────────────

  it('stars the AI recommendation in Recommendation mode', () => {
    const row = cmp.rows().find((r) => r.handle === 0)!;
    const stop = row.options.find((o) => o.action === 4)!;
    const forward = row.options.find((o) => o.action === 2)!;
    expect(stop.isAiRecommended).toBeTrue();   // impact recommends 'hold' → STOP
    expect(forward.isAiRecommended).toBeFalse();
  });

  it('marks nothing as preferred in Co-Learning — the options stay equal', () => {
    store.interactionMode.set('co-learning');
    const row = cmp.rows().find((r) => r.handle === 0)!;
    expect(row.options.every((o) => !o.isAiRecommended)).toBeTrue();
    expect(cmp.modeBehavior().hint).toContain('gleichwertig');
  });

  it('never invents a recommendation for a train the AI said nothing about', () => {
    // Train 1 is the blocker, not in the impact list. `next_decision` lists the
    // branches that physically exist; none of them is an AI preference.
    const row = cmp.rows().find((r) => r.handle === 1)!;
    expect(row.options.length).toBe(2);
    expect(row.options.every((o) => !o.isAiRecommended)).toBeTrue();
  });

  it('cannot star a hold at a switch, because a switch offers no stop', () => {
    // Backend truth (cell_classifier): SWITCH → left/forward/right only.
    // A 'hold' recommendation there simply has nothing to mark.
    store.impact.set([impactItem(1, { recommended_action: 'hold' })]);
    const row = cmp.rows().find((r) => r.handle === 1)!;
    expect(row.options.every((o) => !o.isAiRecommended)).toBeTrue();
  });

  it('stars a reroute at the branch the AI names', () => {
    store.impact.set([
      impactItem(1, { recommended_action: 'reroute', reroute_action: 1, can_reroute: true }),
    ]);
    const row = cmp.rows().find((r) => r.handle === 1)!;
    expect(row.options.find((o) => o.action === 1)!.isAiRecommended).toBeTrue();
    expect(row.options.find((o) => o.action === 2)!.isAiRecommended).toBeFalse();
  });

  // ── rows ────────────────────────────────────────────────────────────────

  it('puts trains in a conflict first, then the tightest deadline', () => {
    const order = cmp.rows().map((r) => r.handle);
    // 1 is malfunctioning and 0 is blocked → both in conflict; 1 is overdue.
    expect(order.slice(0, 2)).toEqual([1, 0]);
    expect(order.at(-1)).toBe(2);
  });

  it('says what is going on in one phrase, from the impact analysis', () => {
    const blocked = cmp.rows().find((r) => r.handle === 0)!;
    expect(blocked.message).toContain('blockiert durch Zug 1');
    expect(blocked.message).toContain('frei in 12');

    const blocker = cmp.rows().find((r) => r.handle === 1)!;
    expect(blocker.message).toContain('Störung, noch 12');
    expect(blocker.message).toContain('blockiert Zug 0');
  });

  it('reads slack as time in hand, and lateness as lateness', () => {
    expect(cmp.rows().find((r) => r.handle === 0)!.slack).toBe('noch 40');
    const late = cmp.rows().find((r) => r.handle === 1)!;
    expect(late.slack).toBe('+19 spät');
    expect(late.slackLate).toBeTrue();
  });

  it('narrows to the conflict set without changing what a conflict is', () => {
    expect(cmp.rows().length).toBe(3);
    cmp.toggleConflictsOnly();
    // The definition lives in the store, shared with the roster's filter.
    expect(cmp.rows().map((r) => r.handle).sort()).toEqual([0, 1]);
    expect(cmp.conflictCount()).toBe(2);
  });

  // ── acting (spec §4/§5) ─────────────────────────────────────────────────

  it('acts through the dispatch seam, stamped as coming from the table', () => {
    const actions = TestBed.inject(TrainActionService);
    const spy = spyOn(actions, 'toggle');
    cmp.onAction(0, 4);
    expect(spy).toHaveBeenCalledWith(0, 4, 'table');
  });

  it('shows the operator their own standing override', () => {
    store.state.set({
      agents: [agent(0, {
        override_action: 4,
        next_decision: { cell_type: 'MERGING', options: MERGING_OPTIONS } as never,
      })],
    } as SessionState);
    const row = cmp.rows()[0];
    expect(row.options.find((o) => o.action === 4)!.isMine).toBeTrue();
    expect(row.options.find((o) => o.action === 2)!.isMine).toBeFalse();
  });
});
