/**
 * surface.css.ts — Vanilla Extract recipe for surface-level containers.
 *
 * Applies the surface cascade vars to an element so it reads from the correct
 * level in the elevation hierarchy. Wraps the same scope-class semantics as
 * surfaces.css.ts but makes them composable with VE recipe().
 *
 * Usage:
 *   import { surface } from '@emdash/ui/styles/recipes/surface';
 *   <div className={surface({ level: 'elevated', interactive: true })} />
 *
 * Variants:
 *   level       — sunken | base | elevated | paper (default: base)
 *   status      — destructive | warning | info | success (default: none)
 *   interactive — true | false: adds hover/selected cursor + transition
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

export const surface = recipe({
  base: {
    backgroundColor: vars.surface,
    color: vars.foreground,
  },

  variants: {
    level: {
      // Sunken — recessed, below the base plane (sidebars, trays)
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
      // Base — default surface level (content areas, cards on sunken canvas)
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
      // Elevated — raised above base (popovers, dialogs, dropdowns)
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
      // Paper — maximum elevation (tooltip-level, floating panels)
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

    interactive: {
      true: {
        cursor: 'pointer',
        transition: 'background-color 150ms, color 150ms',
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
  },
});

export type SurfaceVariants = RecipeVariants<typeof surface>;
