import { CommonModule } from '@angular/common';
import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  HostBinding,
  Input,
  computed,
  inject,
  signal,
} from '@angular/core';
import { AgentColorService } from '../../core/agent-color.service';
import { ApiService } from '../../core/api.service';
import { PolicyGraph, PolicyGraphEdge, PolicyGraphNode, RailTile } from '../../core/models';
import { SessionStore } from '../../core/session.store';

/** A node placed on the canvas: x = simulation step, y = branch lane. */
interface LaidOutNode {
  node: PolicyGraphNode;
  x: number;
  y: number;
  glyph: 'root' | 'divergence' | 'arrival' | 'deadlock' | 'truncated' | 'terminal';
}

/** An edge drawn as an orthogonal connector between two laid-out nodes. */
interface LaidOutEdge {
  edge: PolicyGraphEdge;
  path: string;
  midX: number;
  midY: number;
  label: string;
  isDivergence: boolean;
}

/** A train drawn on the preview map for the hovered node. */
interface PreviewAgent {
  handle: number;
  x: number;
  y: number;
  color: string;
  rotation: number;
  state: string;
}

const CELL = 32;              // map cell size, matching flatland-map
const COL_W = 26;             // px per simulation step on the graph x-axis
const LANE_H = 34;            // px per branch lane on the graph y-axis
const MARGIN_X = 16;
const MARGIN_Y = 18;

/**
 * Policy-Divergence Event Graph.
 *
 * Answers "what would each policy do, and where do they actually differ?"
 * for the whole run. The backend rolls every available policy forward in
 * lockstep from the current state; a node is created only where they
 * produce *different futures* (plus arrivals and deadlocks), so the graph
 * shows genuine decision moments rather than every step.
 * See docs/plans/policy-divergence-event-graph.md.
 *
 * Layout is split: the graph of futures on the left, a preview of the
 * world state on the right. Hovering (or clicking to pin) a node renders
 * exactly the state that node represents — same rail tiles as the main
 * map, with the trains placed where that future puts them.
 *
 * x is the simulation step, so no graph-layout library is needed: nodes
 * already carry their step, and lanes are assigned per branch.
 */
