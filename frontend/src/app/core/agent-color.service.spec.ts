import { TestBed } from '@angular/core/testing';
import { AgentColorService } from './agent-color.service';
import { TRAIN_TYPES } from './agent-color.types';

describe('AgentColorService', () => {
  let svc: AgentColorService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    svc = TestBed.inject(AgentColorService);
  });

  it('maps handle 0 to first train type (normal)', () => {
    expect(svc.getTrainType(0)).toBe('normal');
  });

  it('maps handles round-robin through TRAIN_TYPES', () => {
    for (let h = 0; h < TRAIN_TYPES.length * 2; h++) {
      const expected = TRAIN_TYPES[h % TRAIN_TYPES.length].type;
      expect(svc.getTrainType(h)).toBe(expected);
    }
  });

  it('handles negative handles gracefully', () => {
    expect(svc.getTrainType(-1)).toBe(TRAIN_TYPES[TRAIN_TYPES.length - 1].type);
  });

  it('returns the default tinted colour state when state is omitted', () => {
    expect(svc.getColor(1)).toBe(TRAIN_TYPES[1].colors.default);
  });

  it('returns each of the 4 tinted colour states', () => {
    const colors = svc.getColors(2);
    expect(colors.default).toBeTruthy();
    expect(colors.focus).toBeTruthy();
    expect(colors.muted).toBeTruthy();
    expect(colors.related).toBeTruthy();
  });

  it('separates tinted from solid colours', () => {
    const tint = svc.getColor(1, 'focus');
    const solid = svc.getColorSolid(1, 'focus');
    expect(tint.indexOf('rgba')).toBeGreaterThanOrEqual(0);
    expect(solid.charAt(0)).toBe('#');
  });

  it('returns a human-readable label', () => {
    expect(svc.getLabel(0)).toBe('Normal');
    expect(svc.getLabel(1)).toBe('Intercity');
  });

  it('plan colours are deterministic per handle', () => {
    expect(svc.getPlanColor(3)).toBe(svc.getPlanColor(3));
  });

  it('plan colours are unique for every train in a 20-train episode', () => {
    const colors = new Set<string>();
    for (let h = 0; h < 20; h++) {
      colors.add(svc.getPlanColor(h));
    }
    expect(colors.size).toBe(20);
  });
});
