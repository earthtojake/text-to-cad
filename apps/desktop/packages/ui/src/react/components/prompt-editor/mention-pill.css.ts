import { keyframes, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const pillWrapper = style({
  display: 'inline-block',
  verticalAlign: 'baseline',
});

export const pill = style({
  position: 'relative',
  display: 'inline-flex',
  cursor: 'default',
  userSelect: 'none',
  alignItems: 'center',
  gap: '0.25rem',
  borderRadius: tokenVars.radiusSm,
  backgroundColor: vars.surfaceHover,
  paddingLeft: '0.25rem',
  paddingRight: '0.25rem',
  paddingTop: '0.125rem',
  paddingBottom: '0.125rem',
  fontSize: tokenVars.textXs,
  fontWeight: 400,
  color: vars.foreground,
  boxShadow: `0 0 0 1px color-mix(in srgb, ${vars.foreground} 10%, transparent)`,
  verticalAlign: 'baseline',
});

const pendingPulse = keyframes({
  '0%, 100%': { opacity: 1 },
  '50%': { opacity: 0.55 },
});

export const pillPending = style({
  animation: `${pendingPulse} 1.4s ease-in-out infinite`,
  '@media': {
    '(prefers-reduced-motion: reduce)': {
      animation: 'none',
    },
  },
});

export const pillIconArea = style({
  position: 'relative',
  display: 'flex',
  width: '0.875rem',
  height: '0.875rem',
  flexShrink: 0,
  alignItems: 'center',
  justifyContent: 'center',
});

export const pillRemoveBtn = style({
  position: 'absolute',
  inset: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: tokenVars.radiusSm,
  backgroundColor: vars.surfaceHover,
  opacity: 0,
  transition: 'opacity 150ms',
  selectors: {
    [`${pill}:hover &`]: { opacity: 1 },
    '&:hover': { backgroundColor: vars.surfaceSelected },
  },
});

export const pillName = style({
  maxWidth: '200px',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});
