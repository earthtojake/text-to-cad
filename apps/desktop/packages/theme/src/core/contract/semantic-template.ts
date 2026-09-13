/**
 * Role-stable semantic template: maps every CSS custom-property slot to a
 * scale.step reference.  Written once, never branched per theme or polarity.
 *
 * This is the ONLY place semantics are assigned. Scales are hue-named in the
 * palette (green, red, amber, blue, orange, purple); here we say what each hue
 * means (success → green, error → red, merged → purple, conflict → orange, …).
 *
 * Ref syntax:
 *   "scale.step"         → e.g. "neutral.1", "accent.9", "green.11"
 *   "scale.contrast"     → the auto-computed contrast-on-solid color
 *   "mix(A pct%, B)"     → CSS color-mix expression resolved at output time
 *   "#literal"           → literal CSS color (kept to an absolute minimum)
 *
 * Normalizations applied vs semantic.tokens.json:
 *   - background / foreground-inverse: mapped to neutral.1 (light theme makes neutral.1 = white)
 *   - border / border-* / foreground-passive / status-* / foreground-diff-added:
 *       collapsed to one step; ramp generation ensures perceptual correctness per polarity
 *   - primary-button: unified on accent.9 solid + accent.contrast text (Radix pattern)
 *   - foreground-body: kept as mix expression (resolved by the CSS emitter)
 */

export const SEMANTIC_TEMPLATE = {
  // ── Backgrounds ───────────────────────────────────────────────────────────
  background: 'neutral.1',
  'background-1': 'neutral.2',
  'background-2': 'neutral.3',
  'background-3': 'neutral.4',

  // ── Foregrounds ───────────────────────────────────────────────────────────
  foreground: 'neutral.12',
  'foreground-inverse': 'neutral.1',
  /** Resolved as color-mix(in srgb, var(--neutral-11) 40%, var(--neutral-12)) by the CSS emitter */
  'foreground-body': 'mix(neutral.11 40%, neutral.12)',
  'foreground-muted': 'neutral.11',
  'foreground-passive': 'neutral.9',

  // ── Secondary (sidebar / secondary panels) ────────────────────────────────
  'background-secondary': 'neutral.2',
  'background-secondary-1': 'neutral.1',
  'background-secondary-2': 'neutral.4',
  'background-secondary-3': 'neutral.6',

  'foreground-secondary': 'neutral.12',
  'foreground-secondary-muted': 'neutral.11',
  'foreground-secondary-passive': 'neutral.9',

  // ── Tertiary (code editors / inset panels) ────────────────────────────────
  'background-tertiary': 'neutral.3',
  'background-tertiary-1': 'neutral.4',
  'background-tertiary-2': 'neutral.5',
  'background-tertiary-3': 'neutral.6',

  'foreground-tertiary': 'neutral.12',
  'foreground-tertiary-muted': 'neutral.11',
  'foreground-tertiary-passive': 'neutral.9',

  // ── Quaternary ────────────────────────────────────────────────────────────
  'background-quaternary': 'neutral.1',
  'background-quaternary-1': 'neutral.2',
  'background-quaternary-2': 'neutral.3',

  // ── Neutral (inverted / pill) ─────────────────────────────────────────────
  'background-neutral': 'neutral.12',
  'foreground-neutral': 'neutral.1',

  // ── Primary button ────────────────────────────────────────────────────────
  'primary-button-background': 'accent.9',
  'primary-button-background-hover': 'accent.10',
  'primary-button-foreground': 'accent.contrast',
  'primary-button-border': 'accent.7',

  // ── Destructive (red) ─────────────────────────────────────────────────────
  'background-destructive': 'red.3',
  'background-destructive-1': 'red.2',
  'foreground-destructive': 'red.11',
  'foreground-destructive-muted': 'red.9',

  // ── Borders ───────────────────────────────────────────────────────────────
  border: 'neutral.6',
  'border-1': 'neutral.7',
  'border-2': 'neutral.8',
  'border-subtle': 'neutral.5',
  'border-destructive': 'red.8',
  'border-primary': 'neutral.9',

  // ── Selection (blue) ──────────────────────────────────────────────────────
  selection: 'blue.6',
  'selection-foreground': 'blue.12',

  // ── Status ────────────────────────────────────────────────────────────────
  'status-in-progress': 'amber.11',
  'status-in-review': 'green.10',
  'status-done': 'neutral.9',
  'status-todo': 'neutral.9',
  'status-cancelled': 'neutral.9',

  // ── Diff ──────────────────────────────────────────────────────────────────
  'foreground-diff-added': 'green.9',
  'foreground-diff-modified': 'amber.9',
  'foreground-diff-deleted': 'red.9',

  // ── Semantic state sets ───────────────────────────────────────────────────
  // success → green
  'foreground-success': 'green.9',
  'background-success': 'green.3',
  'background-success-hover': 'green.4',
  'border-success': 'green.7',

  // error → red
  'foreground-error': 'red.9',
  'background-error': 'red.3',
  'background-error-hover': 'red.4',
  'border-error': 'red.7',

  // warning → amber
  'foreground-warning': 'amber.11',
  'background-warning': 'amber.3',
  'background-warning-hover': 'amber.4',
  'border-warning': 'amber.7',

  // info → blue
  'foreground-info': 'blue.9',
  'background-info': 'blue.3',
  'background-info-hover': 'blue.4',
  'border-info': 'blue.7',

  // ── VCS state extras ──────────────────────────────────────────────────────
  // merge conflict → orange; merged PR → purple (GitHub convention)
  'foreground-conflict': 'orange.11',
  'foreground-merged': 'purple.9',
} as const;

export type SemanticSlot = keyof typeof SEMANTIC_TEMPLATE;
export type SemanticVar = string;

import { nsName } from './namespace';

/** Array of all semantic CSS custom property names for runtime validation. */
export const SEMANTIC_VARS: readonly SemanticVar[] = Object.keys(SEMANTIC_TEMPLATE).map((k) =>
  nsName(k)
);
