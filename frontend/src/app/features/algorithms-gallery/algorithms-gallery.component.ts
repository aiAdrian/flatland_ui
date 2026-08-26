import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { PolicyInfo } from '../../core/models';
import { ConfigShellComponent } from '../config-shell/config-shell.component';

type Family = PolicyInfo['family'];
type Role = PolicyInfo['role'];

interface Facet<T> {
  id: T;
  label: string;
  colorVar: string | null;
  amount: number;
}

interface FamilyGroup {
  family: Family;
  label: string;
  answers: string;
  blurb: string;
  colorVar: string;
  entries: PolicyInfo[];
}

/** Presentation per algorithm family — the primary grouping, mirroring how
 *  `kind` groups the Widget Gallery. Deliberately about *how the algorithm
 *  decides*, not about what it is called. */
const FAMILY_META: Record<Family, { label: string; answers: string; blurb: string; token: string }> = {
  'rule-based': {
    label: 'Rule-based',
    answers: 'A fixed rule, evaluated per train per step.',
    blurb:
      'Hand-written heuristics. Cheap, fully inspectable, no training and no checkpoint — what you read in the source is what runs.',
    token: '--app-kind-context',
  },
  'search-based': {
    label: 'Search-based',
    answers: 'A plan, computed by searching over futures.',
    blurb:
      'Classical planning (CBS, prioritised planning). Optimises explicitly against a stated objective; cost is compute at plan time, not training.',
    token: '--app-kind-decision-support',
  },
  learned: {
    label: 'Learned',
    answers: 'A policy fitted to data.',
    blurb:
      'RL or imitation. Needs a checkpoint to be useful at all, and its behaviour is only as good as what it was trained on.',
    token: '--app-kind-prediction',
  },
  hybrid: {
    label: 'Hybrid',
    answers: 'Search, with learned parts inside it.',
    blurb:
      'Planning whose scoring or heuristics come from a model. Degrades to the pure-search path when no model is present.',
    token: '--app-kind-capitalization',
  },
};

const ROLE_META: Record<Role, { label: string; blurb: string; token: string }> = {
  operational: {
    label: 'Operational',
    blurb: 'Meant to actually run a session.',
    token: '--app-positive',
  },
  baseline: {
    label: 'Baseline',
    blurb: 'A comparison point — it exists to be beaten, or to fail in an instructive way.',
    token: '--app-kind-decision-support',
  },
  diagnostic: {
    label: 'Diagnostic',
    blurb: 'Isolates one effect. Not for running a study condition.',
    token: '--sbb-color-granite',
  },
};

const FAMILY_ORDER: Family[] = ['rule-based', 'search-based', 'hybrid', 'learned'];

/**
 * Algorithm Gallery — the catalog of every decision algorithm the playground
 * can run.
 *
 * ## Why this exists
 *
 * Until now an algorithm was a line in a dropdown: five labels, no way to tell
 * rule-based from learned, what a policy does when two trains contend, where it
 * came from, or whether it may be published. For a research playground where
 * the algorithm is a study *condition*, that is the wrong amount of information.
 *
 * ## Second instance of the catalog pattern
 *
 * Shares the Widget Gallery's grammar — governance bar, facet rail on sbb-tag,
 * compact rows that expand — but deliberately NOT its schema: the facets here
 * are family / role / determinism / licence, because that is what distinguishes
 * one algorithm from another. Forcing one schema across catalogs would make
 * both worse. The common parts are still not extracted into a shared component;
 * with two examples the seams are becoming visible, and a third would settle it.
 *
 * ## No second source of truth
 *
 * Everything is read live from `GET /policies`, which serves
 * `app/policies/registry.py` — already the single authority for runtime
 * behaviour. The Widget Gallery has to cross-check a frontend catalog against a
 * runtime map because those two drifted; here there is nothing to drift.
 *
 * Reached at /algorithms.
 */
