import { keyframes, style, styleVariants } from '@vanilla-extract/css';

const spin = keyframes({
  from: { transform: 'rotate(0deg)' },
  to: { transform: 'rotate(360deg)' },
});

export const spinner = style({
  animationName: spin,
  animationDuration: '1s',
  animationTimingFunction: 'linear',
  animationIterationCount: 'infinite',
  flexShrink: 0,
});

export const size = styleVariants({
  sm: { width: '1rem', height: '1rem' },
  md: { width: '1.25rem', height: '1.25rem' },
  lg: { width: '1.5rem', height: '1.5rem' },
});

export const track = style({ opacity: 0.25 });

export const arc = style({ opacity: 0.75 });
