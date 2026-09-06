import { keyframes, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const root = style({
  display: 'flex',
  flexDirection: 'column',
  width: '100%',
  flex: 1,
  minHeight: 0,
  gap: '0.5rem',
  color: vars.foreground,
});

export const label = style({
  fontSize: tokenVars.textXs,
  fontWeight: 400,
  color: vars.foregroundMuted,
});

export const progressHeader = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  fontSize: tokenVars.textSm,
  fontWeight: 400,
  color: vars.foregroundMuted,
});

export const progressContainer = style({
  display: 'flex',
  flexDirection: 'column',
  gap: '0.5rem',
  border: `1px solid ${vars.border}`,
  borderRadius: tokenVars.radiusLg,
  padding: '1rem',
});

export const stepViewport = style({
  minHeight: '1.75rem',
  display: 'flex',
  marginTop: '30%',
  alignItems: 'center',
  overflow: 'hidden',
});

export const stepRow = style({
  display: 'grid',
  gridTemplateColumns: '1.25rem minmax(0, 1fr)',
  alignItems: 'center',
  gap: '0.5rem',
  minWidth: 0,
});

export const iconSlot = style({
  display: 'inline-flex',
  width: '1.25rem',
  height: '1.25rem',
  alignItems: 'center',
  justifyContent: 'center',
});

export const iconPending = style({
  color: vars.foregroundPassive,
});

export const iconLoading = style({
  color: vars.foregroundMuted,
});

export const iconError = style({
  color: vars.foregroundError,
});

export const stepName = style({
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  fontSize: tokenVars.textLg,
  fontWeight: 400,
  color: vars.foreground,
});

export const stepChildren = style({});

export const footer = style({
  // Pushes the footer to the bottom of the container when extra vertical space
  // is available (auto margin absorbs the free space), so it visibly floats to
  // the bottom. In an auto-height container it collapses to the normal gap.
  marginTop: 'auto',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '1rem',
  borderRadius: tokenVars.radiusLg,
  border: `1px solid ${vars.border}`,
  backgroundColor: vars.background1,
  padding: '0.375rem 0.375rem 0.375rem 0.75rem',
});

export const footerProgress = style({
  fontFamily: tokenVars.fontMono,
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
  whiteSpace: 'nowrap',
});

export const footerActions = style({
  display: 'flex',
  alignItems: 'center',
  gap: '0.25rem',
});

const stepExitUpKeyframes = keyframes({
  from: {
    opacity: 1,
    transform: 'translateY(0)',
  },
  to: {
    opacity: 0,
    transform: 'translateY(-8px)',
  },
});

const stepEnterFromBottomKeyframes = keyframes({
  from: {
    opacity: 0,
    transform: 'translateY(8px)',
  },
  to: {
    opacity: 1,
    transform: 'translateY(0)',
  },
});

export const stepExit = style({
  animationName: stepExitUpKeyframes,
  animationDuration: '220ms',
  animationTimingFunction: 'ease-in',
  animationFillMode: 'forwards',
  '@media': {
    '(prefers-reduced-motion: reduce)': {
      animationDuration: '1ms',
      transform: 'none',
    },
  },
});

export const stepEnter = style({
  animationName: stepEnterFromBottomKeyframes,
  animationDuration: '180ms',
  animationTimingFunction: 'ease-out',
  animationFillMode: 'both',
  '@media': {
    '(prefers-reduced-motion: reduce)': {
      animationDuration: '1ms',
      transform: 'none',
    },
  },
});

export const progressTrack = style({
  height: '0.375rem',
  width: '100%',
  overflow: 'hidden',
  borderRadius: '999px',
  backgroundColor: vars.background2,
});

export const progressFill = style({
  height: '100%',
  borderRadius: '999px',
  backgroundColor: vars.foreground,
  transition: 'width 300ms ease-out',
});
