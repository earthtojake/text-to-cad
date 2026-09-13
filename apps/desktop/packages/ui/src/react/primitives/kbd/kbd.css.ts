import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const kbd = style({
  pointerEvents: 'none',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexShrink: 0,
  minWidth: '1.15rem',
  height: '1.15rem',
  width: '1rem',
  borderRadius: tokenVars.radiusSm,
  border: `1px solid var(--kbd-border, ${vars.borderSubtle})`,
  backgroundColor: `var(--kbd-bg, ${vars.backgroundSecondary})`,
  color: `var(--kbd-color, ${vars.foregroundMuted})`,
  fontFamily: tokenVars.fontSans,
  fontSize: '10px',
  fontWeight: 400,
  lineHeight: 1,
  userSelect: 'none',
});

globalStyle(`${kbd} svg:not([class*='size-'])`, {
  width: '0.75rem',
  height: '0.75rem',
});

export const kbdGroup = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '0.1rem',
});
