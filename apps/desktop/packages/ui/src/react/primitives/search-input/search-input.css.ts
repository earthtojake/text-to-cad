import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

/** Wrapper that provides the positioning context for the icon. */
export const container = style({
  position: 'relative',
  display: 'flex',
  minWidth: 0,
  alignItems: 'center',
  width: '100%',
});

/** Search icon pinned to the left, non-interactive. */
export const icon = style({
  pointerEvents: 'none',
  position: 'absolute',
  left: '0.625rem',
  flexShrink: 0,
  color: vars.foregroundMuted,
});
globalStyle(`${icon} svg:not([class*='size-'])`, { width: '0.875rem', height: '0.875rem' });

/** Optional shortcut/help content pinned to the trailing edge and vertically centered. */
export const shortcut = style({
  pointerEvents: 'none',
  position: 'absolute',
  right: '0.5rem',
  top: '50%',
  transform: 'translateY(-50%)',
  display: 'inline-flex',
  alignItems: 'center',
  gap: tokenVars.space0_5,
  color: vars.foregroundMuted,
});

/** Hide the shortcut hint once the user has typed so it behaves as a placeholder adornment. */
globalStyle(`${container}:has(input:not(:placeholder-shown)) .${shortcut}`, {
  display: 'none',
});

/** Clear button pinned to the right. */
export const clearButton = style({
  pointerEvents: 'auto',
  position: 'absolute',
  right: '0.375rem',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '1.25rem',
  height: '1.25rem',
  borderRadius: tokenVars.radiusSm,
  border: 'none',
  backgroundColor: 'transparent',
  color: vars.foregroundMuted,
  cursor: 'pointer',
  transition: 'color 150ms, background-color 150ms',
  selectors: {
    '&:hover': { backgroundColor: vars.surfaceHover, color: vars.foreground },
    '&:focus-visible': {
      outline: 'none',
      boxShadow: `0 0 0 2px ${vars.borderPrimary}`,
    },
  },
});
globalStyle(`${clearButton} svg`, { pointerEvents: 'none', width: '0.75rem', height: '0.75rem' });

/** Suppress the browser-native clear button on search inputs; the component renders its own. */
globalStyle('input[type="search"]::-webkit-search-cancel-button', {
  display: 'none',
});
