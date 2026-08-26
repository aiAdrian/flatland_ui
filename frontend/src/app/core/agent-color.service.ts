import { Injectable } from '@angular/core';
import { ColorState, TRAIN_TYPES, TrainType, TrainTypeColors } from './agent-color.types';

/**
 * Central source of truth for agent / train colours.
 *
 * Round-robin assignment: agent.handle % TRAIN_TYPES.length.
 * Deterministic - same handle always yields the same train type.
 *
 * Two flavours per state:
 *   getColor(h, state)       -> tinted   (alpha 0.7) for fills, dots, badges
 *   getColorSolid(h, state)  -> opaque                for lines, strokes, paths
 */
@Injectable({ providedIn: 'root' })
export class AgentColorService {
  private idx(handle: number): number {
    const n = TRAIN_TYPES.length;
    return ((handle % n) + n) % n;
  }

  /** Map handle -> train type (deterministic, round-robin). */
  getTrainType(handle: number): TrainType {
    return TRAIN_TYPES[this.idx(handle)].type;
  }

  /** Human label, e.g. for tooltips / inspector. */
  getLabel(handle: number): string {
    return TRAIN_TYPES[this.idx(handle)].label;
  }

  /** Tinted (alpha 0.7) colours - all 4 states. */
  getColors(handle: number): TrainTypeColors {
    return TRAIN_TYPES[this.idx(handle)].colors;
  }

  /** Solid (alpha 1.0) colours - all 4 states. */
  getColorsSolid(handle: number): TrainTypeColors {
    return TRAIN_TYPES[this.idx(handle)].colorsSolid;
  }

  /**
   * Tinted single colour. API parity with the legacy agentColor(handle): string.
   * Use for dots, badges, soft fills.
   */
  getColor(handle: number, state: ColorState = 'default'): string {
    return this.getColors(handle)[state];
  }

  /**
   * Solid single colour. Use for lines, strokes, agent paths and other
   * elements that need full opacity to read clearly.
   */
  getColorSolid(handle: number, state: ColorState = 'default'): string {
    return this.getColorsSolid(handle)[state];
  }

  /**
   * The global selected-agent colour — the TS-side value of the
   * `--app-select-color` token in styles.scss; keep the two in sync.
   */
  getSelectedColor(): string {
    return '#f939e9';
  }

  /**
   * Distinct per-handle colour for per-train route overlays (Director plan).
   * The train-type palette above has only 6 identities (two of them the same
   * grey), so routes of different trains become indistinguishable; here every
   * handle gets its own hue via golden-angle spacing, kept in the muted
   * mid-tone range of the SBB agent palette. Deterministic per handle,
   * independent of spawn state.
   */
  getPlanColor(handle: number): string {
    const h = Math.abs(handle);
    const hue = Math.round((210 + h * 137.508) % 360);
    const light = h % 2 === 0 ? 57 : 64;
    return `hsl(${hue}, 42%, ${light}%)`;
  }
}
