import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const root = style({
  minWidth: 0,
});

export const list = style({
  display: 'flex',
  minWidth: 0,
  alignItems: 'center',
  margin: 0,
  padding: 0,
  listStyle: 'none',
});

export const item = style({
  display: 'flex',
  minWidth: 0,
  alignItems: 'center',
});

export const separator = style({
  width: '0.75rem',
  height: '0.75rem',
  marginInline: '0.375rem',
  flexShrink: 0,
  color: vars.foregroundPassive,
});

export const label = style({
  overflow: 'hidden',
  color: vars.foregroundMuted,
  fontSize: tokenVars.textSm,
  lineHeight: 1.25,
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const current = style([
  label,
  {
    color: vars.foreground,
  },
]);

export const link = style({
  overflow: 'hidden',
  border: 0,
  borderRadius: tokenVars.radiusSm,
  padding: 0,
  background: 'transparent',
  color: vars.foregroundMuted,
  cursor: 'pointer',
  font: 'inherit',
  fontSize: tokenVars.textSm,
  lineHeight: 1.25,
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  selectors: {
    '&:hover': {
      color: vars.foreground,
    },
    '&:focus-visible': {
      outline: `2px solid ${vars.borderPrimary}`,
      outlineOffset: '2px',
    },
  },
});
