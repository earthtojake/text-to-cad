import '@styles/layers.css';
import { style, styleVariants } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const root = style({
  '@layer': {
    recipes: {
      display: 'flex',
      width: '100%',
      height: '100%',
      minHeight: 0,
      flexDirection: 'column',
      overflow: 'hidden',
      borderRadius: tokenVars.radiusLg,
      backgroundColor: vars.surface,
    },
  },
});

/** Default loading slot: centered spinner. */
export const loading = style({
  '@layer': {
    recipes: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      padding: '2rem',
    },
  },
});

export const rowGrid = style({
  '@layer': {
    recipes: {
      display: 'grid',
      width: '100%',
      gridTemplateColumns: 'var(--collection-view-template)',
      alignItems: 'center',
      columnGap: tokenVars.space3,
      paddingInline: '0.75rem',
    },
  },
});

const bodyCellBase = style({
  '@layer': {
    recipes: {
      minWidth: 0,
      selectors: {
        "&[data-align='start']": {
          alignSelf: 'start',
        },
        "&[data-align='end']": {
          alignSelf: 'end',
        },
      },
    },
  },
});

export const bodyCell = styleVariants({
  default: [bodyCellBase, { '@layer': { recipes: { paddingBlock: '0.75rem' } } }],
  compact: [bodyCellBase, { '@layer': { recipes: { paddingBlock: '0.375rem' } } }],
});

const freeformBase = style({
  '@layer': {
    recipes: {
      display: 'flex',
      width: '100%',
      minWidth: 0,
      alignItems: 'center',
      gap: tokenVars.space3,
      paddingInline: '0.75rem',
    },
  },
});

export const freeform = styleVariants({
  default: [freeformBase, { '@layer': { recipes: { paddingBlock: '0.75rem' } } }],
  compact: [freeformBase, { '@layer': { recipes: { paddingBlock: '0.375rem' } } }],
});

export const cell = style({
  '@layer': {
    recipes: {
      display: 'flex',
      minWidth: 0,
      flexDirection: 'column',
      gap: '0.125rem',
    },
  },
});

export const cellPrimary = style({
  '@layer': {
    recipes: {
      overflow: 'hidden',
      fontSize: tokenVars.textSm,
      lineHeight: tokenVars.textSmLineHeight,
      color: vars.foreground,
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
    },
  },
});

export const cellSecondary = style({
  '@layer': {
    recipes: {
      overflow: 'hidden',
      fontSize: tokenVars.textXs,
      lineHeight: tokenVars.textXsLineHeight,
      color: vars.foregroundMuted,
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
    },
  },
});
