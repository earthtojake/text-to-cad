/**
 * composer-contract.css.ts — ChatComposer theme contract.
 *
 * Emits, scoped to `composerThemeScope` under :where(.emlight)/:where(.emdark),
 * a bridge that maps every --em-* custom property read by the ChatComposer
 * subtree (Button, SplitButton, PromptEditor, notice band, permission band,
 * portaled dropdown) to a var(--composer-*, <polarity default>) expression.
 *
 * This makes the full composer subtree re-themeable by the host via a small,
 * documented --composer-* set, without the host importing @emdash/ui's color
 * theme sheets (theme.css / semantic.css).
 *
 * SCOPING
 * ───────
 * The bridge only applies inside elements carrying `composerThemeScope`.
 * ChatComposer puts the class on its root AND on every surface it portals out
 * of its DOM subtree (agent/model/permission dropdowns, MCP and context-usage
 * popovers, effort submenu, prompt-editor suggestion popups) — portals mount
 * under <body>, so they would otherwise escape a root-scoped bridge. Keeping
 * the redefinitions scoped means the host's app-wide --em-* values stay owned
 * by the theme sheets; the composer contract never leaks document-wide.
 * (Host --composer-* inputs are typically set on the theme root and inherit
 * into the portaled surfaces just fine.)
 *
 * The defaults mirror the generated light/dark @emdash/ui theme so the composer
 * renders correctly in Storybook (where the theme sheets ARE imported) and in any
 * host that does not override the --composer-* vars.
 *
 * PUBLIC CONTRACT — --composer-* variables
 * ─────────────────────────────────────────
 * Set any of these on a selector that inherits to the composer root to re-theme:
 *
 * Core foregrounds:
 *   --composer-fg                  main text color
 *   --composer-fg-muted            secondary / label text
 *   --composer-fg-passive          placeholder text
 *
 * Borders:
 *   --composer-border              default border color
 *   --composer-border-strong       hover / focus-within border
 *   --composer-border-focus        focus-ring outline color
 *
 * Surfaces (elevation ramp — base is the popup/menu bg, elevated is the shell):
 *   --composer-surface             base surface (menus, attachment remove btn)
 *   --composer-surface-hover       hover tint on base surface
 *   --composer-surface-selected    selected tint on base surface
 *   --composer-surface-elevated    elevated shell background (composer border bg)
 *   --composer-surface-elevated-hover  elevated shell hover tint
 *
 * Primary / send button (accent):
 *   --composer-accent              accent button background
 *   --composer-accent-hover        accent button hover background
 *   --composer-accent-fg           accent button foreground
 *   --composer-accent-border       accent button border
 *
 * Destructive / stop button:
 *   --composer-fg-destructive      destructive text and ghost-destructive color
 *   --composer-destructive-bg      primary-destructive button background
 *   --composer-border-destructive  primary-destructive button border / focus ring
 *   --composer-destructive-hover   primary/ghost destructive hover background
 *   --composer-destructive-selected primary/ghost destructive active background
 *
 * Error notice band (and primary-destructive ghost hover context):
 *   --composer-error-surface       error band background
 *   --composer-error-border        error band border
 *   --composer-error-fg            error band foreground
 *
 * Warning notice band:
 *   --composer-fg-warning          warning text
 *   --composer-warning-surface     warning band background
 *   --composer-warning-border      warning band border
 *   --composer-warning-surface-fg  warning band foreground
 *
 * Info notice band:
 *   --composer-fg-info             info text
 *   --composer-info-surface        info band background
 *   --composer-info-border         info band border
 *   --composer-info-surface-fg     info band foreground
 *
 * Legacy single-property override (pre-contract, still honoured):
 *   --composer-bg                  overrides the shell background directly
 *                                  (takes priority over --composer-surface-elevated)
 */

import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';

/**
 * Scope marker for the composer theme bridge. ChatComposer applies it to its
 * root element and to every portaled surface it renders (see SCOPING above).
 * The rules stay unlayered on purpose: the bridge redefines --em-* slots that
 * semantic.css declares inside `@layer tokens`, and staying unlayered keeps
 * the bridge authoritative regardless of where a host mounts the theme class.
 */
export const composerThemeScope = style({});

// Zero-specificity theme-conditional selectors for the scoped bridge. The
// theme class always sits above the scoped element (<html>, or a wrapper-mode
// provider element), so a descendant combinator is sufficient.
const lightScope = `:where(.emlight) :where(${composerThemeScope})`;
const darkScope = `:where(.emdark) :where(${composerThemeScope})`;

