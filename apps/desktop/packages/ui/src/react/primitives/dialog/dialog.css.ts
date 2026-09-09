import { globalStyle, style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import { kfFadeIn, kfFadeOut, kfPopupIn, kfPopupOut } from '@styles/effects/animations.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const overlay = style({
  position: 'fixed',
  inset: 0,
  zIndex: 50,
  backgroundColor: 'rgba(0,0,0,0.4)',
  selectors: {
    '&[data-open]': { animation: `${kfFadeIn} 100ms both` },
    '&[data-closed]': { animation: `${kfFadeOut} 100ms both` },
  },
});

/** Full-viewport grid that centers the popup without using transform on the popup itself. */
export const positioner = style({
  position: 'fixed',
  inset: 0,
  zIndex: 50,
  display: 'grid',
  placeItems: 'center',
  padding: '1rem',
  pointerEvents: 'none',
});

export const content = recipe({
  base: {
    pointerEvents: 'auto',
    zIndex: 50,
    display: 'flex',
    maxHeight: '100%',
    width: '100%',
    maxWidth: '100%',
    flexDirection: 'column',
    overflow: 'hidden',
    borderRadius: tokenVars.radiusXl,
    backgroundColor: vars.surface,
    fontSize: tokenVars.textSm,
    color: vars.foreground,
    boxShadow: `${vars.shadowOverlay}, 0 0 0 1px color-mix(in srgb, ${vars.foreground} 10%, transparent)`,
    outline: 'none',
    selectors: {
      '&[data-open]': { animation: `${kfPopupIn} 100ms both` },
      '&[data-closed]': { animation: `${kfPopupOut} 100ms both` },
    },
  },
  variants: {
    size: {
      xs: { '@media': { 'screen and (min-width: 640px)': { maxWidth: '20rem' } } },
      sm: { '@media': { 'screen and (min-width: 640px)': { maxWidth: '24rem' } } },
      md: { '@media': { 'screen and (min-width: 640px)': { maxWidth: '32rem' } } },
      lg: { '@media': { 'screen and (min-width: 640px)': { maxWidth: '42rem' } } },
      xl: { '@media': { 'screen and (min-width: 640px)': { maxWidth: '80vw', height: '80vh' } } },
      // Near-fullscreen: fills the positioner (viewport minus its 1rem padding).
      full: { height: '100%' },
    },
  },
  defaultVariants: { size: 'md' },
});

export const header = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: '0.5rem',
  padding: '1rem',
});

export const headerInner = style({
  display: 'flex',
  minWidth: 0,
  flexDirection: 'column',
  gap: '0.25rem',
});

export const footer = style({
  display: 'flex',
  flexShrink: 0,
  flexDirection: 'column-reverse',
  gap: '0.5rem',
  borderTop: `1px solid ${vars.border}`,
  padding: '0.75rem',
  backgroundColor: vars.surfaceEmphasis,
  '@media': {
    '(min-width: 640px)': {
      flexDirection: 'row',
      justifyContent: 'flex-end',
    },
  },
});

export const title = style({
  fontSize: tokenVars.textSm,
  fontWeight: 500,
  color: vars.foreground,
});

export const description = style({
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
});
globalStyle(`${description} a`, {
  textDecoration: 'underline',
  textUnderlineOffset: '3px',
});
globalStyle(`${description} a:hover`, {
  color: vars.foreground,
});

export const body = style({
  display: 'flex',
  width: '100%',
  flexDirection: 'column',
  gap: '0.5rem',
  padding: '1rem',
  paddingTop: 0,
  outline: 'none',
  selectors: {
    '&:focus-visible': { outline: 'none' },
  },
});

export const closeButtonOverride = style({
  marginTop: '-0.25rem',
  marginRight: '-0.25rem',
  flexShrink: 0,
  color: vars.foregroundMuted,
  selectors: {
    '&:hover': { color: vars.foreground },
  },
});
