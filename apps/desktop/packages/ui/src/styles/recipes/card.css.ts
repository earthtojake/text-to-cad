/**
 * card.css.ts — Vanilla Extract recipe for card containers.
 *
 * Composes the surface recipe for elevation + border + radius + padding.
 * The card pattern appears across ~88 desktop renderer files — highest-leverage
 * abstraction in the design system.
 *
 * Usage:
 *   import { card } from '@emdash/ui/styles/recipes/card';
 *   <div className={card({ padding: 'md', interactive: true })} />
 *
 * Variants:
 *   padding     — none | sm | md | lg (default: md)
 *   radius      — sm | md | lg (default: md)
 *   interactive — true | false: hover/selected state (default: false)
 *   level       — sunken | base | elevated | paper (default: base)
 *   status      — destructive | warning | info | success (optional)
 *
 * Status rooms are level-aware: when both `level` and `status` are set on the
 * same element, the level variant rebinds the effective --surface-<status>*
 * cascade vars to the canvas-matched tints generated at theme build time.
 */

import { SURFACE_STATUSES } from '@emdash/theme';
import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
// Relative import: the dts emitter rewrites aliased imports to a dangling
// relative path, silently degrading the exported types.
import { vars } from '../../theme/core/contract/contract.css';
import { tokenVars } from '../../theme/tokens.css';

const toCamel = (s: string) => s.replace(/-([a-z0-9])/g, (_: string, c: string) => c.toUpperCase());
const vv = vars as unknown as Record<string, string>;

function statusRebindings(scope: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const status of SURFACE_STATUSES) {
    for (const sub of ['', '-hover', '-selected', '-border', '-foreground']) {
      const effectiveKey = toCamel(`surface-${status}${sub}`);
      const scopeKey = toCamel(`surface-${status}-${scope}${sub}`);
      result[vv[effectiveKey]] = vv[scopeKey];
    }
  }
  return result;
}

export const card = recipe({
  base: {
    backgroundColor: vars.surface,
    color: vars.foreground,
    border: `1px solid ${vars.surfaceBorder}`,
    overflow: 'hidden',
  },

  variants: {
    level: {
      sunken: {
        vars: {
          [vars.surface]: vars.surfaceSunken,
          [vars.surfaceHover]: vars.surfaceSunkenHover,
          [vars.surfaceSelected]: vars.surfaceSunkenSelected,
          [vars.surfaceEmphasis]: vars.surfaceBase,
          [vars.surfaceEmphasisHover]: vars.surfaceBaseHover,
          [vars.surfaceEmphasisSelected]: vars.surfaceBaseEmphasisSelected,
          ...statusRebindings('sunken'),
        },
      },
      base: {
        vars: {
          [vars.surface]: vars.surfaceBase,
          [vars.surfaceHover]: vars.surfaceBaseHover,
          [vars.surfaceSelected]: vars.surfaceBaseSelected,
          [vars.surfaceEmphasis]: vars.surfaceBaseEmphasis,
          [vars.surfaceEmphasisHover]: vars.surfaceBaseEmphasisHover,
          [vars.surfaceEmphasisSelected]: vars.surfaceBaseEmphasisSelected,
          // base is the default — no status rebindings needed
        },
      },
      elevated: {
        vars: {
          [vars.surface]: vars.surfaceElevated,
          [vars.surfaceHover]: vars.surfaceElevatedHover,
          [vars.surfaceSelected]: vars.surfaceElevatedSelected,
          [vars.surfaceEmphasis]: vars.surfaceElevatedEmphasis,
          [vars.surfaceEmphasisHover]: vars.surfaceElevatedEmphasisHover,
          [vars.surfaceEmphasisSelected]: vars.surfaceElevatedEmphasisSelected,
          ...statusRebindings('elevated'),
        },
      },
      paper: {
        vars: {
          [vars.surface]: vars.surfacePaper,
          [vars.surfaceHover]: vars.surfacePaperHover,
          [vars.surfaceSelected]: vars.surfacePaperSelected,
          [vars.surfaceEmphasis]: vars.surfaceElevatedEmphasis,
          [vars.surfaceEmphasisHover]: vars.surfaceElevatedEmphasisHover,
          [vars.surfaceEmphasisSelected]: vars.surfaceElevatedEmphasisSelected,
          ...statusRebindings('paper'),
        },
      },
    },

    status: {
      destructive: {
        vars: {
          [vars.surface]: vars.surfaceDestructive,
          [vars.surfaceForeground]: vars.surfaceDestructiveForeground,
          [vars.surfaceBorder]: vars.surfaceDestructiveBorder,
          [vars.surfaceHover]: vars.surfaceDestructiveHover,
          [vars.surfaceSelected]: vars.surfaceDestructiveSelected,
        },
      },
      warning: {
        vars: {
          [vars.surface]: vars.surfaceWarning,
          [vars.surfaceForeground]: vars.surfaceWarningForeground,
          [vars.surfaceBorder]: vars.surfaceWarningBorder,
          [vars.surfaceHover]: vars.surfaceWarningHover,
          [vars.surfaceSelected]: vars.surfaceWarningSelected,
        },
      },
      info: {
        vars: {
          [vars.surface]: vars.surfaceInfo,
          [vars.surfaceForeground]: vars.surfaceInfoForeground,
          [vars.surfaceBorder]: vars.surfaceInfoBorder,
          [vars.surfaceHover]: vars.surfaceInfoHover,
          [vars.surfaceSelected]: vars.surfaceInfoSelected,
        },
      },
      success: {
        vars: {
          [vars.surface]: vars.surfaceSuccess,
          [vars.surfaceForeground]: vars.surfaceSuccessForeground,
          [vars.surfaceBorder]: vars.surfaceSuccessBorder,
          [vars.surfaceHover]: vars.surfaceSuccessHover,
          [vars.surfaceSelected]: vars.surfaceSuccessSelected,
        },
      },
    },

    radius: {
      sm: { borderRadius: tokenVars.radiusSm },
      md: { borderRadius: tokenVars.radiusMd },
      lg: { borderRadius: tokenVars.radiusLg },
    },

    padding: {
      none: { padding: 0 },
      sm: { padding: '0.5rem' },
      md: { padding: '0.75rem' },
      lg: { padding: '1rem' },
    },

    interactive: {
      true: {
        cursor: 'pointer',
        transition: 'background-color 150ms',
        selectors: {
          '&:hover': { backgroundColor: vars.surfaceHover },
          '&[data-selected]': { backgroundColor: vars.surfaceSelected },
          '&[aria-selected="true"]': { backgroundColor: vars.surfaceSelected },
        },
      },
    },
  },

  defaultVariants: {
    level: 'base',
    radius: 'md',
    padding: 'md',
  },
});

export type CardVariants = RecipeVariants<typeof card>;
