/**
 * layout.css.ts — Composable layout utility classes.
 *
 * Each export is a stable class name built from sx() sprinkle atoms so it
 * participates in the `utilities` layer and can be overridden by a consumer
 * passing additional sx() props. Compose with cx() or spread alongside recipe
 * classes.
 *
 * Usage:
 *   import { row, stack, fill, truncate } from '@emdash/ui/styles/utilities';
 *   <div className={cx(row, 'gap-2')} />
 */

import { style } from '@vanilla-extract/css';
import { sx } from './sprinkles.css';

// ── Flex row helpers ─────────────────────────────────────────────────────────

/** Horizontal flex container, items aligned center. */
export const row = style([sx({ display: 'flex', flexDirection: 'row', alignItems: 'center' })]);

/** Horizontal flex container, items space-between + center-aligned. */
export const rowBetween = style([
  sx({
    display: 'flex',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  }),
]);

// ── Stack / vertical ─────────────────────────────────────────────────────────

/** Vertical flex container. */
export const stack = style([sx({ display: 'flex', flexDirection: 'column' })]);

// ── Centering ────────────────────────────────────────────────────────────────

/** Flex container that centers children both axes. */
export const center = style([
  sx({ display: 'flex', alignItems: 'center', justifyContent: 'center' }),
]);

// ── Sizing helpers ───────────────────────────────────────────────────────────

/** Flex child that expands to fill remaining space. */
export const fill = style([sx({ flex: '1' })]);

// ── Text overflow ─────────────────────────────────────────────────────────────

/** Single-line text overflow ellipsis. */
export const truncate = style({
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  minWidth: 0,
});

// ── Absolute overlay ─────────────────────────────────────────────────────────

/** Fills parent with absolute positioning (inset 0). */
export const overlay = style([sx({ position: 'absolute' }), { inset: 0 }]);
