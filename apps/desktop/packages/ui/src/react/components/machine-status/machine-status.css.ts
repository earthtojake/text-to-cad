import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
// Side-effect import so the @layer order declaration is emitted before these
// rules; otherwise `recipes` gets registered first and loses to app layers.
import '@styles/layers.css';

export const root = style({
  '@layer': {
    recipes: {
      display: 'inline-flex',
      width: 'var(--machine-status-size, 1.5rem)',
      height: 'var(--machine-status-size, 1.5rem)',
      flexShrink: 0,
      alignItems: 'center',
      justifyContent: 'center',
      verticalAlign: 'middle',
    },
  },
});

export const icon = style({
  '@layer': {
    recipes: {
      display: 'block',
      width: '100%',
      height: '100%',
      overflow: 'visible',
    },
  },
});

export const backgroundSegment = style({
  '@layer': {
    recipes: {
      fill: vars.background3,
    },
  },
});

export const dot = style({
  '@layer': {
    recipes: {
      fill: vars.foreground,
      opacity: 0.6,
    },
  },
});

export const statusDot = style({
  '@layer': {
    recipes: {
      stroke: vars.background,
      strokeWidth: '1.5',
    },
  },
});

export const statusDotVariant = {
  idle: style({
    '@layer': {
      recipes: {
        fill: vars.foregroundMuted,
      },
    },
  }),
  successful: style({
    '@layer': {
      recipes: {
        fill: vars.foregroundSuccess,
      },
    },
  }),
  error: style({
    '@layer': {
      recipes: {
        fill: vars.foregroundError,
      },
    },
  }),
  initializing: style({
    '@layer': {
      recipes: {
        fill: vars.foregroundInfo,
      },
    },
  }),
};
