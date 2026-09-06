import { keyframes, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
// Side-effect import so the @layer order declaration is emitted before these
// rules; otherwise `recipes` gets registered first and loses to app layers.
import '@styles/layers.css';

const dotPulse = keyframes({
  '0%, 18%': {
    opacity: 1,
    transform: 'scale(1)',
  },
  '38%, 100%': {
    opacity: 0.28,
    transform: 'scale(0.8)',
  },
});

const DOT_COUNT = 4;
const PERIOD_MS = 1000;
const dotStaticOpacity = [1, 0.72, 0.48, 0.32];

export const root = style({
  '@layer': {
    recipes: {
      display: 'inline-flex',
      width: 'var(--script-status-size, 1.5rem)',
      height: 'var(--script-status-size, 1.5rem)',
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

export const successIcon = style({
  '@layer': {
    recipes: {
      color: vars.foregroundSuccess,
    },
  },
});

export const errorIcon = style({
  '@layer': {
    recipes: {
      color: vars.foregroundError,
    },
  },
});

export const inProgressIcon = style({
  '@layer': {
    recipes: {
      color: vars.foregroundMuted,
    },
  },
});

export const dot = Array.from({ length: DOT_COUNT }, (_, index) =>
  style({
    '@layer': {
      recipes: {
        fill: 'currentColor',
        opacity: 0.28,
        transform: 'scale(0.8)',
        transformBox: 'fill-box',
        transformOrigin: 'center',
        animationName: dotPulse,
        animationDuration: `${PERIOD_MS}ms`,
        animationTimingFunction: 'ease-in-out',
        animationIterationCount: 'infinite',
        animationDelay: `${-((DOT_COUNT - index) % DOT_COUNT) * (PERIOD_MS / DOT_COUNT)}ms`,
        '@media': {
          '(prefers-reduced-motion: reduce)': {
            animationName: 'none',
            opacity: dotStaticOpacity[index]?.toString() ?? '0.48',
            transform: 'scale(0.9)',
          },
        },
      },
    },
  })
);

export const waitingIcon = style({
  '@layer': {
    recipes: {
      color: vars.foregroundPassive,
    },
  },
});

export const cancelledIcon = style({
  '@layer': {
    recipes: {
      color: vars.foregroundMuted,
    },
  },
});
