/**
 * surfaces.css.ts — VE surface cascade system.
 *
 * Replaces the hand-written surfaces.css with typed Vanilla Extract globalStyle
 * calls driven by the same contract vars that all component styles use.
 *
 * Two concerns handled here:
 *  1. Default cascade binding — emitted on :root AND every .em<id> theme selector
 *     so the generic --surface vars resolve correctly regardless of where the theme
 *     class is applied (wrapper div in Storybook, documentElement in Electron).
 *  2. Scope classes — .surface-<level>, .surface-emphasis, status rooms — rebind
 *     the generic vars to the appropriate level tokens.
 *
 * Elevation hierarchy (darkest → lightest in both modes):
 *   surface-sunken  → surface-base → surface-base-emphasis
 *   → surface-elevated → surface-elevated-emphasis
 *
 * Status rooms (destructive/warning/info/success) carry per-elevation-scope
 * variants generated at theme build time. Each elevation scope class rebinds
 * the effective --surface-<status>* cascade vars to the canvas-matched tokens
 * so a status room inside any elevation context reads with the correct lightness.
 */

import { SURFACE_STATUSES } from '@emdash/theme';
import { THEME_MANIFEST } from '@emdash/theme/manifest';
import { globalStyle } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Build a CSS color-mix expression as a static string for VE. */
function colorMix(a: string, pct: number, b: string): string {
  return `color-mix(in srgb, ${a} ${pct}%, ${b})`;
}

const toCamel = (s: string) => s.replace(/-([a-z0-9])/g, (_: string, c: string) => c.toUpperCase());
const vv = vars as unknown as Record<string, string>;

/**
 * Returns a vars object that rebinds each status surface's effective cascade
 * vars to the per-scope generated tokens for the given elevation scope name.
 * Spread this into the elevation scope class's `vars` block so any status room
 * nested inside (or applied on the same element) uses the canvas-matched tint.
 */
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

// ── 1. Default cascade binding (robust — works wherever .em<id> lands) ────────

const themeSelectors = THEME_MANIFEST.map((t) => t.selector).join(', ');
const defaultCascadeSelectors = `:root, ${themeSelectors}`;

globalStyle(defaultCascadeSelectors, {
  vars: {
    // Default to base elevation
    [vars.surface]: vars.surfaceBase,
    [vars.surfaceHover]: vars.surfaceBaseHover,
    [vars.surfaceSelected]: vars.surfaceBaseSelected,
    [vars.surfaceEmphasis]: vars.surfaceBaseEmphasis,
    [vars.surfaceEmphasisHover]: vars.surfaceBaseEmphasisHover,
    [vars.surfaceEmphasisSelected]: vars.surfaceBaseEmphasisSelected,
    // Computed from the current surface + foreground (adapts automatically)
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
    // Status-relative vars — undefined by default (no active status room)
    // Components that need these on a plain surface use direct level vars.
  },
});

// ── 2. Elevation scope classes ────────────────────────────────────────────────

globalStyle('.surface-sunken', {
  vars: {
    [vars.surface]: vars.surfaceSunken,
    [vars.surfaceHover]: vars.surfaceSunkenHover,
    [vars.surfaceSelected]: vars.surfaceSunkenSelected,
    // Cards on sunken canvas use base
    [vars.surfaceEmphasis]: vars.surfaceBase,
    [vars.surfaceEmphasisHover]: vars.surfaceBaseHover,
    [vars.surfaceEmphasisSelected]: vars.surfaceBaseSelected,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
    // Status rooms on sunken canvas use canvas-matched tints
    ...statusRebindings('sunken'),
  },
});

globalStyle('.surface-base', {
  vars: {
    [vars.surface]: vars.surfaceBase,
    [vars.surfaceHover]: vars.surfaceBaseHover,
    [vars.surfaceSelected]: vars.surfaceBaseSelected,
    [vars.surfaceEmphasis]: vars.surfaceBaseEmphasis,
    [vars.surfaceEmphasisHover]: vars.surfaceBaseEmphasisHover,
    [vars.surfaceEmphasisSelected]: vars.surfaceBaseEmphasisSelected,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
  },
});

globalStyle('.surface-elevated', {
  vars: {
    [vars.surface]: vars.surfaceElevated,
    [vars.surfaceHover]: vars.surfaceElevatedHover,
    [vars.surfaceSelected]: vars.surfaceElevatedSelected,
    [vars.surfaceEmphasis]: vars.surfaceElevatedEmphasis,
    [vars.surfaceEmphasisHover]: vars.surfaceElevatedEmphasisHover,
    [vars.surfaceEmphasisSelected]: vars.surfaceElevatedEmphasisSelected,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
    // Status rooms on elevated canvas use canvas-matched tints
    ...statusRebindings('elevated'),
  },
});

globalStyle('.surface-base-emphasis', {
  vars: {
    [vars.surface]: vars.surfaceBaseEmphasis,
    [vars.surfaceHover]: vars.surfaceBaseEmphasisHover,
    [vars.surfaceSelected]: vars.surfaceBaseEmphasisSelected,
    // Next rung up: elevated
    [vars.surfaceEmphasis]: vars.surfaceElevated,
    [vars.surfaceEmphasisHover]: vars.surfaceElevatedHover,
    [vars.surfaceEmphasisSelected]: vars.surfaceElevatedSelected,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
    // Status rooms on base-emphasis canvas use canvas-matched tints
    ...statusRebindings('base-emphasis'),
  },
});

