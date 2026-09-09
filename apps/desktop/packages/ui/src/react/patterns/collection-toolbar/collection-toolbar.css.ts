import { style } from '@vanilla-extract/css';
import { tokenVars } from '@theme/tokens.css';

export const root = style({
  '@layer': {
    recipes: {
      display: 'grid',
      width: '100%',
      minWidth: 0,
      gridTemplateColumns: 'minmax(0, 1fr) auto',
      alignItems: 'center',
      gap: tokenVars.space2,
    },
  },
});

export const trailing = style({
  '@layer': {
    recipes: {
      display: 'flex',
      minWidth: 0,
      alignItems: 'center',
      justifyContent: 'flex-end',
      gap: tokenVars.space2,
    },
  },
});

export const metadata = style({
  '@layer': {
    recipes: {
      display: 'flex',
      minWidth: 0,
      alignItems: 'center',
      justifyContent: 'flex-end',
      flexWrap: 'wrap',
      gap: tokenVars.space2,
    },
  },
});

export const actions = style({
  '@layer': {
    recipes: {
      display: 'flex',
      flexShrink: 0,
      alignItems: 'center',
      gap: tokenVars.space2,
    },
  },
});