@Component({
  selector: 'app-algorithms-gallery',
  standalone: true,
  imports: [CommonModule, FormsModule, ConfigShellComponent],
  templateUrl: './algorithms-gallery.component.html',
  styleUrl: './algorithms-gallery.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AlgorithmsGalleryComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly familyMeta = FAMILY_META;
  readonly roleMeta = ROLE_META;

  readonly policies = signal<PolicyInfo[]>([]);
  readonly loadError = signal<string | null>(null);
  readonly loading = signal(true);

  // ── Filters ──────────────────────────────────────────────────────────────
  readonly familyFilter = signal<ReadonlySet<Family>>(new Set());
  readonly roleFilter = signal<Role | 'all'>('all');
  readonly determinismFilter = signal<'all' | 'deterministic' | 'stochastic'>('all');
  readonly query = signal('');
  private readonly expanded = signal<ReadonlySet<string>>(new Set());

  ngOnInit(): void {
    this.api.listPolicies().subscribe({
      next: (list: PolicyInfo[]) => {
        this.policies.set(list);
        this.loading.set(false);
      },
      error: () => {
        this.loadError.set('Could not reach the backend — /policies is served by the FastAPI app.');
        this.loading.set(false);
      },
    });
  }

  readonly total = computed(() => this.policies().length);

  private matches(p: PolicyInfo): boolean {
    const fams = this.familyFilter();
    if (fams.size && !fams.has(p.family)) return false;

    const role = this.roleFilter();
    if (role !== 'all' && p.role !== role) return false;

    const det = this.determinismFilter();
    if (det === 'deterministic' && !p.deterministic) return false;
    if (det === 'stochastic' && p.deterministic) return false;

    const q = this.query().trim().toLowerCase();
    if (q) {
      const hay = [
        p.label, p.id, p.description, p.at_conflict,
        p.provenance, p.grounding, p.observation, p.licence,
      ].join(' ').toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  }

  readonly groups = computed<FamilyGroup[]>(() => {
    const shown = this.policies().filter((p) => this.matches(p));
    return FAMILY_ORDER.map((family) => ({
      family,
      label: FAMILY_META[family].label,
      answers: FAMILY_META[family].answers,
      blurb: FAMILY_META[family].blurb,
      colorVar: `var(${FAMILY_META[family].token})`,
      entries: shown.filter((p) => p.family === family),
    })).filter((g) => g.entries.length > 0);
  });

  readonly shownCount = computed(() =>
    this.groups().reduce((n, g) => n + g.entries.length, 0),
  );

  readonly isFiltered = computed(
    () =>
      this.familyFilter().size > 0 ||
      this.roleFilter() !== 'all' ||
      this.determinismFilter() !== 'all' ||
      this.query().trim().length > 0,
  );

  // ── Governance tallies ───────────────────────────────────────────────────
  private count(pred: (p: PolicyInfo) => boolean): number {
    return this.policies().filter(pred).length;
  }

  readonly roleTally = computed(() =>
    (['operational', 'baseline', 'diagnostic'] as Role[]).map((id) => ({
      id,
      label: ROLE_META[id].label.toLowerCase(),
      n: this.count((p) => p.role === id),
    })),
  );

  /** Everything shipped today is rule-based or hybrid — nothing learned is
   *  connected. Surfaced rather than left to be noticed, because it is the
   *  most consequential fact about the current catalog. */
  readonly learnedCount = computed(() => this.count((p) => p.family === 'learned'));

  /** Distinct licences in the catalog. More than one means an open-source
   *  release has a question to answer per algorithm. */
  readonly licences = computed(() => {
    const seen = new Map<string, number>();
    for (const p of this.policies()) seen.set(p.licence, (seen.get(p.licence) ?? 0) + 1);
    return [...seen.entries()].map(([licence, n]) => ({ licence, n }));
  });

  // ── Facets ───────────────────────────────────────────────────────────────
  readonly familyFacets = computed<Facet<Family>[]>(() =>
    FAMILY_ORDER.map((f) => ({
      id: f,
      label: FAMILY_META[f].label,
      colorVar: `var(${FAMILY_META[f].token})`,
      amount: this.count((p) => p.family === f),
    })),
  );

  readonly roleFacets = computed<Facet<Role>[]>(() =>
    (['operational', 'baseline', 'diagnostic'] as Role[]).map((r) => ({
      id: r,
      label: ROLE_META[r].label,
      colorVar: `var(${ROLE_META[r].token})`,
      amount: this.count((p) => p.role === r),
    })),
  );

  // ── Actions ──────────────────────────────────────────────────────────────
  isFamilyActive(f: Family): boolean {
    return this.familyFilter().has(f);
  }

  toggleFamily(f: Family): void {
    const next = new Set(this.familyFilter());
    next.has(f) ? next.delete(f) : next.add(f);
    this.familyFilter.set(next);
  }

  clearFamilies(): void {
    this.familyFilter.set(new Set());
  }

  setRole(r: Role | 'all'): void {
    this.roleFilter.set(r);
  }

  setDeterminism(d: 'all' | 'deterministic' | 'stochastic'): void {
    this.determinismFilter.set(d);
  }

  resetFilters(): void {
    this.familyFilter.set(new Set());
    this.roleFilter.set('all');
    this.determinismFilter.set('all');
    this.query.set('');
  }

  isExpanded(p: PolicyInfo): boolean {
    return this.expanded().has(p.id);
  }

  toggleExpanded(p: PolicyInfo): void {
    const next = new Set(this.expanded());
    next.has(p.id) ? next.delete(p.id) : next.add(p.id);
    this.expanded.set(next);
  }

  // ── Cosmetics ────────────────────────────────────────────────────────────
  roleVar(r: Role): string {
    return `var(${ROLE_META[r].token})`;
  }

  familyVar(f: Family): string {
    return `var(${FAMILY_META[f].token})`;
  }

  trackByFamily = (_: number, g: FamilyGroup): string => g.family;
  trackByPolicy = (_: number, p: PolicyInfo): string => p.id;
}
