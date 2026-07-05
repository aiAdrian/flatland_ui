/**
 * Visual-Encoding Registry — v1.
 *
 * Per the `visual-encoding-registry` plan: one config owning, per semantic
 * *role*, a selectable tuple. Scope so far: **authorship** (human vs AI, the
 * plan's original v1 role) plus two roles pulled forward from the
 * colour-usage-audit's cleanup (`severity`, `positive`) because they already
 * have live consumers today (`--app-severity-*`, `--app-positive` in
 * `styles.scss`) and the owner asked for more choice, not just authorship.
 * Roles `train`, `city`, `mode` remain reserved placeholders — do not build
 * UI for them yet (train/agent-identity palette swapping is a materially
 * bigger design task — a full colour-blind-safe 6-type SBB palette — and is
 * explicitly deferred, not silently skipped; see colour-usage-audit.md §4
 * open question 4).
 *
 * Authorship still has no runtime consumer (the what-if tile B1 is the first
 * one) — that remains an intentional seam-first field, not dead code.
 * Severity/positive DO have live consumers: `SessionStore` applies the active
 * preset's values as `:root` CSS custom-property overrides (see
 * `session.store.ts`), so choosing a preset actually changes malfunction/
 * severity/recommended colours app-wide.
 *
 * Colours are runtime-configurable data values (chosen via preset), not SCSS —
 * the no-hardcoded-colour guardrail governs stylesheets/templates, not user
 * data.
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
  /** Overrides --app-severity-warn / --app-severity-error at runtime. */
  severity: { warn: string; error: string };
  /** Overrides --app-positive ("recommended"/good) at runtime. */
  positive: string;
}

export type VisualEncodingPresetId = 'default' | 'high-contrast';

export interface VisualEncodingPreset {
  id: VisualEncodingPresetId;
  label: string;
  description: string;
  encoding: VisualEncoding;
}

/**
 * The two presets. Default = the SBB tokens already in `styles.scss`
 * (severity warn/error orange/red, positive green, authorship human blue
 * solid / AI amber dashed).
 *
 * The alternate is a colour-blind-safe set built from the Okabe & Ito (2008)
 * "Color Universal Design" palette, chosen so all three roles stay mutually
 * distinguishable under deuteranopia/protanopia (the two most common forms):
 * authorship blue #0072B2 vs vermillion #D55E00 (both ≥ WCAG AA 4.5:1 on
 * white), severity warn orange #E69F00 / error uses near-black #333333
 * instead of a second red-family hue (avoids colliding with AI-vermillion —
 * red/orange/vermillion all read similarly under protanopia), and positive
 * uses bluish-green #009E73 rather than pure green — the Okabe-Ito pairing
 * conventionally used for "good/bad" because it stays distinct from
 * red/vermillion for red-green colour-blind viewers, unlike SBB green vs red.
 * Line-style (solid vs dashed) is retained on authorship as a second channel
 * so it still reads without colour (a11y), per the audit's blue/amber-overload
 * note.
 */
export const VISUAL_ENCODING_PRESETS: VisualEncodingPreset[] = [
  {
    id: 'default',
    label: 'Default',
    description: 'SBB colours: green/orange/red severity, blue/amber authorship.',
    encoding: {
      authorship: {
        human: { color: '#0079c7', lineStyle: 'solid', icon: '👤', label: 'Du' },
        ai:     { color: '#ffaa00', lineStyle: 'dashed', icon: '🤖', label: 'AI' },
      },
      severity: { warn: '#ffaa00', error: '#eb0000' },
      positive: '#00973b',
    },
  },
  {
    id: 'high-contrast',
    label: 'High-contrast (colour-blind-safe)',
    description: 'Okabe-Ito palette — stays distinguishable under red-green colour blindness.',
    encoding: {
      authorship: {
        human: { color: '#0072b2', lineStyle: 'solid', icon: '👤', label: 'Du' },
        ai:     { color: '#d55e00', lineStyle: 'dashed', icon: '🤖', label: 'AI' },
      },
      severity: { warn: '#e69f00', error: '#333333' },
      positive: '#009e73',
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
    const severity = parsed?.severity;
    const positive = parsed?.positive;
    if (human && ai && typeof human.color === 'string' && typeof ai.color === 'string'
      && (human.lineStyle === 'solid' || human.lineStyle === 'dashed')
      && (ai.lineStyle === 'solid' || ai.lineStyle === 'dashed')
      && severity && typeof severity.warn === 'string' && typeof severity.error === 'string'
      && typeof positive === 'string') {
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
      && p.encoding.authorship.ai.lineStyle === a.lineStyle
      && p.encoding.severity.warn === encoding.severity.warn
      && p.encoding.severity.error === encoding.severity.error
      && p.encoding.positive === encoding.positive) {
      return p.id;
    }
  }
  return 'default';
}
