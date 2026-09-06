import { style } from '@vanilla-extract/css';
// Side-effect import so the @layer order declaration is emitted before these
// rules; otherwise `recipes` gets registered first and loses to app layers.
import '@styles/layers.css';

export const grid = style({
  '@layer': {
    recipes: {
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 16rem), 1fr))',
      gap: '0.75rem',
    },
  },
});

export const section = style({
  '@layer': {
    recipes: {
      display: 'flex',
      flexDirection: 'column',
      gap: '0.5rem',
    },
  },
});

export const item = style({
  '@layer': {
    recipes: {
      display: 'flex',
      alignItems: 'center',
      gap: '0.75rem',
      width: '100%',
      textAlign: 'left',
    },
  },
});