@Component({
  selector: 'app-policy-graph',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './policy-graph.component.html',
  styleUrl: './policy-graph.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class PolicyGraphComponent {
  @Input() embedded = false;

  readonly store = inject(SessionStore);
  private api = inject(ApiService);
  private agentColors = inject(AgentColorService);

  readonly graph = signal<PolicyGraph | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  /** Node under the mouse; the preview follows this unless one is pinned. */
  readonly hoveredId = signal<string | null>(null);
  /** Clicking a node pins it so the preview survives moving the mouse away. */
  readonly pinnedId = signal<string | null>(null);

  readonly fullscreen = signal(false);

  /** Budget knobs — the build is CPU-bound, so they are user-visible. */
  readonly maxNodes = signal(800);
  readonly maxWallS = signal(60);

  /** Branch only where a disputed train still has a choice — on a switch or
   *  the cell before one. Mid-section a train is committed, so a policy
   *  disagreement there is a timing difference, not a routing decision.
   *  Cuts the tree ~3x and is what makes an 8-train whole run tractable. */
  readonly routingOnly = signal(true);

  @HostBinding('class.policy-graph--fullscreen') get isFullscreen() {
    return this.fullscreen();
  }

  toggleFullscreen(): void {
    this.fullscreen.update((v) => !v);
  }

  // ── data ──────────────────────────────────────────────────────────

  load(refresh = false): void {
    const id = this.store.session()?.id;
    if (!id) {
      this.error.set('No active session.');
      return;
    }
    this.loading.set(true);
    this.error.set(null);
    this.api
      .policyGraph(id, {
        maxNodes: this.maxNodes(),
        maxWallS: this.maxWallS(),
        decisionCellsOnly: this.routingOnly(),
        refresh,
      })
      .subscribe({
        next: (g) => {
          this.graph.set(g);
          this.hoveredId.set(null);
          this.pinnedId.set(g.root_id);
          this.loading.set(false);
        },
        error: (e) => {
          this.error.set(e?.error?.detail ?? e?.message ?? 'Failed to build graph');
          this.loading.set(false);
        },
      });
  }

  // ── graph layout (x = step, lanes = branches) ─────────────────────

  readonly layout = computed<{ nodes: LaidOutNode[]; edges: LaidOutEdge[]; width: number; height: number }>(() => {
    const g = this.graph();
    if (!g) return { nodes: [], edges: [], width: 0, height: 0 };

    const childrenOf = new Map<string, string[]>();
    const hasParent = new Set<string>();
    for (const e of g.edges) {
      if (!childrenOf.has(e.from)) childrenOf.set(e.from, []);
      childrenOf.get(e.from)!.push(e.to);
      hasParent.add(e.to);
    }

    // Depth-first walk assigns each leaf its own lane, so sibling
    // branches never overlap and a path reads left-to-right.
    const lane = new Map<string, number>();
    let nextLane = 0;
    const seen = new Set<string>();
    const walk = (id: string): number => {
      if (seen.has(id)) return lane.get(id) ?? 0;
      seen.add(id);
      const kids = (childrenOf.get(id) ?? []).filter((k) => !seen.has(k));
      if (kids.length === 0) {
        const own = nextLane++;
        lane.set(id, own);
        return own;
      }
      const kidLanes = kids.map(walk);
      // Sit on the average of the children so a fork looks symmetric.
      const own = kidLanes.reduce((a, b) => a + b, 0) / kidLanes.length;
      lane.set(id, own);
      return own;
    };
    walk(g.root_id);
    // Any node not reachable from the root (shouldn't happen, but never
    // silently drop data) gets appended below.
    for (const id of Object.keys(g.nodes)) {
      if (!lane.has(id)) lane.set(id, nextLane++);
    }

    const rootStep = g.nodes[g.root_id]?.step ?? 0;
    const xOf = (n: PolicyGraphNode) => MARGIN_X + (n.step - rootStep) * COL_W;
    const yOf = (id: string) => MARGIN_Y + (lane.get(id) ?? 0) * LANE_H;

    const nodes: LaidOutNode[] = Object.values(g.nodes).map((n) => ({
      node: n,
      x: xOf(n),
      y: yOf(n.id),
      glyph: n.truncated
        ? 'truncated'
        : n.event === 'root'
          ? 'root'
          : n.event === 'deadlock'
            ? 'deadlock'
            : n.event === 'arrival'
              ? 'arrival'
              : n.terminal
                ? 'terminal'
                : 'divergence',
    }));

    const edges: LaidOutEdge[] = g.edges.map((e) => {
      const a = g.nodes[e.from];
      const b = g.nodes[e.to];
      const x1 = xOf(a);
      const y1 = yOf(e.from);
      const x2 = xOf(b);
      const y2 = yOf(e.to);
      // Elbow: run along the parent's lane, then drop into the child's.
      const midX = x1 + Math.max(8, (x2 - x1) * 0.55);
      return {
        edge: e,
        path: `M ${x1} ${y1} H ${midX} V ${y2} H ${x2}`,
        midX: (x1 + x2) / 2,
        midY: y2 - 6,
        label: this.edgeLabel(e),
        isDivergence: Object.keys(e.action_diff).length > 0,
      };
    });

    const width = Math.max(...nodes.map((n) => n.x), 0) + MARGIN_X * 2;
    const height = Math.max(...nodes.map((n) => n.y), 0) + MARGIN_Y * 2;
    return { nodes, edges, width, height };
  });

  private edgeLabel(e: PolicyGraphEdge): string {
    if (!e.policy_ids.length) return '';
    return e.policy_ids.map((p) => this.policyShort(p)).join('+');
  }

  policyShort(id: string): string {
    if (id === 'deadlock_avoidance') return 'DLA';
    if (id === 'shortest_path') return 'SP';
    return id
      .split('_')
      .map((s) => s.charAt(0).toUpperCase())
      .join('');
  }

  // ── selection / preview ───────────────────────────────────────────

  readonly activeId = computed(() => this.hoveredId() ?? this.pinnedId());

  readonly activeNode = computed<PolicyGraphNode | null>(() => {
    const g = this.graph();
    const id = this.activeId();
    return g && id ? (g.nodes[id] ?? null) : null;
  });

  /** The edge that leads INTO the active node — this is what the
   *  operator wants to read: which policies chose what to get here. */
  readonly activeEdges = computed<PolicyGraphEdge[]>(() => {
    const g = this.graph();
    const id = this.activeId();
    if (!g || !id) return [];
    const incoming = g.edges.filter((e) => e.to === id);
    if (!incoming.length) return [];
    // Show all sibling branches of the same fork, so the choice is visible
    // as a comparison rather than a single option.
    const parent = incoming[0].from;
    return g.edges.filter((e) => e.from === parent && Object.keys(e.action_diff).length > 0);
  });

  onNodeEnter(id: string): void {
    this.hoveredId.set(id);
  }

  onNodeLeave(): void {
    this.hoveredId.set(null);
  }

  onNodeClick(id: string): void {
    this.pinnedId.set(id);
  }

  isActive(id: string): boolean {
    return this.activeId() === id;
  }

  isPinned(id: string): boolean {
    return this.pinnedId() === id;
  }

  // ── preview map ───────────────────────────────────────────────────

  readonly tiles = computed<RailTile[]>(() => this.store.railTiles());

  readonly mapWidth = computed(() => this.store.width() * CELL);
  readonly mapHeight = computed(() => this.store.height() * CELL);

  /** Trains as the hovered future places them. */
  readonly previewAgents = computed<PreviewAgent[]>(() => {
    const n = this.activeNode();
    if (!n) return [];
    return Object.entries(n.agents).map(([handle, a]) => {
      const h = Number(handle);
      return {
        handle: h,
        x: a.pos[1] * CELL + CELL / 2,
        y: a.pos[0] * CELL + CELL / 2,
        color: this.agentColors.getColorSolid(h),
        // Flatland direction 0=N,1=E,2=S,3=W → degrees for the arrow.
        rotation: a.dir * 90,
        state: a.state,
      };
    });
  });

  readonly previewTargets = computed(() => {
    const g = this.graph();
    if (!g) return [];
    return Object.entries(g.agent_targets).map(([handle, t]) => ({
      handle: Number(handle),
      x: t[1] * CELL + CELL / 2,
      y: t[0] * CELL + CELL / 2,
      color: this.agentColors.getColorSolid(Number(handle)),
    }));
  });

  /** Trains that exist but are not on the map in this future — either not
   *  yet departed or already arrived. Shown as a count so the preview
   *  never silently omits trains. */
  readonly previewOffMap = computed(() => {
    const g = this.graph();
    const n = this.activeNode();
    if (!g || !n) return { waiting: 0, arrived: 0 };
    const onMap = Object.keys(n.agents).length;
    const arrived = n.arrived.length;
    return { waiting: Math.max(0, g.num_agents - onMap - arrived), arrived };
  });

  tileHref(t: RailTile): string {
    return `/flatland-svg/${t.svg}`;
  }

  tileX(t: RailTile): number {
    return t.c * CELL;
  }

  tileY(t: RailTile): number {
    return t.r * CELL;
  }

  tileTransform(t: RailTile): string {
    const cx = t.c * CELL + CELL / 2;
    const cy = t.r * CELL + CELL / 2;
    return `rotate(${t.rot} ${cx} ${cy})`;
  }

  readonly cellSize = CELL;

  // ── summary text ──────────────────────────────────────────────────

  readonly summary = computed(() => {
    const g = this.graph();
    if (!g) return null;
    const s = g.stats;
    return {
      nodes: s.nodes,
      divergences: s.divergences,
      avoided: s.false_divergences + s.ongoing_dispute_steps + s.non_decision_disputes,
      truncated: s.truncated_nodes,
      deadEnds: s.pruned_deadlock_branches,
      seconds: s.build_seconds,
      policies: g.policy_ids.map((p) => this.policyShort(p)).join(' vs '),
    };
  });

  agentColor(handle: number): string {
    return this.agentColors.getColorSolid(handle);
  }

  objectKeys(o: Record<string, unknown>): string[] {
    return Object.keys(o);
  }
}