// ── Light defaults ─────────────────────────────────────────────────────────────
// Values mirror the generated @emdash/ui emlight theme (semantic.css + theme.css).

globalStyle(lightScope, {
  vars: {
    // Core foregrounds
    [vars.foreground]: 'var(--composer-fg, color(display-p3 0.1329 0.1309 0.1314))',
    [vars.foregroundMuted]: 'var(--composer-fg-muted, color(display-p3 0.3826 0.3787 0.3798))',
    [vars.foregroundPassive]: 'var(--composer-fg-passive, color(display-p3 0.5582 0.5525 0.554))',

    // Borders
    [vars.border]: 'var(--composer-border, color(display-p3 0.7703 0.7673 0.7681))',
    [vars.border1]: 'var(--composer-border-strong, color(display-p3 0.8109 0.8067 0.8078))',
    [vars.borderPrimary]: 'var(--composer-border-focus, color(display-p3 0.5582 0.5525 0.554))',
    [vars.borderDestructive]:
      'var(--composer-border-destructive, color(display-p3 1 0.5988 0.5722))',

    // Surface level vars (the cascade vars --em-surface/hover/selected in
    // surfaces.css.ts default to var(--em-surface-base) etc., so bridging the
    // level vars is sufficient to drive the full surface cascade):
    [vars.surfaceBase]: 'var(--composer-surface, color(display-p3 0.9543 0.9539 0.954))',
    [vars.surfaceBaseHover]: 'var(--composer-surface-hover, color(display-p3 0.9023 0.9019 0.902))',
    [vars.surfaceBaseSelected]:
      'var(--composer-surface-selected, color(display-p3 0.8508 0.8505 0.8506))',
    [vars.surfaceBaseEmphasis]:
      'var(--composer-surface-elevated, color(display-p3 0.9765 0.9762 0.9763))',
    [vars.surfaceBaseEmphasisHover]:
      'var(--composer-surface-elevated-hover, color(display-p3 0.9243 0.924 0.9241))',

    // Primary / send button
    [vars.primaryButtonBackground]: 'var(--composer-accent, color(display-p3 0 0.6298 0.4648))',
    [vars.primaryButtonBackgroundHover]:
      'var(--composer-accent-hover, color(display-p3 0 0.5868 0.4314))',
    [vars.primaryButtonForeground]: 'var(--composer-accent-fg, color(display-p3 1 1 1))',
    [vars.primaryButtonBorder]:
      'var(--composer-accent-border, color(display-p3 0.5072 0.8816 0.7469))',

    // Destructive / stop button + ghost-destructive
    [vars.foregroundDestructive]:
      'var(--composer-fg-destructive, color(display-p3 0.5963 0.2559 0.2471))',
    [vars.backgroundDestructive]:
      'var(--composer-destructive-bg, color(display-p3 0.9541 0.8772 0.8687))',
    [vars.surfaceDestructiveHover]:
      'var(--composer-destructive-hover, color(display-p3 0.9395 0.8204 0.8078))',
    [vars.surfaceDestructiveSelected]:
      'var(--composer-destructive-selected, color(display-p3 0.9377 0.7569 0.7389))',

    // Error notice band (surface-destructive is also the ghost-destructive room)
    [vars.surfaceDestructive]:
      'var(--composer-error-surface, color(display-p3 0.9541 0.8772 0.8687))',
    [vars.surfaceDestructiveBorder]:
      'var(--composer-error-border, color(display-p3 0.9467 0.685 0.6619))',
    [vars.surfaceDestructiveForeground]:
      'var(--composer-error-fg, color(display-p3 0.5963 0.2559 0.2471))',

    // Warning notice band
    [vars.foregroundWarning]: 'var(--composer-fg-warning, color(display-p3 0.4753 0.3235 0))',
    [vars.surfaceWarning]:
      'var(--composer-warning-surface, color(display-p3 0.9296 0.8956 0.8292))',
    [vars.surfaceWarningBorder]:
      'var(--composer-warning-border, color(display-p3 0.8723 0.7501 0.5113))',
    [vars.surfaceWarningForeground]:
      'var(--composer-warning-surface-fg, color(display-p3 0.4753 0.3235 0))',

    // Info notice band
    [vars.foregroundInfo]: 'var(--composer-fg-info, color(display-p3 0.2318 0.5438 0.9627))',
    [vars.surfaceInfo]: 'var(--composer-info-surface, color(display-p3 0.8604 0.9046 0.965))',
    [vars.surfaceInfoBorder]: 'var(--composer-info-border, color(display-p3 0.6279 0.7807 0.9926))',
    [vars.surfaceInfoForeground]:
      'var(--composer-info-surface-fg, color(display-p3 0.1721 0.3782 0.6587))',
  },
});

