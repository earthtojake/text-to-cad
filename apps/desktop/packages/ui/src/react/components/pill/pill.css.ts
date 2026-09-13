import { keyframes, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';
// Side-effect import so the @layer order declaration is emitted before these
// rules; otherwise `recipes` gets registered first and loses to app layers.
import '@styles/layers.css';

const dotPulse = keyframes({
  '0%, 100%': {
    opacity: 1,
  },
  '50%': {
    opacity: 0.4,
  },
});

export const root = style({
  '@layer': {
    recipes: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.375rem',
      padding: '0.125rem 0.75rem',
      borderRadius: tokenVars.radiusFull,
      fontSize: 'var(--em-text-xs)',
      fontWeight: 500,
      lineHeight: 'var(--em-text-xs--line-height)',
      whiteSpace: 'nowrap',
    },
  },
});

export const label = style({
  '@layer': {
    recipes: {
      color: 'currentColor',
    },
  },
});

export const dot = style({
  '@layer': {
    recipes: {
      width: '0.375rem',
      height: '0.375rem',
      borderRadius: '50%',
      backgroundColor: 'currentColor',
      flexShrink: 0,
    },
  },
});

export const pulsingDot = style({
  '@layer': {
    recipes: {
      animationName: dotPulse,
      animationDuration: '1.5s',
      animationTimingFunction: 'ease-in-out',
      animationIterationCount: 'infinite',
      '@media': {
        '(prefers-reduced-motion: reduce)': {
          animationName: 'none',
        },
      },
    },
  },
});

export const variant = {
  neutral: style({
    '@layer': {
      recipes: {
        color: vars.foregroundMuted,
        backgroundColor: `color-mix(in srgb, ${vars.foregroundMuted} 10%, transparent)`,
      },
    },
  }),
  success: style({
    '@layer': {
      recipes: {
        color: vars.foregroundSuccess,
        backgroundColor: `color-mix(in srgb, ${vars.foregroundSuccess} 12%, transparent)`,
      },
    },
  }),
  warning: style({
    '@layer': {
      recipes: {
        color: vars.foregroundWarning,
        backgroundColor: `color-mix(in srgb, ${vars.foregroundWarning} 12%, transparent)`,
      },
    },
  }),
  error: style({
    '@layer': {
      recipes: {
        color: vars.foregroundError,
        backgroundColor: `color-mix(in srgb, ${vars.foregroundError} 12%, transparent)`,
      },
    },
  }),
  info: style({
    '@layer': {
      recipes: {
        color: vars.foregroundInfo,
        backgroundColor: `color-mix(in srgb, ${vars.foregroundInfo} 12%, transparent)`,
      },
    },
  }),
};
