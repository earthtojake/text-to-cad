/**
 * box — variant-driven layout/spacing/border/background recipe.
 *
 * A class-first alternative to the Box component for statically-known
 * combinations. Defaults to `display: flex, direction: row`.
 *
 * Usage:
 *   import { box } from '@emdash/ui/styles/recipes/box';
 *   <div className={box({ display: 'flex', direction: 'column', gap: '2', padding: '3' })} />
 */

import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import { tokenVars } from '../../theme/tokens.css';
import { vars } from '@theme/core/contract/contract.css';

// Spacing scale keys map 1:1 to Tailwind numeric suffixes so the DX is
// familiar: gap='2' → 0.5rem, gap='4' → 1rem, gap='6' → 1.5rem, etc.
const SPACE: Record<string, string> = {
  '0': '0px',
  '0.5': '0.125rem',
  '1': '0.25rem',
  '1.5': '0.375rem',
  '2': '0.5rem',
  '2.5': '0.625rem',
  '3': '0.75rem',
  '4': '1rem',
  '6': '1.5rem',
  '8': '2rem',
};

const gapVariants = Object.fromEntries(
  Object.entries(SPACE).map(([k, v]) => [k, { gap: v }])
) as Record<keyof typeof SPACE, { gap: string }>;

const paddingVariants = Object.fromEntries(
  Object.entries(SPACE).map(([k, v]) => [k, { padding: v }])
) as Record<keyof typeof SPACE, { padding: string }>;

export const box = recipe({
  base: {},

  variants: {
    display: {
      flex: { display: 'flex' },
      grid: { display: 'grid' },
      block: { display: 'block' },
      'inline-flex': { display: 'inline-flex' },
      none: { display: 'none' },
    },

    direction: {
      row: { flexDirection: 'row' },
      column: { flexDirection: 'column' },
    },

    align: {
      start: { alignItems: 'flex-start' },
      center: { alignItems: 'center' },
      end: { alignItems: 'flex-end' },
      stretch: { alignItems: 'stretch' },
      baseline: { alignItems: 'baseline' },
    },

    justify: {
      start: { justifyContent: 'flex-start' },
      center: { justifyContent: 'center' },
      end: { justifyContent: 'flex-end' },
      between: { justifyContent: 'space-between' },
    },

    wrap: {
      true: { flexWrap: 'wrap' },
    },

    gap: gapVariants,

    padding: paddingVariants,

    radius: {
      none: { borderRadius: 0 },
      sm: { borderRadius: tokenVars.radiusSm },
      md: { borderRadius: tokenVars.radiusMd },
      lg: { borderRadius: tokenVars.radiusLg },
      xl: { borderRadius: tokenVars.radiusXl },
    },

    border: {
      true: { border: `1px solid ${vars.border}` },
    },

    background: {
      none: { backgroundColor: 'transparent' },
      input: { backgroundColor: vars.surfaceInput },
      surface: { backgroundColor: vars.surface },
    },
  },

  defaultVariants: {
    display: 'flex',
    direction: 'row',
  },
});

export type BoxVariants = RecipeVariants<typeof box>;
