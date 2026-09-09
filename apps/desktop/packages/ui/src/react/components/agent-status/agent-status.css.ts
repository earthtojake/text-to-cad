import { keyframes, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
// Side-effect import so the @layer order declaration is emitted before these
// rules; otherwise `recipes` gets registered first and loses to app layers.
import '@styles/layers.css';

const dotShimmer = keyframes({
  '0%, 100%': {
    opacity: 0.3,
    transform: 'scale(0.8)',
  },
  '35%': {
    opacity: 1,
    transform: 'scale(1.0)',
  },
  '68%': {
    opacity: 0.4,
    transform: 'scale(0.89)',
  },
});

const DOT_COUNT = 9;
const PERIOD_MS = 1200;
const dotStaticOpacity = [0.96, 0.72, 0.48, 0.72, 0.48, 0.32, 0.48, 0.32, 0.24];

export const root = style({
  '@layer': {
    recipes: {
      display: 'inline-flex',
      width: 'var(--agent-status-size, 1.5rem)',
      height: 'var(--agent-status-size, 1.5rem)',
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

export const workingIcon = style({
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
        transform: 'scale(0.72)',
        transformBox: 'fill-box',
        transformOrigin: 'center',
        animationName: dotShimmer,
        animationDuration: `${PERIOD_MS}ms`,
        animationTimingFunction: 'cubic-bezier(0.45, 0, 0.2, 1)',
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

export const warningShape = style({
  '@layer': {
    recipes: {
      fill: vars.backgroundWarning,
      stroke: vars.foregroundWarning,
    },
  },
});

export const successShape = style({
  '@layer': {
    recipes: {
      fill: vars.backgroundSuccess,
      stroke: vars.foregroundSuccess,
    },
  },
});

export const errorShape = style({
  '@layer': {
    recipes: {
      fill: vars.backgroundError,
      stroke: vars.foregroundError,
    },
  },
});

export const errorMark = style({
  '@layer': {
    recipes: {
      fill: vars.foregroundError,
      stroke: vars.foregroundError,
      strokeLinecap: 'round',
    },
  },
});
