import '@styles/layers.css';
import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const root = style({
  '@layer': {
    recipes: {
      position: 'relative',
      display: 'inline-flex',
      width: 'var(--workspace-icon-size, 2.25rem)',
      height: 'var(--workspace-icon-size, 2.25rem)',
      flexShrink: 0,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: tokenVars.radiusLg,
      backgroundColor: vars.surfaceEmphasis,
      color: vars.foregroundMuted,
      transition: 'background-color 100ms',
      selectors: {
        // Step up with the host row's hover so tile/row contrast is preserved:
        // the row paints surfaceHover while the tile paints surfaceEmphasisHover.
        "[data-slot='list-row']:hover &": {
          backgroundColor: vars.surfaceEmphasisHover,
        },
      },
    },
  },
});

export const icon = style({
  '@layer': {
    recipes: {
      display: 'block',
      // 1rem at the default 2.25rem tile size, scaling with the size prop.
      width: 'calc(var(--workspace-icon-size, 2.25rem) * 0.4444)',
      height: 'calc(var(--workspace-icon-size, 2.25rem) * 0.4444)',
    },
  },
});

export const statusDot = style({
  '@layer': {
    recipes: {
      position: 'absolute',
      right: '-0.125rem',
      bottom: '-0.125rem',
      // 0.625rem at the default 2.25rem tile size, scaling with the size prop.
      width: 'calc(var(--workspace-icon-size, 2.25rem) * 0.2778)',
      height: 'calc(var(--workspace-icon-size, 2.25rem) * 0.2778)',
      borderRadius: '50%',
      // Ring separating the dot from the tile and the surface behind it.
      boxShadow: `0 0 0 2px ${vars.surface}`,
      transition: 'box-shadow 100ms',
      selectors: {
        // Keep the ring matched to the hovered row background.
        "[data-slot='list-row']:hover &": {
          boxShadow: `0 0 0 2px ${vars.surfaceHover}`,
        },
      },
    },
  },
});

export const statusDotVariant = {
  active: style({
    '@layer': {
      recipes: {
        backgroundColor: vars.foregroundSuccess,
      },
    },
  }),
  idle: style({
    '@layer': {
      recipes: {
        backgroundColor: vars.foregroundMuted,
      },
    },
  }),
  'setting-up': style({
    '@layer': {
      recipes: {
        backgroundColor: vars.foregroundInfo,
      },
    },
  }),
  // `foregroundWarning` (amber.11) reads as dark brown in the light theme, so
  // the tearing-down dot uses the theme's bright amber solid (amber.9) instead.
  'tearing-down': style({
    '@layer': {
      recipes: {
        backgroundColor: vars.foregroundDiffModified,
      },
    },
  }),
  error: style({
    '@layer': {
      recipes: {
        backgroundColor: vars.foregroundError,
      },
    },
  }),
};
