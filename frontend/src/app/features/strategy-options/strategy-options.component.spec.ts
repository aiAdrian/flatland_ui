import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DirectorStrategy } from '../../core/api.service';
import {
  OperatorModelService,
  OperatorProfile,
  ValueAxis,
} from '../../core/operator-model.service';
import { SessionStore } from '../../core/session.store';
import { StrategyOptionsComponent } from './strategy-options.component';

/**
 * Planner paths as they really arrive: one entry per train, many points each,
 * and handles that match the plan's `changed` list. The earlier fixture had a
 * single one-point path under handle '0' while `changed` named 1 and 2 — which
 * hid that only *rerouted* trains are drawn, and that a one-cell path cannot
 * be drawn at all.
 */
const PATHS = {
  '1': [
    { step: 3, row: 1, col: 2 },
    { step: 4, row: 1, col: 3 },
    { step: 5, row: 2, col: 3 },
  ],
  '2': [
    { step: 3, row: 5, col: 5 },
    { step: 4, row: 5, col: 6 },
  ],
  // Not in `changed`: keeps its route, so it must not be drawn.
  '7': [
    { step: 3, row: 9, col: 1 },
    { step: 4, row: 9, col: 2 },
  ],
};

/** What the overlay is expected to draw: the rerouted trains only. */
const REROUTED = { '1': PATHS['1'], '2': PATHS['2'] };

function strategy(
  id: string,
  ident: string,
  focus: 'punctuality' | 'connections' | 'stability',
  over: Partial<DirectorStrategy> = {},
): DirectorStrategy {
  const weights =
    focus === 'punctuality'
      ? { punctuality: 5, connections: 2, stability: 2 }
      : focus === 'connections'
        ? { punctuality: 2, connections: 5, stability: 2 }
        : { punctuality: 2, connections: 2, stability: 5 };
  return {
    id,
    ident,
    focus,
    weights,
    plan: {
      source: 'search',
      weighted: 0.6,
      utilities: { punctuality: 0.9, connections: 0.4, stability: 0.7 },
      changed: [1, 2],
    },
    paths: PATHS,
    ...over,
  };
}

const THREE = [
  strategy('focus_delay', 'A', 'punctuality'),
  strategy('focus_connections', 'B', 'connections'),
  strategy('focus_stability', 'C', 'stability'),
];

