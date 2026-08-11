import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { OperatorModelService, OperatorProfile } from './operator-model.service';

/** Minimal profile payload, shaped like the backend's `ProfileOut`. */
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

describe('OperatorModelService', () => {
  let svc: OperatorModelService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    svc = TestBed.inject(OperatorModelService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('posts a deliberate signal and mirrors the returned profile', () => {
    svc.recordSignal({
      step: 12,
      handle: 3,
      value: 'connection',
      deliberate: true,
      context: { connection_critical: true },
    }).subscribe();

    const req = http.expectOne((r) => r.url.endsWith('/operator/operator1/signal'));
    expect(req.request.method).toBe('POST');
    expect(req.request.body.deliberate).toBeTrue();
    expect(req.request.body.value).toBe('connection');

    req.flush(profileFixture({ evidenceCount: 1 }));
    expect(svc.profile()?.evidenceCount).toBe(1);
  });

  it('marks a passive accept as non-deliberate (the evidence guard)', () => {
    svc.recordSignal({ followedAi: true, deliberate: false }).subscribe();

    const req = http.expectOne((r) => r.url.endsWith('/operator/operator1/signal'));
    expect(req.request.body.deliberate).toBeFalse();
    expect(req.request.body.followedAi).toBeTrue();
    req.flush(profileFixture({ passiveCount: 1 }));

    expect(svc.profile()?.passiveCount).toBe(1);
    expect(svc.profile()?.evidenceCount).toBe(0);
  });

  it('exposes the suggested Director dials once a profile is loaded', () => {
    svc.loadProfile().subscribe();
    http.expectOne((r) => r.url.endsWith('/operator/operator1')).flush(
      profileFixture({
        isWarm: true,
        suggestedDirectorWeights: { punctuality: 0.6, connections: 2.1, stability: 0.9 },
      }),
    );

    expect(svc.isWarm()).toBeTrue();
    expect(svc.suggestedWeights()?.connections).toBe(2.1);
  });

  it('unwraps the adjustment envelope', () => {
    let received: unknown = 'unset';
    svc.adjustment({ connection_critical: true }, ['connection']).subscribe((a) => (received = a));

    const req = http.expectOne((r) => r.url.endsWith('/operator/operator1/adjustment'));
    expect(req.request.body.availableValues).toEqual(['connection']);
    req.flush({
      adjustment: {
        targetValue: 'connection',
        reason: 'confirmed preference',
        appliedLearning: 'Protect critical connections.',
        confidence: 0.9,
      },
    });

    expect((received as { targetValue: string }).targetValue).toBe('connection');
  });

  it('returns null when the model proposes no adjustment', () => {
    let received: unknown = 'unset';
    svc.adjustment().subscribe((a) => (received = a));
    http
      .expectOne((r) => r.url.endsWith('/operator/operator1/adjustment'))
      .flush({ adjustment: null });

    expect(received).toBeNull();
  });

  it('uses the configured operator id in the url', () => {
    svc.operatorId.set('gereon');
    svc.loadProfile().subscribe();
    const req = http.expectOne((r) => r.url.endsWith('/operator/gereon'));
    req.flush(profileFixture({ operatorId: 'gereon' }));
    expect(svc.profile()?.operatorId).toBe('gereon');
  });

  it('folds the session into the profile on end-session', () => {
    svc.endSession().subscribe();
    const req = http.expectOne((r) => r.url.endsWith('/operator/operator1/end-session'));
    expect(req.request.method).toBe('POST');
    req.flush(profileFixture({ isWarm: true, priorSessions: 1 }));
    expect(svc.profile()?.priorSessions).toBe(1);
  });
});
