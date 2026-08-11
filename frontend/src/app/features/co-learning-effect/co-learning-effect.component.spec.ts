import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { OperatorModelService, OperatorProfile } from '../../core/operator-model.service';
import { CoLearningEffectComponent } from './co-learning-effect.component';

function profileFixture(overrides: Partial<OperatorProfile> = {}): OperatorProfile {
  return {
    operatorId: 'operator1',
    isWarm: false,
    priorSessions: 0,
    evidenceCount: 0,
    passiveCount: 0,
    trustRatio: 0,
    valueWeights: {},
    valueProfile: { dominant: null, label: '—', dominantPct: 0, distribution: [], total: 0 },
    confirmedLearnings: [],
    optionPresentation: 'recommend',
    suggestedDirectorWeights: { punctuality: 1, connections: 1, stability: 1 },
    ...overrides,
  };
}

describe('CoLearningEffectComponent', () => {
  let fixture: ComponentFixture<CoLearningEffectComponent>;
  let cmp: CoLearningEffectComponent;
  let http: HttpTestingController;
  let model: OperatorModelService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [CoLearningEffectComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    fixture = TestBed.createComponent(CoLearningEffectComponent);
    cmp = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    model = TestBed.inject(OperatorModelService);
  });

  afterEach(() => {
    // The component itself issues no requests on construction.
    http.verify();
  });

  it('shows no callout while the model proposes nothing', () => {
    fixture.detectChanges();
    expect(cmp.confirmedCallout()).toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('bestätigt');
  });

  it('renders the "because you taught me this" callout for a confirmed learning', () => {
    cmp.refresh({ connection_critical: true });
    http.expectOne((r) => r.url.endsWith('/operator/operator1/adjustment')).flush({
      adjustment: {
        targetValue: 'connection',
        reason: 'confirmed preference',
        appliedLearning: 'Bei kritischem Anschluss bevorzugst du Halten.',
        confidence: 0.9,
      },
    });
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(cmp.confirmedCallout()).not.toBeNull();
    expect(text).toContain('Anschluss');
    expect(text).toContain('Bei kritischem Anschluss bevorzugst du Halten.');
    expect(text).toContain('Ranking-Nudge');
  });

  it('does not show the callout for a hint that came only from statistics', () => {
    cmp.refresh();
    http.expectOne((r) => r.url.endsWith('/operator/operator1/adjustment')).flush({
      adjustment: {
        targetValue: 'punctuality',
        reason: 'learned from 3 similar decision(s) (75%)',
        appliedLearning: null,
        confidence: 0.75,
      },
    });
    fixture.detectChanges();

    // The hint exists, but only a *confirmed* learning earns the callout.
    expect(cmp.adjustment()).not.toBeNull();
    expect(cmp.confirmedCallout()).toBeNull();
  });

  it('hides the dial proposal while the weights are still neutral', () => {
    model.profile.set(profileFixture());
    fixture.detectChanges();
    expect(cmp.weightsDiffer()).toBeFalse();
  });

  it('offers the inferred dials once they carry a preference', () => {
    model.profile.set(
      profileFixture({
        suggestedDirectorWeights: { punctuality: 0.4, connections: 2.2, stability: 0.4 },
      }),
    );
    fixture.detectChanges();

    expect(cmp.weightsDiffer()).toBeTrue();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('2.2');
    expect(text).toContain('Für Director übernehmen');
  });

  it('shows the carried-over profile when the model is warm', () => {
    model.profile.set(
      profileFixture({
        isWarm: true,
        priorSessions: 2,
        valueProfile: {
          dominant: 'connection',
          label: 'Connection-first',
          dominantPct: 71,
          distribution: [],
          total: 7,
        },
      }),
    );
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('2 früheren Session');
    expect(text).toContain('Connection-first');
    expect(text).toContain('71%');
  });

  it('maps value axes to German labels', () => {
    expect(cmp.axisLabel('connection')).toBe('Anschluss');
    expect(cmp.axisLabel('punctuality')).toBe('Pünktlichkeit');
    expect(cmp.axisLabel('stability')).toBe('Netzstabilität');
    expect(cmp.axisLabel(null)).toBe('—');
  });
});