globalStyle('.surface-elevated-emphasis', {
  vars: {
    [vars.surface]: vars.surfaceElevatedEmphasis,
    [vars.surfaceHover]: vars.surfaceElevatedEmphasisHover,
    [vars.surfaceSelected]: vars.surfaceElevatedEmphasisSelected,
    // Top of the ladder — clamps to itself
    [vars.surfaceEmphasis]: vars.surfaceElevatedEmphasis,
    [vars.surfaceEmphasisHover]: vars.surfaceElevatedEmphasisHover,
    [vars.surfaceEmphasisSelected]: vars.surfaceElevatedEmphasisSelected,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
    // Status rooms on elevated-emphasis canvas use canvas-matched tints
    ...statusRebindings('elevated-emphasis'),
  },
});

// ── 3. Semantic role: paper ───────────────────────────────────────────────────

globalStyle('.surface-paper', {
  vars: {
    [vars.surface]: vars.surfacePaper,
    [vars.surfaceHover]: vars.surfacePaperHover,
    [vars.surfaceSelected]: vars.surfacePaperSelected,
    // Cards on paper use base-emphasis
    [vars.surfaceEmphasis]: vars.surfaceBaseEmphasis,
    [vars.surfaceEmphasisHover]: vars.surfaceBaseEmphasisHover,
    [vars.surfaceEmphasisSelected]: vars.surfaceBaseEmphasisSelected,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
    // Status rooms on paper canvas use canvas-matched tints
    ...statusRebindings('paper'),
  },
});

// ── 4. Generic emphasis clamp ─────────────────────────────────────────────────
//
// A card/tab adopts its canvas's emphasis color as its own surface.
// --surface-emphasis is NOT re-declared here to avoid a dependency cycle
// (re-declaring a custom property in terms of itself → guaranteed-invalid value).
// By leaving it inherited, nested cards clamp to the same emphasis level.

globalStyle('.surface-emphasis', {
  vars: {
    [vars.surface]: vars.surfaceEmphasis,
    [vars.surfaceHover]: vars.surfaceEmphasisHover,
    [vars.surfaceSelected]: vars.surfaceEmphasisSelected,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
  },
});

// ── 5. Status surface rooms ───────────────────────────────────────────────────
//
// Colored "rooms" derived from the red / amber / blue ramps.
// Generic --surface-* and --surface-emphasis-* are rebound so any ghost
// Button / Toggle / Tab inside a status box hovers/selects with the correct tint.
// The emphasis vars clamp to the selected state (no additional elevation step).

globalStyle('.surface-destructive', {
  vars: {
    [vars.surface]: vars.surfaceDestructive,
    [vars.surfaceHover]: vars.surfaceDestructiveHover,
    [vars.surfaceSelected]: vars.surfaceDestructiveSelected,
    [vars.surfaceEmphasis]: vars.surfaceDestructiveSelected,
    [vars.surfaceEmphasisHover]: vars.surfaceDestructiveSelected,
    [vars.surfaceEmphasisSelected]: vars.surfaceDestructiveSelected,
    [vars.surfaceBorder]: vars.surfaceDestructiveBorder,
    [vars.surfaceForeground]: vars.surfaceDestructiveForeground,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
  },
});

globalStyle('.surface-warning', {
  vars: {
    [vars.surface]: vars.surfaceWarning,
    [vars.surfaceHover]: vars.surfaceWarningHover,
    [vars.surfaceSelected]: vars.surfaceWarningSelected,
    [vars.surfaceEmphasis]: vars.surfaceWarningSelected,
    [vars.surfaceEmphasisHover]: vars.surfaceWarningSelected,
    [vars.surfaceEmphasisSelected]: vars.surfaceWarningSelected,
    [vars.surfaceBorder]: vars.surfaceWarningBorder,
    [vars.surfaceForeground]: vars.surfaceWarningForeground,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
  },
});

globalStyle('.surface-info', {
  vars: {
    [vars.surface]: vars.surfaceInfo,
    [vars.surfaceHover]: vars.surfaceInfoHover,
    [vars.surfaceSelected]: vars.surfaceInfoSelected,
    [vars.surfaceEmphasis]: vars.surfaceInfoSelected,
    [vars.surfaceEmphasisHover]: vars.surfaceInfoSelected,
    [vars.surfaceEmphasisSelected]: vars.surfaceInfoSelected,
    [vars.surfaceBorder]: vars.surfaceInfoBorder,
    [vars.surfaceForeground]: vars.surfaceInfoForeground,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
  },
});

globalStyle('.surface-success', {
  vars: {
    [vars.surface]: vars.surfaceSuccess,
    [vars.surfaceHover]: vars.surfaceSuccessHover,
    [vars.surfaceSelected]: vars.surfaceSuccessSelected,
    [vars.surfaceEmphasis]: vars.surfaceSuccessSelected,
    [vars.surfaceEmphasisHover]: vars.surfaceSuccessSelected,
    [vars.surfaceEmphasisSelected]: vars.surfaceSuccessSelected,
    [vars.surfaceBorder]: vars.surfaceSuccessBorder,
    [vars.surfaceForeground]: vars.surfaceSuccessForeground,
    [vars.surfaceInput]: colorMix(vars.surface, 94, vars.foreground),
  },
});
