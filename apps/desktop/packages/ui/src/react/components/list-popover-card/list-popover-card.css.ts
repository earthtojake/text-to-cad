import { style } from '@vanilla-extract/css';
import { tokenVars } from '@theme/tokens.css';
// Side-effect import so the @layer order declaration is emitted before these
// rules; otherwise `recipes` gets registered first and loses to app layers.
import '@styles/layers.css';

/**
 * Anchors the card just above the bottom edge of the nearest positioned
 * ancestor (the list container), inset from both sides.
 */
export const positioner = style({
  '@layer': {
    recipes: {
      position: 'absolute',
      right: '1.5rem',
      bottom: '1rem',
      left: '1.5rem',
    },
  },
});

export const inner = style({
  '@layer': {
    recipes: {
      display: 'flex',
      alignItems: 'center',
      gap: '0.5rem',
      fontSize: tokenVars.textSm,
    },
  },
});
