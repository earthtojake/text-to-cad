import '@styles/layers.css';
import { style } from '@vanilla-extract/css';

export const root = style({
  '@layer': {
    recipes: {
      display: 'flex',
      width: '100%',
      minWidth: 0,
      alignItems: 'center',
      gap: '0.75rem',
    },
  },
});

export const icon = style({
  '@layer': {
    recipes: {
      display: 'flex',
      flexShrink: 0,
      alignItems: 'center',
      justifyContent: 'center',
    },
  },
});

export const title = style({
  '@layer': {
    recipes: {
      display: 'flex',
      minWidth: 0,
      flex: '1 1 auto',
      alignItems: 'center',
      overflow: 'hidden',
    },
  },
});

export const actions = style({
  '@layer': {
    recipes: {
      display: 'flex',
      minWidth: 0,
      flexShrink: 0,
      alignItems: 'center',
      gap: '0.5rem',
      marginLeft: 'auto',
    },
  },
});
