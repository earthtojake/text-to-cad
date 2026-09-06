import { style } from '@vanilla-extract/css';
import { popupShadowSm, popupSurfaceInverted } from '@styles/recipes/popup-surface.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const positioner = style({
  isolation: 'isolate',
  zIndex: 50,
});

export const content = style([
  popupSurfaceInverted,
  popupShadowSm,
  {
    display: 'inline-flex',
    width: 'fit-content',
    maxWidth: '20rem',
    alignItems: 'center',
    gap: '0.375rem',
    padding: '0.375rem 0.75rem',
    fontSize: tokenVars.textXs,
    lineHeight: tokenVars.textXsLineHeight,
    vars: {
      // Adapt Kbd keycaps rendered inside tooltip content to the inverted
      // surface via the custom-property hooks kbd.css exposes.
      '--kbd-bg': `color-mix(in srgb, ${vars.foregroundNeutral} 15%, transparent)`,
      '--kbd-border': `color-mix(in srgb, ${vars.foregroundNeutral} 20%, transparent)`,
      '--kbd-color': vars.foregroundNeutral,
    },
  },
]);

export const arrow = style({
  zIndex: 50,
  width: '0.625rem',
  height: '0.625rem',
  borderRadius: '2px',
  backgroundColor: vars.backgroundNeutral,
  transform: 'translateY(calc(-50% - 2px)) rotate(45deg)',
  selectors: {
    '&[data-side="bottom"]': { top: '0.25rem' },
    '&[data-side="top"]': { bottom: '-0.625rem' },
    '&[data-side="left"], &[data-side="inline-start"]': {
      top: '50%',
      right: '-0.25rem',
      transform: 'translateY(-50%) rotate(45deg)',
    },
    '&[data-side="right"], &[data-side="inline-end"]': {
      top: '50%',
      left: '-0.25rem',
      transform: 'translateY(-50%) rotate(45deg)',
    },
  },
});