describe('StrategyOptionsComponent', () => {
  let fixture: ComponentFixture<StrategyOptionsComponent>;
  let cmp: StrategyOptionsComponent;
  let http: HttpTestingController;
  let store: SessionStore;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [StrategyOptionsComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(StrategyOptionsComponent);
    cmp = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    store = TestBed.inject(SessionStore);
    // load() needs a session; the component's own effect loads on session
    // change, so tests call load() explicitly and it is idempotent while a
    // request is in flight.
    store.session.set({ id: 's1' } as never);
    store.state.set({ elapsed_steps: 0 } as never);
    // The component loads on session change, so let its effect run once here;
    // the tests then only answer the request it made.
    fixture.detectChanges();
  });

  afterEach(() => {
    store.directorPreviewPaths.set(null);
    store.directorPreviewStrategyId.set(null);
    store.directorPreviewIsCommitted.set(false);
    store.directorFocusOutlook.set(null);
    store.playing.set(false);
    store.directorPlanPaths.set(null);
    store.session.set(null);
    store.state.set(null);
  });

  /** Answer the load() request; `flushState` also answers the follow-up
   *  /director call that resolves which focus is committed. */
  function flushStrategies(
    body: Partial<{
      available: boolean;
      reason: string | null;
      step: number;
      current: unknown;
      strategies: DirectorStrategy[];
    }> = {},
    state: { punctuality: number; connections: number; stability: number } | null = null,
  ): void {
    http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
      session_id: 's1',
      step: 0,
      available: true,
      reason: null,
      current: null,
      strategies: THREE,
      ...body,
    });
    if (state) {
      http.expectOne((r) => r.url.endsWith('/director')).flush({
        session_id: 's1',
        weights: state,
        plan: null,
        paths: null,
      });
    } else {
      http.expectOne((r) => r.url.endsWith('/director')).flush({
        session_id: 's1',
        weights: { punctuality: 1, connections: 1, stability: 1 },
        plan: null,
        paths: null,
      });
    }
  }

  it('renders three tiles labelled A/B/C with German focus titles', () => {
    flushStrategies();
    fixture.detectChanges();

    const tiles = cmp.tiles();
    expect(tiles.map((t) => t.ident)).toEqual(['A', 'B', 'C']);
    expect(tiles.map((t) => t.copy.title)).toEqual([
      'Verspätung minimieren',
      'Anschlüsse halten',
      'Stabilität maximieren',
    ]);
  });

  it('names the trade-off on every tile so no option looks strictly best', () => {
    flushStrategies();
    for (const tile of cmp.tiles()) {
      expect(tile.copy.gives.length).toBeGreaterThan(0);
      expect(tile.copy.costs.length).toBeGreaterThan(0);
    }
  });

  it('weights its own axis highest in every preset, without zeroing another', () => {
    flushStrategies();
    for (const tile of cmp.tiles()) {
      const w = tile.strategy.weights as unknown as Record<string, number>;
      const own = w[tile.strategy.focus];
      const others = Object.entries(w)
        .filter(([k]) => k !== tile.strategy.focus)
        .map(([, v]) => v);
      for (const other of others) {
        expect(own).toBeGreaterThan(other);
        expect(other).toBeGreaterThan(0);
      }
    }
  });

  it('marks exactly one axis per tile as its focus', () => {
    flushStrategies();
    for (const tile of cmp.tiles()) {
      expect(tile.axes.filter((a) => a.isFocus).length).toBe(1);
    }
  });

  it('exposes the planner utilities as percentages', () => {
    flushStrategies();
    const axes = cmp.tiles()[0].axes;
    expect(axes.map((a) => a.pct)).toEqual([90, 40, 70]);
    expect(cmp.tiles()[0].changed).toBe(2);
    expect(cmp.hasPlans()).toBeTrue();
  });

  it('degrades to preset-only tiles when the planner cannot answer', () => {
    http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
      session_id: 's1',
      step: 4,
      available: false,
      reason: 'No models installed — strategy plans need them',
      strategies: THREE.map((s) => ({ ...s, plan: null, paths: null })),
    });
    // Two /director reads follow an unavailable answer: the active-focus sync,
    // and the self-sufficiency attempt to materialise a first plan.
    for (const req of http.match((r) => r.url.endsWith('/director'))) {
      req.flush({
        session_id: 's1',
        weights: { punctuality: 1, connections: 1, stability: 1 },
        plan: { source: 'avoidance (no models)' },
        paths: null,
      });
    }
    fixture.detectChanges();

    expect(cmp.unavailableReason()).toContain('No models installed');
    expect(cmp.hasPlans()).toBeFalse();
    // Still three usable directives, just without numbers.
    expect(cmp.tiles().length).toBe(3);
    expect(cmp.tiles()[0].axes.every((a) => a.pct === null)).toBeTrue();
    // No step is claimed for numbers that do not exist.
    expect(cmp.computedAtStep()).toBeNull();
    expect(cmp.stale()).toBeFalse();
  });

  it('reads each axis as a delta against the plan currently driving', () => {
    flushStrategies({
      current: {
        source: 'search',
        weighted: 0.5,
        utilities: { punctuality: 0.8, connections: 0.4, stability: 0.9 },
      },
    });
    const axes = cmp.tiles()[0].axes;
    // 90/40/70 against a baseline of 80/40/90.
    expect(axes.map((a) => a.delta)).toEqual([10, 0, -20]);
  });

  it('leaves the delta unknown when there is no plan to compare against', () => {
    flushStrategies({ current: null });
    expect(cmp.tiles()[0].axes.every((a) => a.delta === null)).toBeTrue();
  });

  it('says so when all three focuses produce the same plan', () => {
    // Identical utilities AND no rerouted train: the choice does not bite here.
    const same = THREE.map((s) => ({
      ...s,
      plan: { ...s.plan!, changed: [] },
    }));
    flushStrategies({ strategies: same });
    fixture.detectChanges();

    expect(cmp.allFocusesAgree()).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('selben Plan');
  });

  it('does not claim agreement when a focus reroutes trains', () => {
    const differing = [
      { ...THREE[0], plan: { ...THREE[0].plan!, changed: [] } },
      { ...THREE[1], plan: { ...THREE[1].plan!, changed: [] } },
      {
        ...THREE[2],
        plan: {
          ...THREE[2].plan!,
          changed: [3],
          utilities: { punctuality: 0.7, connections: 0.4, stability: 0.95 },
        },
      },
    ];
    flushStrategies({ strategies: differing });
    expect(cmp.allFocusesAgree()).toBeFalse();
  });

  it('shows the share of transfers that hold, not the veto-style utility', () => {
    // The connections utility is a geometric mean clamped at 1e-4: measured
    // 0.022 while 38 % of 35 transfers actually held. Showing 2 % was correct
    // for the search and wrong for a human.
    flushStrategies({
      strategies: [
        {
          ...THREE[1],
          plan: {
            ...THREE[1].plan!,
            utilities: { punctuality: 0.85, connections: 0.022, stability: 0.0017 },
            reported: {
              keptRatio: 0.3767,
              connectionCount: 35,
              safety: { slack: 0.69, deadlock: 0.007, track: 0.721, cascade: 0.5 },
            },
          },
        },
      ],
    });
    fixture.detectChanges();

    const connections = cmp.tiles()[0].axes.find((a) => a.focus === 'connections')!;
    expect(connections.pct).toBe(38);
    expect(connections.scope).toBe('von 35');
    expect(fixture.nativeElement.textContent).toContain('von 35');
  });

  it('names the factor that limits stability instead of leaving a bare 0 %', () => {
    // stability = slack × deadlock × track × cascade. 0.69 × 0.007 × 0.72 × 0.50
    // = 0.0017 → "0 %", while three of four reserves are fine and only the
    // deadlock risk is critical.
    flushStrategies({
      strategies: [
        {
          ...THREE[2],
          plan: {
            ...THREE[2].plan!,
            utilities: { punctuality: 0.85, connections: 0.022, stability: 0.0017 },
            reported: {
              keptRatio: 0.3767,
              connectionCount: 35,
              safety: { slack: 0.69, deadlock: 0.007, track: 0.721, cascade: 0.5 },
            },
          },
        },
      ],
    });
    fixture.detectChanges();

    // 0.007 → 1 %; the sub-percent case has its own test below.
    expect(cmp.tiles()[0].stabilityHint).toBe('begrenzt durch Deadlock-Risiko (1 %)');
    expect(fixture.nativeElement.textContent).toContain('Deadlock-Risiko');
  });

  it('does not round a sub-percent bottleneck down to "0 %"', () => {
    // 0.007 shown as "0 %" reads like a placeholder rather than a measurement.
    flushStrategies({
      strategies: [
        {
          ...THREE[2],
          plan: {
            ...THREE[2].plan!,
            reported: {
              keptRatio: 0.4,
              connectionCount: 10,
              safety: { slack: 0.7, deadlock: 0.004, track: 0.7, cascade: 0.6 },
            },
          },
        },
      ],
    });
    expect(cmp.tiles()[0].stabilityHint).toContain('<1 %');
  });

  it('stays quiet about a limiting factor when none stands out', () => {
    flushStrategies({
      strategies: [
        {
          ...THREE[2],
          plan: {
            ...THREE[2].plan!,
            reported: {
              keptRatio: 0.9,
              connectionCount: 4,
              safety: { slack: 0.8, deadlock: 0.75, track: 0.9, cascade: 0.85 },
            },
          },
        },
      ],
    });
    expect(cmp.tiles()[0].stabilityHint).toBeNull();
  });

  it('falls back to the raw utility when no reported figures arrive', () => {
    flushStrategies();
    const connections = cmp.tiles()[0].axes.find((a) => a.focus === 'connections')!;
    // THREE's fixture utilities: connections 0.4 → 40 %, and no scope to show.
    expect(connections.pct).toBe(40);
    expect(connections.scope).toBeNull();
    expect(cmp.tiles()[0].stabilityHint).toBeNull();
  });

  it('materialises the first plan itself when the session has not planned yet', () => {
    // Director plans lazily, so entering the mode finds nothing to compare
    // against. The tiles have to trigger that plan on their own — the panel that
    // used to do it is no longer on the Director screen.
    http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
      session_id: 's1',
      step: 0,
      available: false,
      reason: "No committed plan yet — step under 'goal_directed' first",
      current: null,
      strategies: THREE.map((s) => ({ ...s, plan: null, paths: null })),
    });
    for (const req of http.match((r) => r.url.endsWith('/director'))) {
      req.flush({
        session_id: 's1',
        weights: { punctuality: 3, connections: 3, stability: 3 },
        plan: null,
        paths: null,
      });
    }

    // It plans with the dials the session already has: nothing is silently
    // committed on the operator's behalf.
    const push = http.expectOne((r) => r.url.endsWith('/director/weights'));
    expect(push.request.body).toEqual({
      punctuality: 3,
      connections: 3,
      stability: 3,
      plan: true,
    });
    push.flush({
      session_id: 's1',
      weights: { punctuality: 3, connections: 3, stability: 3 },
      replanned: true,
      plan: null,
      paths: { '0': [{ step: 1, row: 0, col: 0 }] },
    });

    // ...and reloads the tiles now that a plan exists.
    http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
      session_id: 's1',
      step: 0,
      available: true,
      reason: null,
      current: null,
      strategies: THREE,
    });
    expect(cmp.hasPlans()).toBeTrue();
  });

  it('never reports a goal as its own price', () => {
    // Produced "du priorisierst Anschlüsse — auch wenn es 2 Punkte Anschlüsse
    // kostet". A goal cannot be its own price.
    flushStrategies({
      current: {
        source: 'search',
        weighted: 0.5,
        // Baseline better than the option on connections *and* punctuality, so
        // the focus axis itself regresses.
        utilities: { punctuality: 0.95, connections: 0.5, stability: 0.5 },
      },
    });

    cmp.apply(cmp.tiles()[1]); // B = connections focus
    http.expectOne((r) => r.url.endsWith('/director/weights')).flush({
      session_id: 's1',
      weights: { punctuality: 2, connections: 5, stability: 2 },
      replanned: true,
      plan: null,
      paths: PATHS,
    });
    http.expectOne((r) => r.url.endsWith('/director/strategies'));

    const pending = store.pendingStrategyReflection()!;
    expect(pending.axis).toBe('connection');
    expect(pending.tradedAway).not.toBeNull();
    expect(pending.tradedAway).not.toContain('Anschlüsse');
    expect(pending.hypothesis).not.toContain('Anschlüsse kostet');
  });

  it('reports no price when only the goal own axis regressed', () => {
    flushStrategies({
      current: {
        source: 'search',
        weighted: 0.5,
        // Only connections is worse; punctuality and stability improve.
        utilities: { punctuality: 0.5, connections: 0.9, stability: 0.5 },
      },
    });

    cmp.apply(cmp.tiles()[1]);
    http.expectOne((r) => r.url.endsWith('/director/weights')).flush({
      session_id: 's1',
      weights: { punctuality: 2, connections: 5, stability: 2 },
      replanned: true,
      plan: null,
      paths: PATHS,
    });
    http.expectOne((r) => r.url.endsWith('/director/strategies'));

    expect(store.pendingStrategyReflection()!.tradedAway).toBeNull();
  });

  it('publishes the previewed focus for the impact forecast below the map', () => {
    flushStrategies({
      current: {
        source: 'search',
        weighted: 0.5,
        utilities: { punctuality: 0.95, connections: 0.4, stability: 0.9 },
      },
    });

    cmp.togglePreview(cmp.tiles()[1]);
    fixture.detectChanges();

    const outlook = store.directorFocusOutlook();
    expect(outlook?.subject).toBe('B · Anschlüsse halten');
    // 90/40/70 against 95/40/90: worse punctuality, connections held, less
    // stability headroom.
    expect(outlook?.signals).toEqual({
      addsDelay: true,
      keepsConnections: true,
      addsRipple: true,
    });
  });

  it('publishes nothing to the forecast while no focus is chosen', () => {
    flushStrategies({
      current: {
        source: 'search',
        weighted: 0.5,
        utilities: { punctuality: 0.9, connections: 0.4, stability: 0.7 },
      },
    });
    fixture.detectChanges();
    expect(store.directorFocusOutlook()).toBeNull();
  });

  it('marks the numbers stale once the episode moved on', () => {
    flushStrategies({ step: 5 });
    expect(cmp.stale()).toBeFalse();
    // elapsedSteps is derived from the session state, so move the state.
    store.state.set({ elapsed_steps: 9 } as never);
    expect(cmp.stale()).toBeTrue();
  });

  it('pins a focus look-ahead onto the map and releases it on a second click', () => {
    flushStrategies();

    const tile = cmp.tiles()[2];
    cmp.togglePreview(tile);
    expect(store.directorPreviewStrategyId()).toBe('focus_stability');
    expect(store.directorPreviewPaths()).toEqual(REROUTED);
    expect(cmp.tiles()[2].isPreviewed).toBeTrue();

    cmp.togglePreview(cmp.tiles()[2]);
    expect(store.directorPreviewStrategyId()).toBeNull();
    expect(store.directorPreviewPaths()).toBeNull();
  });

  it('gates the look-ahead on the divergence the map actually draws', () => {
    // The button used to enable on `plan.changed`, which includes trains whose
    // cells stay identical and only their timing shifts — so it was clickable
    // while nothing appeared on the map.
    flushStrategies({
      strategies: THREE.map((s) => ({
        ...s,
        plan: { ...s.plan!, changed: [1, 2, 7] },
        divergence: { reroutes: {}, holds: [] },
      })),
    });
    expect(cmp.tiles()[0].previewPaths).toBeNull();
    // The map draws no marks; the button then offers the plan instead of nothing.
    expect(cmp.previewBlockedReason(cmp.tiles()[0])).toContain('wie der laufende Plan');
    expect(cmp.previewLabel(cmp.tiles()[0])).toBe('Plan auf Karte');
  });

  it('counts the rerouted trains from the divergence, not from the re-plan list', () => {
    // Measured live: a focus reported `changed = [0..7]` with four actual
    // reroutes, and another with none — so the tile read "Leitet 8 Züge um" next
    // to a disabled "Auf Karte". Two sources, one of them wrong.
    flushStrategies({
      strategies: THREE.map((s) => ({
        ...s,
        plan: { ...s.plan!, changed: [0, 1, 2, 3, 4, 5, 6, 7] },
        divergence: {
          reroutes: { '1': { branch: { row: 1, col: 3, step: 4 }, points: PATHS['1'] } },
          holds: [{ handle: 5, row: 2, col: 2, steps: 3 }],
        },
      })),
    });
    fixture.detectChanges();

    expect(cmp.tiles()[0].changed).toBe(1);
    expect(cmp.tiles()[0].holds).toBe(1);
    const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
    expect(text).toContain('Leitet 1 Zug/Züge um');
    expect(text).toContain('1 warten statt umzufahren');
    expect(text).not.toContain('Leitet 8');
  });

  it('still puts something on the map when a focus deviates nowhere', () => {
    // The disabled button was what "Auf Karte funktioniert nicht" looked like,
    // and tile A lands in this state routinely: its plan equals the one already
    // driving. The routes are still worth seeing — just not as a look-ahead at a
    // change that does not exist.
    flushStrategies({
      strategies: THREE.map((s) => ({
        ...s,
        plan: { ...s.plan!, changed: [0, 1, 2] },
        divergence: { reroutes: {}, holds: [] },
      })),
    });
    fixture.detectChanges();

    const tile = cmp.tiles()[0];
    expect(tile.previewPaths).toBeNull();
    expect(tile.fullPaths).not.toBeNull();
    expect(cmp.previewLabel(tile)).toBe('Plan auf Karte');

    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('.so-btn--preview');
    expect(btn.hasAttribute('disabled')).toBeFalse();
    btn.click();

    expect(store.directorPreviewStrategyId()).toBe('focus_delay');
    // Every drawable route, and no divergence — so the map draws lines, not marks.
    expect(Object.keys(store.directorPreviewPaths()!).sort()).toEqual(['1', '2', '7']);
    expect(store.directorPreviewDivergence()).toBeNull();
    expect(store.directorPreviewIsFullPlan()).toBeTrue();
    expect(store.directorPreviewIsCommitted()).toBeFalse();

    // And it turns off again.
    fixture.detectChanges();
    cmp.togglePreview(cmp.tiles()[0]);
    expect(store.directorPreviewPaths()).toBeNull();
    expect(store.directorPreviewIsFullPlan()).toBeFalse();
  });

  it('says when the plan behind a focus is a baseline, not a searched one', () => {
    // §3.7's portfolio guarantee can hand back `plan_all_lines` /
    // `plan_avoiding_overlaps`. Presenting that as a searched answer would
    // overstate what the planner did for this goal.
    flushStrategies({
      strategies: [
        { ...THREE[0], plan: { ...THREE[0].plan!, source: 'lines', considered: { search: 0.4, lines: 0.6, avoidance: 0.5 } } },
        THREE[1],
        THREE[2],
      ],
    });
    fixture.detectChanges();

    expect(cmp.tiles()[0].fellBackTo).toContain('Linienplan');
    expect(cmp.tiles()[1].fellBackTo).toBeNull();
    const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
    expect(text).toContain('die Suche fand nichts Besseres');
  });

  it('stays quiet when the search won', () => {
    flushStrategies();
    expect(cmp.tiles().every((t) => t.fellBackTo === null)).toBeTrue();
    expect(fixture.nativeElement.textContent).not.toContain('nichts Besseres');
  });

  it('says the tile text and the button agree on what is shown', () => {
    flushStrategies({
      strategies: THREE.map((s) => ({
        ...s,
        plan: { ...s.plan!, changed: [0, 1, 2] },
        divergence: { reroutes: {}, holds: [] },
      })),
    });
    fixture.detectChanges();
    const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
    expect(text).toContain('Fährt jeden Zug wie der laufende Plan');
    expect(text).toContain('Plan auf Karte');
  });

  it('keeps promising the map while the answer is still being computed', () => {
    flushStrategies({ strategies: THREE.map((s) => ({ ...s, plan: null, paths: null })) });
    store.playing.set(true);
    fixture.detectChanges();
    // Unplanned is not the same as "no difference"; claiming the latter here
    // would be a finding the component does not have.
    expect(cmp.previewLabel(cmp.tiles()[0])).toBe('Auf Karte');
  });

  it('recognises agreement through the divergence as well', () => {
    // `plan.changed` stayed non-empty even when no train drove differently, so
    // the "all three lead to the same plan" note could never appear in practice.
    flushStrategies({
      strategies: THREE.map((s) => ({
        ...s,
        plan: { ...s.plan!, changed: [0, 1, 2] },
        divergence: { reroutes: {}, holds: [] },
      })),
    });
    expect(cmp.allFocusesAgree()).toBeTrue();
  });

  it('offers the look-ahead when the only difference is a wait', () => {
    // A hold has no alternative route, but it is still a visible difference.
    flushStrategies({
      strategies: THREE.map((s) => ({
        ...s,
        divergence: { reroutes: {}, holds: [{ handle: 3, row: 4, col: 5, steps: 6 }] },
      })),
    });
    expect(cmp.tiles()[0].previewPaths).not.toBeNull();
    expect(cmp.previewBlockedReason(cmp.tiles()[0])).toBeNull();
  });

  it('publishes the divergence, not full routes, for the map', () => {
    const divergence = {
      reroutes: {
        '1': { branch: { row: 1, col: 3, step: 4 }, points: PATHS['1'] },
      },
      holds: [{ handle: 5, row: 2, col: 2, steps: 3 }],
    };
    flushStrategies({ strategies: THREE.map((s) => ({ ...s, divergence })) });

    cmp.togglePreview(cmp.tiles()[0]);
    expect(store.directorPreviewDivergence()).toEqual(divergence);
    // A fresh preview starts without a train singled out.
    expect(store.directorHoverHandle()).toBeNull();

    cmp.clearPreview();
    expect(store.directorPreviewDivergence()).toBeNull();
  });

  it('draws only the trains a focus reroutes, not every planned route', () => {
    // All eight planned routes look nearly identical between the options — most
    // trains keep their path — so drawing all of them cluttered the grid without
    // distinguishing anything.
    flushStrategies();
    const paths = cmp.tiles()[0].previewPaths!;
    expect(Object.keys(paths).sort()).toEqual(['1', '2']);
    expect(paths['7']).toBeUndefined();
  });

  it('offers no look-ahead for a focus that reroutes nobody', () => {
    // The honest case that used to look like a broken button: planned, but every
    // train keeps its route.
    flushStrategies({
      strategies: THREE.map((s) => ({ ...s, plan: { ...s.plan!, changed: [] }, paths: {} })),
    });
    expect(cmp.tiles()[0].previewPaths).toBeNull();
    // No routes at all either, so there is genuinely nothing to draw.
    expect(cmp.tiles()[0].fullPaths).toBeNull();
    expect(cmp.previewBlockedReason(cmp.tiles()[0])).toContain('keine Route vor');

    cmp.togglePreview(cmp.tiles()[0]);
    expect(store.directorPreviewStrategyId()).toBeNull();
  });

  it('skips a rerouted train whose remaining path is too short to draw', () => {
    flushStrategies({
      strategies: [
        {
          ...THREE[0],
          plan: { ...THREE[0].plan!, changed: [1, 2] },
          paths: { '1': [{ step: 9, row: 1, col: 1 }], '2': PATHS['2'] },
        },
      ],
    });
    // A single cell cannot be drawn as a line.
    expect(Object.keys(cmp.tiles()[0].previewPaths!)).toEqual(['2']);
  });

  it('re-points a live look-ahead at the new routes after a recompute', () => {
    flushStrategies();
    cmp.togglePreview(cmp.tiles()[0]);
    expect(store.directorPreviewPaths()).toEqual(REROUTED);

    // Recompute with a different reroute set: the map must not keep drawing the
    // previous routes under the same "previewing" label.
    const next = { '3': PATHS['1'] };
    cmp.load(true);
    http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
      session_id: 's1', step: 12, available: true, reason: null, current: null,
      strategies: THREE.map((s) => ({ ...s, plan: { ...s.plan!, changed: [3] }, paths: next })),
    });
    for (const req of http.match((r) => r.url.endsWith('/director'))) {
      req.flush({ session_id: 's1', weights: { punctuality: 1, connections: 1, stability: 1 }, plan: null, paths: null });
    }

    expect(store.directorPreviewPaths()).toEqual(next);
  });

  it('drops a live look-ahead when the refreshed focus reroutes nobody', () => {
    flushStrategies();
    cmp.togglePreview(cmp.tiles()[0]);

    cmp.load(true);
    http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
      session_id: 's1', step: 12, available: true, reason: null, current: null,
      strategies: THREE.map((s) => ({ ...s, plan: { ...s.plan!, changed: [] }, paths: {} })),
    });
    for (const req of http.match((r) => r.url.endsWith('/director'))) {
      req.flush({ session_id: 's1', weights: { punctuality: 1, connections: 1, stability: 1 }, plan: null, paths: null });
    }

    // Showing nothing beats showing a stale picture under a fresh label.
    expect(store.directorPreviewPaths()).toBeNull();
    expect(store.directorPreviewStrategyId()).toBeNull();
  });

  it('does not preview a focus that has no planned reroute', () => {
    flushStrategies({
      strategies: THREE.map((s) => ({ ...s, plan: null, paths: null })),
    });
    cmp.togglePreview(cmp.tiles()[0]);
    expect(store.directorPreviewStrategyId()).toBeNull();
  });

  it('commits a focus and shows the plan that now drives', () => {
    flushStrategies();
    cmp.togglePreview(cmp.tiles()[1]);

    cmp.apply(cmp.tiles()[1]);
    const req = http.expectOne((r) => r.url.endsWith('/director/weights'));
    expect(req.request.body).toEqual({
      punctuality: 2,
      connections: 5,
      stability: 2,
      plan: true,
    });
    req.flush({
      session_id: 's1',
      weights: { punctuality: 2, connections: 5, stability: 2 },
      replanned: true,
      plan: null,
      paths: PATHS,
    });

    expect(cmp.activeFocus()).toBe('connections');
    expect(cmp.tiles()[1].isActive).toBeTrue();
    expect(store.directorPlanPaths()).toEqual(PATHS);
    // The committed course stays drawn. Clearing it here — which is what this
    // did before — meant committing a focus changed nothing visible beyond a
    // button label, so A/B/C looked like it had no effect.
    expect(store.directorPreviewPaths()).toEqual(REROUTED);
    expect(store.directorPreviewStrategyId()).toBe('focus_connections');
    expect(store.directorPreviewIsCommitted()).toBeTrue();

    // The committed plan is the new baseline, so the per-focus deltas refer to
    // something that no longer drives → re-fetch (free when cached).
    http.expectOne((r) => r.url.endsWith('/director/strategies'));
  });

  it('does not let a click hide the plan that is driving', () => {
    flushStrategies();
    cmp.apply(cmp.tiles()[1]);
    http.expectOne((r) => r.url.endsWith('/director/weights')).flush({
      session_id: 's1',
      weights: { punctuality: 2, connections: 5, stability: 2 },
      replanned: true,
      plan: null,
      paths: PATHS,
    });
    http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
      session_id: 's1', step: 0, available: true, reason: null, current: null, strategies: THREE,
    });
    expect(store.directorPreviewIsCommitted()).toBeTrue();

    // Clicking the committed tile turns it back into a plain look-ahead rather
    // than clearing the overlay: hiding the active course is never the intent.
    cmp.togglePreview(cmp.tiles()[1]);
    expect(store.directorPreviewPaths()).toEqual(REROUTED);
    expect(store.directorPreviewIsCommitted()).toBeFalse();
  });

  it('explains a preview button it has to disable', () => {
    flushStrategies({ strategies: THREE.map((s) => ({ ...s, plan: null, paths: null })) });
    expect(cmp.previewBlockedReason(cmp.tiles()[0])).toContain('Optionen berechnen');
  });

  it('does not force a first plan while the run is already producing one', () => {
    // Stepping under 'goal_directed' plans on the first step, so forcing a second
    // one only competes for the same ~10s and doubles the apparent stall.
    store.playing.set(true);
    http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
      session_id: 's1',
      step: 0,
      available: false,
      reason: "No committed plan yet — step under 'goal_directed' first",
      current: null,
      strategies: THREE.map((s) => ({ ...s, plan: null, paths: null })),
    });
    http.expectOne((r) => r.url.endsWith('/director')).flush({
      session_id: 's1',
      weights: { punctuality: 1, connections: 1, stability: 1 },
      plan: null,
      paths: null,
    });
    http.expectNone((r) => r.url.endsWith('/director/weights'));
    store.playing.set(false);
  });

  it('holds the forecast back while the run is playing', () => {
    // Measured: three residual plans take ~20s, and every simulation step
    // invalidates them — so a mid-run forecast is stale before it arrives, and it
    // competes with the simulation for CPU. Automatic loads wait for a pause.
    flushStrategies({ strategies: THREE.map((s) => ({ ...s, plan: null, paths: null })) });
    store.playing.set(true);
    fixture.detectChanges();

    expect(cmp.waitingForPause()).toBeTrue();
    cmp.load();
    http.expectNone((r) => r.url.endsWith('/director/strategies'));

    const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
    expect(text).toContain('sobald du pausierst');
    expect(text).toContain('Ziele übernehmen kannst du jederzeit');
    expect(cmp.previewBlockedReason(cmp.tiles()[0])).toContain('Pausiere den Lauf');
  });

  it('computes anyway when the operator asks explicitly', () => {
    flushStrategies({ strategies: THREE.map((s) => ({ ...s, plan: null, paths: null })) });
    store.playing.set(true);

    cmp.load(true);
    http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
      session_id: 's1', step: 5, available: true, reason: null,
      current: null, strategies: THREE,
    });
    for (const req of http.match((r) => r.url.endsWith('/director'))) {
      req.flush({ session_id: 's1', weights: { punctuality: 1, connections: 1, stability: 1 }, plan: null, paths: null });
    }
    expect(cmp.hasPlans()).toBeTrue();
  });

  it('recomputes once when the run is paused', () => {
    flushStrategies({ strategies: THREE.map((s) => ({ ...s, plan: null, paths: null })) });
    store.playing.set(true);
    fixture.detectChanges();

    store.playing.set(false);
    fixture.detectChanges();

    const reqs = http.match((r) => r.url.endsWith('/director/strategies'));
    expect(reqs.length).toBe(1);
    reqs[0].flush({
      session_id: 's1', step: 9, available: true, reason: null,
      current: null, strategies: THREE,
    });
    for (const req of http.match((r) => r.url.endsWith('/director'))) {
      req.flush({ session_id: 's1', weights: { punctuality: 1, connections: 1, stability: 1 }, plan: null, paths: null });
    }
    expect(cmp.hasPlans()).toBeTrue();
    expect(cmp.waitingForPause()).toBeFalse();
  });

  it('recognises the committed focus from the session dials, whatever their scale', () => {
    // Same 2:5:2 ratio, different magnitude — the backend normalises.
    flushStrategies({}, { punctuality: 0.4, connections: 1.0, stability: 0.4 });
    expect(cmp.activeFocus()).toBe('connections');
  });

  it('treats neutral dials as "no focus chosen yet"', () => {
    flushStrategies({}, { punctuality: 1, connections: 1, stability: 1 });
    expect(cmp.activeFocus()).toBeNull();
    expect(cmp.tiles().every((t) => !t.isActive)).toBeTrue();
  });

  // ── the simulated outcome (director-mode.md §3.8) ─────────────────────────
  describe('playing a focus out', () => {
    /** A what-if answer: continue vs re-plan, both simulated to the end. */
    function whatIf(over: {
      delay: [number, number];
      arrived?: [number, number];
      kept?: [number, number];
      source?: 'research' | 'continue';
      changed?: number[];
      considered?: { research: number; continue: number };
    }) {
      const [baseDelay, optDelay] = over.delay;
      const [baseArrived, optArrived] = over.arrived ?? [1, 1];
      const [baseKept, optKept] = over.kept ?? [6, 6];
      return {
        session_id: 's1',
        step: 12,
        weights: { punctuality: 2, connections: 5, stability: 2 },
        continue: {
          total_delay: baseDelay, arrived: baseArrived, trains: 6,
          all_arrived: false, steps: 200,
          connections_total: 17, connections_kept: baseKept, kept_ratio: baseKept / 17,
        },
        replan: {
          total_delay: optDelay, arrived: optArrived, trains: 6,
          all_arrived: false, steps: 200,
          connections_total: 17, connections_kept: optKept, kept_ratio: optKept / 17,
          source: over.source ?? 'research',
          changed: over.changed ?? [1, 2],
          predicted: {
            weighted: 0.4,
            utilities: { punctuality: 0.87, connections: 1, stability: 0.03 },
            considered: over.considered ?? { research: 0.4, continue: 0.3 },
          },
        },
      };
    }

    it('reports the measured deltas, on request only', () => {
      flushStrategies();
      // Never automatic: two whole episodes cost ~7 s (measured).
      http.expectNone((r) => r.url.endsWith('/director/whatif'));

      cmp.simulate(cmp.tiles()[2]);
      const req = http.expectOne((r) => r.url.endsWith('/director/whatif'));
      expect(req.request.body).toEqual({ punctuality: 2, connections: 2, stability: 5 });
      req.flush(whatIf({ delay: [442, 324], arrived: [1, 3], kept: [6, 8] }));
      fixture.detectChanges();

      const m = cmp.tiles()[2].measured!;
      expect(m.deltaDelay).toBe(-118);
      expect(m.deltaArrived).toBe(2);
      expect(m.deltaKept).toBe(2);
      expect(m.changesNothing).toBeFalse();

      const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
      expect(text).toContain('Nachgespielt bis Episodenende (ab Schritt 12)');
      expect(text).toContain('Verspätung -118');
      expect(text).toContain('Ankünfte +2 (3/6)');
      expect(text).toContain('Anschlüsse +2 (8/17)');
      // Only the tile that was simulated says anything.
      expect(cmp.tiles()[0].measured).toBeNull();
    });

    it('says when the re-planner keeps the current plan', () => {
      flushStrategies();
      cmp.simulate(cmp.tiles()[1]);
      http.expectOne((r) => r.url.endsWith('/director/whatif')).flush(
        whatIf({ delay: [442, 442], source: 'continue', changed: [] }),
      );
      fixture.detectChanges();

      expect(cmp.tiles()[1].measured!.changesNothing).toBeTrue();
      expect(fixture.nativeElement.textContent).toContain('bleibt beim laufenden Plan');
    });

    it('names it when the simulation contradicts the score', () => {
      // §3.8: the models rank residual plans optimistically. Measured on the demo
      // env, the worst-scored focus was the only one that improved the outcome —
      // a tile that only shows scores recommends the wrong goal confidently.
      flushStrategies();
      cmp.simulate(cmp.tiles()[0]);
      http.expectOne((r) => r.url.endsWith('/director/whatif')).flush(
        whatIf({
          delay: [442, 470],
          considered: { research: 0.8, continue: 0.3 }, // planner preferred re-planning
        }),
      );
      fixture.detectChanges();

      expect(cmp.tiles()[0].measured!.contradictsScore).toBeTrue();
      const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
      expect(text).toContain('widerspricht der Bewertung');
      expect(text).toContain('im Zweifel gilt das Nachspielen');
    });

    it('drops a simulation once the state it was taken from moved on', () => {
      flushStrategies({ step: 12 });
      cmp.simulate(cmp.tiles()[0]);
      http.expectOne((r) => r.url.endsWith('/director/whatif')).flush(
        whatIf({ delay: [442, 400] }),
      );
      expect(cmp.tiles()[0].measured).not.toBeNull();

      cmp.load(true);
      http.expectOne((r) => r.url.endsWith('/director/strategies')).flush({
        session_id: 's1', step: 30, available: true, reason: null,
        current: null, strategies: THREE,
      });
      for (const req of http.match((r) => r.url.endsWith('/director'))) {
        req.flush({ session_id: 's1', weights: { punctuality: 1, connections: 1, stability: 1 }, plan: null, paths: null });
      }
      // Measured numbers from an older step under a fresh plan would be the same
      // stale-under-a-new-label problem the map overlay had.
      expect(cmp.tiles()[0].measured).toBeNull();
    });

    it('keeps the model values when the simulation fails', () => {
      flushStrategies();
      cmp.simulate(cmp.tiles()[0]);
      http.expectOne((r) => r.url.endsWith('/director/whatif')).error(
        new ProgressEvent('error'), { status: 400, statusText: 'no models' },
      );
      fixture.detectChanges();

      expect(cmp.tiles()[0].measured).toBeNull();
      expect(cmp.simulating()).toBeNull();
      expect(fixture.nativeElement.textContent).toContain('Simulation ist fehlgeschlagen');
    });
  });

  // ── the learned preference, where the decision is made ────────────────────
  describe('learned preference', () => {
    let model: OperatorModelService;

    beforeEach(() => {
      model = TestBed.inject(OperatorModelService);
    });

    afterEach(() => model.profile.set(null));

    it('marks the tile the carried-over preference points at', () => {
      model.profile.set(profile({ dominant: 'connection', total: 4, dominantPct: 75, priorSessions: 2 }));
      flushStrategies();
      fixture.detectChanges();

      expect(cmp.tiles().filter((t) => t.isPreferred).map((t) => t.ident)).toEqual(['B']);
      const text = (fixture.nativeElement.textContent as string).replace(/\s+/g, ' ');
      expect(text).toContain('Passt zu deiner gelernten Präferenz');
      // The evidence travels with the mark, and it stays a proposal.
      expect(text).toContain('75 %');
      expect(text).toContain('2 abgeschlossene Schicht(en)');
      expect(text).toContain('keine Vorauswahl');
    });

    it('leaves the order of the tiles alone', () => {
      model.profile.set(profile({ dominant: 'stability', total: 5, dominantPct: 60 }));
      flushStrategies();
      // A nudge, not a ranking: C stays third.
      expect(cmp.tiles().map((t) => t.ident)).toEqual(['A', 'B', 'C']);
      expect(cmp.tiles()[2].isPreferred).toBeTrue();
    });

    it('prefers an explicitly confirmed rule over the distribution', () => {
      model.profile.set(
        profile({
          dominant: 'connection',
          total: 6,
          dominantPct: 80,
          confirmedLearnings: [
            { statement: 'Bei Störung zuerst Stabilität.', targetValue: 'stability' },
          ],
        }),
      );
      flushStrategies();
      fixture.detectChanges();

      expect(cmp.tiles().filter((t) => t.isPreferred).map((t) => t.ident)).toEqual(['C']);
      expect(fixture.nativeElement.textContent).toContain('Von dir bestätigt');
    });

    it('marks nothing on a single decision', () => {
      // One choice is not a preference; a mark after one click would teach the
      // operator that the AI over-reads them.
      model.profile.set(profile({ dominant: 'connection', total: 1, dominantPct: 100 }));
      flushStrategies();
      expect(cmp.tiles().every((t) => !t.isPreferred)).toBeTrue();
    });

    it('marks nothing for an axis Director has no preset for', () => {
      // Throughput-first is a real profile; rounding it onto a neighbouring tile
      // would be an invention.
      model.profile.set(profile({ dominant: 'throughput', total: 8, dominantPct: 70 }));
      flushStrategies();
      expect(cmp.tiles().every((t) => !t.isPreferred)).toBeTrue();
    });

    it('marks nothing without a profile', () => {
      flushStrategies();
      expect(cmp.preferred()).toBeNull();
      expect(fixture.nativeElement.textContent).not.toContain('gelernten Präferenz');
    });
  });
});

/** A backend profile as the operator model returns it. */
function profile(over: {
  dominant: ValueAxis | null;
  total: number;
  dominantPct: number;
  priorSessions?: number;
  confirmedLearnings?: OperatorProfile['confirmedLearnings'];
}): OperatorProfile {
  return {
    operatorId: 'operator1',
    isWarm: (over.priorSessions ?? 0) > 0,
    priorSessions: over.priorSessions ?? 0,
    evidenceCount: over.total,
    passiveCount: 0,
    trustRatio: 0,
    valueWeights: {},
    valueProfile: {
      dominant: over.dominant,
      label: 'Connection-first',
      dominantPct: over.dominantPct,
      distribution: [],
      total: over.total,
    },
    confirmedLearnings: over.confirmedLearnings ?? [],
    optionPresentation: 'neutral',
    suggestedDirectorWeights: { punctuality: 1, connections: 1, stability: 1 },
  };
}
