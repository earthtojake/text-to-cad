/**
 * story-layout.css.ts — escape-hatch VE classes for Storybook stories.
 *
 * Only exports that cannot be expressed via the `sx()` sprinkles (off-scale
 * sizes, grid templates, child-combinator selectors, transforms, effects, and
 * the composite storyTabButton) live here. Everything else uses Box props or
 * inline sx({...}).
 *
 * NOT shipped in the production build (tree-shaken; only story files import this).
 */

import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

// ── Escape-hatch transforms / positioning ─────────────────────────────────────

export const mxAuto = style({ marginLeft: 'auto', marginRight: 'auto' });
export const negTop2 = style({ top: '-0.5rem' });
export const left50pct = style({ left: '50%' });
export const negTranslateX = style({ transform: 'translateX(-50%)' });
export const negTranslateY = style({ transform: 'translateY(-100%)' });

// ── Fixed-px widths (not in the sx SPACE scale) ───────────────────────────────

export const w12 = style({ width: '3rem' });
export const w16 = style({ width: '4rem' });
export const w36 = style({ width: '9rem' });
export const w40 = style({ width: '10rem' });
export const w44 = style({ width: '11rem' });
export const w48 = style({ width: '12rem' });
export const w52 = style({ width: '13rem' });
export const w64 = style({ width: '16rem' });
export const w72 = style({ width: '18rem' });
export const w80 = style({ width: '20rem' });
export const w96 = style({ width: '24rem' });
export const maxW2xl = style({ maxWidth: '42rem' });
export const maxWProse = style({ maxWidth: '65ch' });

// ── Fixed-px heights ──────────────────────────────────────────────────────────

export const h6 = style({ height: '1.5rem' });
export const h7 = style({ height: '1.75rem' });
export const h8 = style({ height: '2rem' });
export const h10 = style({ height: '2.5rem' });
export const h16 = style({ height: '4rem' });
export const h40 = style({ height: '10rem' });
export const h48 = style({ height: '12rem' });
export const hScreen = style({ height: '100vh' });
export const minHScreen = style({ minHeight: '100vh' });
export const maxH50vh = style({ maxHeight: '50vh' });

// ── Square sizes ──────────────────────────────────────────────────────────────

export const size15 = style({ width: '0.375rem', height: '0.375rem' });
export const size3 = style({ width: '0.75rem', height: '0.75rem' });
export const size35 = style({ width: '0.875rem', height: '0.875rem' });
export const size4 = style({ width: '1rem', height: '1rem' });

// ── Grid column templates ─────────────────────────────────────────────────────

export const cols1 = style({ gridTemplateColumns: 'repeat(1, minmax(0, 1fr))' });
export const cols2 = style({ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' });
export const cols3 = style({ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' });
export const cols4 = style({ gridTemplateColumns: 'repeat(4, minmax(0, 1fr))' });
export const cols5 = style({ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' });
export const cols12 = style({ gridTemplateColumns: 'repeat(12, minmax(0, 1fr))' });

export const lgCols2 = style({
  '@media': { '(min-width: 1024px)': { gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' } },
});
export const lgCols3 = style({
  '@media': { '(min-width: 1024px)': { gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' } },
});
export const lgCols7 = style({
  '@media': { '(min-width: 1024px)': { gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' } },
});

// ── Child-combinator selectors (cannot be expressed in sprinkles) ─────────────

export const divideX = style({});
globalStyle(`${divideX} > * + *`, { borderLeftWidth: '1px', borderLeftStyle: 'solid' });

export const divideBorder = style({});
globalStyle(`${divideBorder} > * + *`, { borderColor: vars.border });

export const spaceY15 = style({});
globalStyle(`${spaceY15} > * + *`, { marginTop: '0.375rem' });

export const spaceY4 = style({});
globalStyle(`${spaceY4} > * + *`, { marginTop: '1rem' });

export const spaceY6 = style({});
globalStyle(`${spaceY6} > * + *`, { marginTop: '1.5rem' });

// ── Effects ───────────────────────────────────────────────────────────────────

export const shadowMd = style({
  boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1)',
});
export const backdropBlurSm = style({ backdropFilter: 'blur(4px)' });
export const transitionAll = style({ transition: 'all 150ms' });

// ── Off-scale type ────────────────────────────────────────────────────────────

export const text9px = style({ fontSize: '9px' });
export const text10px = style({ fontSize: '10px' });
export const text11px = style({ fontSize: '11px' });
export const text13px = style({ fontSize: '13px' });
export const trackingWider = style({ letterSpacing: '0.05em' });
export const outlineNone = style({ outline: 'none' });

// ── Special background ────────────────────────────────────────────────────────

/** color-mix transparency not expressible in sprinkles */
export const bgSurface80 = style({
  backgroundColor: `color-mix(in srgb, ${vars.surface} 80%, transparent)`,
});

// ── Composite: story tab strip button ────────────────────────────────────────

export const storyTabButton = style({
  display: 'inline-flex',
  height: '1.75rem',
  alignItems: 'center',
  gap: '0.375rem',
  borderRadius: tokenVars.radiusMd,
  border: '1px solid transparent',
  paddingLeft: '0.625rem',
  paddingRight: '0.625rem',
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
  transition: 'all 150ms',
  ':hover': {
    backgroundColor: vars.surfaceHover,
    color: vars.foreground,
  },
  selectors: {
    '&[data-active="true"]': {
      backgroundColor: vars.surfaceSelected,
      color: vars.foreground,
    },
  },
});
