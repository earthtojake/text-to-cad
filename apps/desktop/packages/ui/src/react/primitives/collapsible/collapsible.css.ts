import { globalStyle, style } from '@vanilla-extract/css';
import { controlVariants } from '@styles/recipes/control.css';
import { vars } from '@theme/core/contract/contract.css';

/**
 * Full-width trigger button: ghost control + space-between so the chevron
 * always pins to the trailing edge.
 */
export const trigger = style([
  controlVariants({ variant: 'ghost' }),
  {
    width: '100%',
    justifyContent: 'space-between',
    gap: '0.5rem',
    paddingLeft: '0.5rem',
    paddingRight: '0.5rem',
    fontWeight: 400,
    color: vars.foreground,
    selectors: {
      '&:hover': { color: vars.foreground },
    },
  },
]);

globalStyle(`${trigger} svg`, { pointerEvents: 'none', flexShrink: 0 });

/** Chevron rotates 180° when the panel is open. */
export const chevron = style({
  transition: 'transform 200ms ease',
  selectors: {
    '[data-panel-open] &': { transform: 'rotate(180deg)' },
  },
});

/**
 * Animated panel: height transitions from 0 → --collapsible-panel-height
 * using base-ui's CSS variable. data-starting-style / data-ending-style
 * mark the from/to keyframes so enter and exit animations are symmetric.
 */
export const panel = style({
  height: 'var(--collapsible-panel-height)',
  overflow: 'hidden',
  transition: 'height 200ms ease, opacity 150ms ease',
  selectors: {
    '&[data-starting-style]': { height: 0, opacity: 0 },
    '&[data-ending-style]': { height: 0, opacity: 0 },
  },
});
