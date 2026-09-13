/**
 * Toast styling — restyles sonner onto the --em-* token contract.
 *
 * Sonner themes itself through CSS custom properties declared on
 * `[data-sonner-toaster][data-sonner-theme=…]` selectors and styles its
 * internals via data-attribute selectors on DOM it owns. Its only theming
 * hooks are those variables and CSS targeting those attributes, so the
 * overrides below are attribute-scoped globalStyles by necessity (this is
 * third-party DOM, not an @emdash/ui component boundary). Every selector is
 * anchored on the doubled `toaster` class so it outranks sonner's injected
 * stylesheet regardless of insertion order.
 */

import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const toaster = style({
  selectors: {
    // (0,3,0) — beats sonner's (0,2,0) theme-default variable declarations.
    '&&[data-sonner-toaster]': {
      fontFamily: tokenVars.fontSans,
      vars: {
        '--normal-bg': vars.background,
        '--normal-border': vars.border,
        '--normal-text': vars.foreground,
        '--border-radius': tokenVars.radiusMd,
      },
    },
  },
});

const scope = `${toaster}${toaster}[data-sonner-toaster]`;
const toastEl = `${scope} [data-sonner-toast][data-styled='true']`;

globalStyle(toastEl, {
  boxShadow: `${vars.shadowMd}, 0 0 0 1px color-mix(in srgb, ${vars.foreground} 10%, transparent)`,
  borderColor: 'transparent',
});

// Sonner hardcodes description colors per light/dark theme; own them instead.
globalStyle(`${toastEl} [data-description]`, {
  color: vars.foregroundMuted,
});

// Tone-colored status icons on an otherwise neutral surface.
const TONE_ICON_COLORS = {
  success: vars.foregroundSuccess,
  error: vars.foregroundError,
  warning: vars.foregroundWarning,
  info: vars.foregroundInfo,
} as const;

for (const [type, color] of Object.entries(TONE_ICON_COLORS)) {
  globalStyle(`${scope} [data-sonner-toast][data-type='${type}'] [data-icon]`, { color });
}

// Promise-toast loading spinner bars (sonner defaults them to its gray ramp).
globalStyle(`${scope} .sonner-loading-bar`, {
  backgroundColor: vars.foregroundMuted,
});

// Action button reads as the primary button.
globalStyle(`${toastEl} [data-button]`, {
  backgroundColor: vars.primaryButtonBackground,
  color: vars.primaryButtonForeground,
  cursor: 'pointer',
});

globalStyle(`${toastEl} [data-button]:hover`, {
  backgroundColor: vars.primaryButtonBackgroundHover,
});
