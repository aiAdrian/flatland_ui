import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SessionStore } from '../../core/session.store';
import { Recommendation, ScenarioOption } from '../../core/events/event-types';
import { RecommendationsPanelComponent } from './recommendations-panel.component';

function scenario(id: string, title: string, over: Partial<ScenarioOption> = {}): ScenarioOption {
  return {
    id,
    title,
    description: `${title} description`,
    score: 0.4,
    isBaseline: false,
    isRecommended: false,
    kpiDeltas: { meanDelay: 0, done: 0, deadlocks: 0 },
    trajectories: { 0: [] },
    ...over,
  } as ScenarioOption;
}

function rec(id: string, title: string, scenarioId: string): Recommendation {
  return { id, title, description: '', confidence: 0.7, countdownSeconds: 0, scenarioId };
}

describe('RecommendationsPanelComponent look-ahead pinning', () => {
  let fixture: ComponentFixture<RecommendationsPanelComponent>;
  let cmp: RecommendationsPanelComponent;
  let store: SessionStore;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [RecommendationsPanelComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(RecommendationsPanelComponent);
    cmp = fixture.componentInstance;
    store = TestBed.inject(SessionStore);

    store.interactionMode.set('recommendation');
    store.scenarios.set([
      scenario('scn_dla', 'DLA (Deadlock Avoidance)', { isBaseline: true }),
      scenario('scn_shortest', 'Shortest Path', { isRecommended: true }),
    ]);
    store.recommendations.set([
      rec('r1', 'Switch to Shortest Path', 'scn_shortest'),
      rec('r2', 'Keep DLA', 'scn_dla'),
    ]);
  });

  it('previews an option on hover and clears it on leave', () => {
    const r = cmp.strategyCards()[0].rec;
    cmp.previewOn(r);
    expect(store.previewScenarioId()).toBe('scn_shortest');
    cmp.previewOff(r);
    expect(store.previewScenarioId()).toBeNull();
  });

  it('keeps a pinned option on the map after the mouse leaves', () => {
    const r = cmp.strategyCards()[0].rec;
    cmp.togglePin(r);
    expect(cmp.isPinned(r)).toBeTrue();
    expect(store.previewScenarioId()).toBe('scn_shortest');

    cmp.previewOff(r);
    expect(store.previewScenarioId()).toBe('scn_shortest');
  });

  it('restores the pinned look-ahead when another card is only hovered', () => {
    const pinned = cmp.strategyCards()[0].rec;
    const hovered = cmp.strategyCards()[1].rec;
    cmp.togglePin(pinned);

    cmp.previewOn(hovered);
    expect(store.previewScenarioId()).toBe('scn_dla');
    cmp.previewOff(hovered);
    expect(store.previewScenarioId()).toBe('scn_shortest');
  });

  it('unpins on a second click and drops the overlay', () => {
    const r = cmp.strategyCards()[0].rec;
    cmp.togglePin(r);
    cmp.togglePin(r);
    expect(cmp.isPinned(r)).toBeFalse();
    expect(store.previewScenarioId()).toBeNull();
  });

  it('does not pin an option without a backing scenario', () => {
    const orphan = rec('r3', 'Unknown branch', 'scn_unknown');
    cmp.togglePin(orphan);
    expect(cmp.isPinned(orphan)).toBeFalse();
    expect(store.previewScenarioId()).toBeNull();
  });
});
