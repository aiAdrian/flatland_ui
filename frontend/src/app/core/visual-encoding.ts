/**
 * Visual-Encoding Registry — v1 (authorship only).
 *
 * Per the `visual-encoding-registry` plan: one config owning, per semantic
 * *role*, a selectable tuple `{ color, lineStyle, icon, label }`. v1 scope is
 * narrow + extensible: **only the `authorship` role** (human vs AI). Roles
 * `train`, `city`, `mode`, `severity` are reserved placeholders — do not build
 * UI for them yet.
 *
 * This is a seam-first build: no component renders authorship today (the
 * what-if tile B1 will be the first consumer). The setting has no visible
 * runtime effect yet — that is intentional (same pattern as `kind`/`granularity`
 * on `PanelDefinition`), not dead code. See
 * [colour-usage-audit.md](../../docs/reference/colour-usage-audit.md) §2/§3 and
 * the `visual-encoding-registry` memory.
 *
 * Colours are runtime-configurable data values (chosen via preset), not SCSS —
 * the no-hardcoded-colour guardrail governs stylesheets/templates, not user
 * data. The what-if tile will bind these via `[style.*]`, not by hardcoding.
 */

export type LineStyle = 'solid' | 'dashed';

export interface VisualEncodingRole {
  color: string;
  lineStyle: LineStyle;
  icon: string;
  label: string;
}

export interface VisualEncoding {
  authorship: { human: VisualEncodingRole; ai: VisualEncodingRole };
}

export type VisualEncodingPresetId = 'default' | 'high-contrast';

export interface VisualEncodingPreset {
  id: VisualEncodingPresetId;
  label: string;
  description: string;
  encoding: VisualEncoding;
}

/**
 * The two presets. Default = the plan's spec (human blue solid, AI amber
 * dashed). The alternate is a colour-blind-safer, higher-contrast pair from the
 * Okabe-Ito palette (the canonical CB-safe set) — blue #0072B2 vs vermillion
 * #D55E00, both ≥ WCAG AA 4.5:1 on white (#0072B2 ≈ 5.6:1, #D55E00 ≈ 4.5:1).
 * Line-style (solid vs dashed) is retained as the second channel so authorship
 * still reads without colour (a11y), per the audit's blue/amber-overload note.
 */
export const VISUAL_ENCODING_PRESETS: VisualEncodingPreset[] = [
  {
    id: 'default',
    label: 'Default',
    description: 'Human blue solid, AI amber dashed.',
    encoding: {
      authorship: {
        human: { color: '#0079c7', lineStyle: 'solid', icon: '👤', label: 'Du' },
        ai:     { color: '#ffaa00', lineStyle: 'dashed', icon: '🤖', label: 'AI' },
      },
    },
  },
  {
    id: 'high-contrast',
    label: 'High-contrast (colour-blind-safer)',
    description: 'Okabe-Ito blue vs vermillion — higher contrast, CB-safe.',
    encoding: {
      authorship: {
        human: { color: '#0072b2', lineStyle: 'solid', icon: '👤', label: 'Du' },
        ai:     { color: '#d55e00', lineStyle: 'dashed', icon: '🤖', label: 'AI' },
      },
    },
  },
];

export const DEFAULT_VISUAL_ENCODING: VisualEncoding = VISUAL_ENCODING_PRESETS[0].encoding;

const STORAGE_KEY = 'flatland.visualEncoding.v1';

/** Load from localStorage, falling back to the default on any error/missing. */
export function loadVisualEncoding(): VisualEncoding {
  try {
    const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
    if (!raw) return DEFAULT_VISUAL_ENCODING;
    const parsed = JSON.parse(raw) as Partial<VisualEncoding> | null;
    const human = parsed?.authorship?.human;
    const ai = parsed?.authorship?.ai;
    if (human && ai && typeof human.color === 'string' && typeof ai.color === 'string'
      && (human.lineStyle === 'solid' || human.lineStyle === 'dashed')
      && (ai.lineStyle === 'solid' || ai.lineStyle === 'dashed')) {
      return parsed as VisualEncoding;
    }
  } catch {
    // ignore — fall through to default
  }
  return DEFAULT_VISUAL_ENCODING;
}

/** Persist to localStorage (no-op on any storage error). */
export function saveVisualEncoding(encoding: VisualEncoding): void {
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(encoding));
    }
  } catch {
    // ignore
  }
}

/** Which preset id matches the given encoding (default if none match). */
export function matchingPresetId(encoding: VisualEncoding): VisualEncodingPresetId {
  const h = encoding.authorship.human;
  const a = encoding.authorship.ai;
  for (const p of VISUAL_ENCODING_PRESETS) {
    if (p.encoding.authorship.human.color === h.color
      && p.encoding.authorship.human.lineStyle === h.lineStyle
      && p.encoding.authorship.ai.color === a.color
      && p.encoding.authorship.ai.lineStyle === a.lineStyle) {
      return p.id;
    }
  }
  return 'default';
}