// ── Dark defaults ──────────────────────────────────────────────────────────────
// Values mirror the generated @emdash/ui emdark theme (semantic.css + theme.css).

globalStyle(darkScope, {
  vars: {
    // Core foregrounds
    [vars.foreground]: 'var(--composer-fg, color(display-p3 0.9151 0.9123 0.913))',
    [vars.foregroundMuted]: 'var(--composer-fg-muted, color(display-p3 0.7229 0.7185 0.7197))',
    [vars.foregroundPassive]: 'var(--composer-fg-passive, color(display-p3 0.5721 0.5663 0.5679))',

    // Borders
    [vars.border]: 'var(--composer-border, color(display-p3 0.2206 0.2181 0.2188))',
    [vars.border1]: 'var(--composer-border-strong, color(display-p3 0.3825 0.3788 0.3798))',
    [vars.borderPrimary]: 'var(--composer-border-focus, color(display-p3 0.5721 0.5663 0.5679))',
    [vars.borderDestructive]:
      'var(--composer-border-destructive, color(display-p3 0.7226 0.3212 0.31))',

    // Surface level vars
    [vars.surfaceBase]: 'var(--composer-surface, color(display-p3 0.0818 0.0817 0.0817))',
    [vars.surfaceBaseHover]:
      'var(--composer-surface-hover, color(display-p3 0.1177 0.1176 0.1176))',
    [vars.surfaceBaseSelected]:
      'var(--composer-surface-selected, color(display-p3 0.1552 0.155 0.1551))',
    [vars.surfaceBaseEmphasis]:
      'var(--composer-surface-elevated, color(display-p3 0.1177 0.1176 0.1176))',
    [vars.surfaceBaseEmphasisHover]:
      'var(--composer-surface-elevated-hover, color(display-p3 0.1552 0.155 0.1551))',

    // Primary / send button
    [vars.primaryButtonBackground]: 'var(--composer-accent, color(display-p3 0 0.6515 0.4817))',
    [vars.primaryButtonBackgroundHover]:
      'var(--composer-accent-hover, color(display-p3 0 0.7093 0.5371))',
    [vars.primaryButtonForeground]: 'var(--composer-accent-fg, color(display-p3 1 1 1))',
    [vars.primaryButtonBorder]: 'var(--composer-accent-border, color(display-p3 0 0.4243 0.3136))',

    // Destructive / stop button + ghost-destructive
    [vars.foregroundDestructive]:
      'var(--composer-fg-destructive, color(display-p3 0.9855 0.6116 0.5853))',
    [vars.backgroundDestructive]:
      'var(--composer-destructive-bg, color(display-p3 0.1618 0.1078 0.1029))',
    [vars.surfaceDestructiveHover]:
      'var(--composer-destructive-hover, color(display-p3 0.2137 0.1261 0.1194))',
    [vars.surfaceDestructiveSelected]:
      'var(--composer-destructive-selected, color(display-p3 0.2764 0.1365 0.1287))',

    // Error notice band
    [vars.surfaceDestructive]:
      'var(--composer-error-surface, color(display-p3 0.1618 0.1078 0.1029))',
    [vars.surfaceDestructiveBorder]:
      'var(--composer-error-border, color(display-p3 0.3495 0.1343 0.1295))',
    [vars.surfaceDestructiveForeground]:
      'var(--composer-error-fg, color(display-p3 0.9855 0.6116 0.5853))',

    // Warning notice band
    [vars.foregroundWarning]: 'var(--composer-fg-warning, color(display-p3 0.8581 0.6803 0.314))',
    [vars.surfaceWarning]:
      'var(--composer-warning-surface, color(display-p3 0.1463 0.1212 0.0721))',
    [vars.surfaceWarningBorder]:
      'var(--composer-warning-border, color(display-p3 0.2995 0.1946 0))',
    [vars.surfaceWarningForeground]:
      'var(--composer-warning-surface-fg, color(display-p3 0.8581 0.6803 0.314))',

    // Info notice band
    [vars.foregroundInfo]: 'var(--composer-fg-info, color(display-p3 0.2522 0.5635 0.9839))',
    [vars.surfaceInfo]: 'var(--composer-info-surface, color(display-p3 0.0959 0.1275 0.1712))',
    [vars.surfaceInfoBorder]: 'var(--composer-info-border, color(display-p3 0.1789 0.3709 0.6338))',
    [vars.surfaceInfoForeground]:
      'var(--composer-info-surface-fg, color(display-p3 0.5114 0.7307 1))',
  },
});
