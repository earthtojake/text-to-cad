import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const diagramContainer = style({
  minHeight: 0,
  flex: 1,
  overflow: 'auto',
  padding: '1rem',
  paddingTop: 0,
});

export const diagram = style({
  minWidth: 0,
});

globalStyle(`${diagram} svg`, {
  display: 'block',
  maxWidth: '100%',
  height: 'auto',
  margin: '0 auto',
});

export const unavailable = style({
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
});
