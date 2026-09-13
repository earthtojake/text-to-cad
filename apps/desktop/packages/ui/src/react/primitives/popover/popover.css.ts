import { style } from '@vanilla-extract/css';
import {
  kfPopupIn,
  kfPopupOut,
  kfPopupInSlideFromTop,
  kfPopupInSlideFromBottom,
  kfPopupInSlideFromLeft,
  kfPopupInSlideFromRight,
} from '@styles/effects/animations.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const positioner = style({
  isolation: 'isolate',
  zIndex: 50,
});

export const popupContent = style({
  zIndex: 50,
  display: 'flex',
  transformOrigin: 'var(--transform-origin)',
  overflow: 'hidden',
  flexDirection: 'column',
  gap: '1rem',
  borderRadius: tokenVars.radiusMd,
  border: `1px solid ${vars.border}`,
  backgroundColor: vars.surface,
  padding: '1rem',
  fontSize: tokenVars.textSm,
  color: vars.foreground,
  boxShadow: vars.shadowSm,
  outline: 'none',
  selectors: {
    '&[data-open]': { animation: `${kfPopupIn} 100ms both` },
    '&[data-open][data-side="bottom"]': { animation: `${kfPopupInSlideFromTop} 100ms both` },
    '&[data-open][data-side="top"]': { animation: `${kfPopupInSlideFromBottom} 100ms both` },
    '&[data-open][data-side="right"]': { animation: `${kfPopupInSlideFromLeft} 100ms both` },
    '&[data-open][data-side="inline-end"]': { animation: `${kfPopupInSlideFromLeft} 100ms both` },
    '&[data-open][data-side="left"]': { animation: `${kfPopupInSlideFromRight} 100ms both` },
    '&[data-open][data-side="inline-start"]': {
      animation: `${kfPopupInSlideFromRight} 100ms both`,
    },
    '&[data-closed]': { animation: `${kfPopupOut} 100ms both` },
  },
});

export const popoverHeader = style({
  display: 'flex',
  flexDirection: 'column',
  gap: '0.25rem',
  fontSize: tokenVars.textSm,
});

export const popoverTitle = style({
  fontWeight: 400,
});

export const popoverDescription = style({
  color: vars.foregroundMuted,
});
