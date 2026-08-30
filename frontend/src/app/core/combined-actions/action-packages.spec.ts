import { buildPackages, PackageContext } from './action-packages';
import { trainWeight } from './impact-prediction';

/**
 * Widget E1 Stufe 1: packages derived from live conflicts must name only
 * trains actually in the session — that is the defect fix (no phantom chips).
 * These specs pin that invariant plus the three distinct rationales.
 */
describe('buildPackages (live-conflict derivation)', () => {
  // A 3-handle contention (the PF–CH shape). nameOf maps each handle to a
  // service name the way TrainIdentityService.nameFor does.
  const handles = [0, 1, 2];
  const nameOf = (h: number): string => ({ 0: 'IC_703', 1: 'RE_18', 2: 'S8_214' } as Record<number, string>)[h];

  const ctx: PackageContext = {
    // IC_703 due latest (156), RE_18 earliest (120), S8_214 mid (140).
    arrivalByHandle: { 0: 156, 1: 120, 2: 140 },
    // S8_214 most delayed (8), IC_703 mid (3), RE_18 least (1).
    delayByHandle: { 0: 3, 1: 1, 2: 8 },
  };

  const packages = () => buildPackages(handles, nameOf, ctx);

  it('produces exactly three packages A/B/C', () => {
    const pkgs = packages();
    expect(pkgs.length).toBe(3);
    expect(pkgs.map((p) => p.id)).toEqual(['A', 'B', 'C']);
  });

  it('names only trains present in the session — no phantoms', () => {
    // Every chip on every card must resolve to one of the input handles via
    // the same nameOf the component uses — that is the handleFor() !== null
    // acceptance check, driven from the derived packages.
    const knownNames = new Set(handles.map(nameOf));
    for (const pkg of packages()) {
      expect(pkg.aiOrder.length).toBeGreaterThan(0);
      for (const name of pkg.aiOrder) {
        expect(knownNames.has(name)).toBeTrue();
      }
    }
  });

  it('ranks package A by service weight, long-distance first, and recommends it', () => {
    const a = packages().find((p) => p.id === 'A')!;
    expect(a.recommended).toBeTrue();
    // IC_703 (weight 5) > RE_18 (3) > S8_214 (2).
    const weights = a.aiOrder.map((n) => trainWeight(n));
    expect(weights).toEqual([...weights].sort((x, y) => y - x));
    expect(a.aiOrder[0]).toBe('IC_703');
  });

  it('ranks package B by earliest scheduled arrival first', () => {
    const b = packages().find((p) => p.id === 'B')!;
    // RE_18 (120) < S8_214 (140) < IC_703 (156).
    expect(b.aiOrder).toEqual(['RE_18', 'S8_214', 'IC_703']);
  });

  it('ranks package C by current delay, most-delayed first', () => {
    const c = packages().find((p) => p.id === 'C')!;
    // S8_214 (8) > IC_703 (3) > RE_18 (1).
    expect(c.aiOrder).toEqual(['S8_214', 'IC_703', 'RE_18']);
  });

  it('keeps all three cards even when two orderings coincide', () => {
    // All three ranks identical → A, B, C would all be the same order. The
    // widget still shows three cards (never silently drops one, never
    // fabricates a difference).
    const equalCtx: PackageContext = {
      arrivalByHandle: { 0: 100, 1: 100, 2: 100 },
      delayByHandle: { 0: 0, 1: 0, 2: 0 },
    };
    const equalNameOf = (h: number) => ({ 0: 'IC_703', 1: 'IC_704', 2: 'IC_705' } as Record<number, string>)[h];
    // Equal weights too (all IC): byWeight tiebreaks by handle → 0,1,2.
    const pkgs = buildPackages(handles, equalNameOf, equalCtx);
    expect(pkgs.length).toBe(3);
    expect(pkgs.every((p) => p.aiOrder.join(',') === 'IC_703,IC_704,IC_705')).toBeTrue();
  });

  it('is deterministic — same inputs always yield the same packages', () => {
    expect(packages()).toEqual(packages());
  });
});
