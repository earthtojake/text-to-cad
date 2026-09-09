import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const layout = style({
  appearance: 'none',
  display: 'flex',
  width: '100%',
  height: '2rem',
  minWidth: 0,
  alignItems: 'center',
  gap: '0.5rem',
  margin: 0,
  paddingTop: 0,
  paddingRight: '0.25rem',
  paddingBottom: 0,
  paddingLeft: '0.625rem',
  font: 'inherit',
  fontSize: tokenVars.textSm,
  textAlign: 'left',
  cursor: 'pointer',
});

export const layoutSm = style({
  height: '1.5rem',
  paddingLeft: '0.5rem',
  fontSize: tokenVars.textXs,
});

export const icon = style({
  pointerEvents: 'none',
  flexShrink: 0,
  color: vars.foregroundMuted,
});
globalStyle(`${icon}:not([class*='size-'])`, { width: '1rem', height: '1rem' });

export const value = style({
  minWidth: 0,
  width: '100%',
  flex: 1,
  overflow: 'hidden',
  color: vars.foreground,
  whiteSpace: 'nowrap',
  textOverflow: 'ellipsis',
});

export const placeholder = style({
  color: vars.foregroundPassive,
});

export const chooseAffordance = style({
  pointerEvents: 'none',
});
