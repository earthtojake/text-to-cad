import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';
// Side-effect import so the @layer order declaration is emitted before these
// rules; otherwise `recipes` gets registered first and loses to app layers.
import '@styles/layers.css';

export const root = style({
  '@layer': {
    recipes: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      minHeight: 0,
      width: '100%',
      padding: '2rem',
      backgroundColor: vars.background,
    },
  },
});

export const bare = style({
  '@layer': {
    recipes: {
      backgroundColor: 'transparent',
    },
  },
});

export const content = style({
  '@layer': {
    recipes: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      textAlign: 'center',
      maxWidth: '20rem',
    },
  },
});

export const label = style({
  '@layer': {
    recipes: {
      margin: 0,
      fontFamily: tokenVars.fontSans,
      fontSize: tokenVars.textSm,
      fontWeight: 500,
      color: vars.foregroundMuted,
    },
  },
});

export const description = style({
  '@layer': {
    recipes: {
      margin: 0,
      marginTop: '0.375rem',
      fontSize: tokenVars.textXs,
      lineHeight: 1.625,
      fontWeight: 400,
      color: vars.foregroundPassive,
    },
  },
});

export const action = style({
  '@layer': {
    recipes: {
      marginTop: '1.25rem',
    },
  },
});
