import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

// ── FilterPill ────────────────────────────────────────────────────────────────

/** The pill chip for an active filter value. */
export const pill = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '0.25rem',
  borderRadius: tokenVars.radiusFull,
  border: `1px solid ${vars.border}`,
  backgroundColor: vars.surfaceHover,
  paddingLeft: '0.5rem',
  paddingRight: '0.25rem',
  paddingTop: '0.125rem',
  paddingBottom: '0.125rem',
  fontSize: tokenVars.textXs,
  color: vars.foreground,
  whiteSpace: 'nowrap',
});

export const pillAvatar = style({
  width: '0.875rem',
  height: '0.875rem',
  borderRadius: '999px',
  flexShrink: 0,
  objectFit: 'cover',
});

export const pillSwatch = style({
  width: '0.5rem',
  height: '0.5rem',
  borderRadius: '999px',
  flexShrink: 0,
});

export const pillRemove = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '1rem',
  height: '1rem',
  borderRadius: '999px',
  border: 'none',
  backgroundColor: 'transparent',
  color: vars.foregroundMuted,
  cursor: 'pointer',
  transition: 'color 150ms',
  selectors: {
    '&:hover': { color: vars.foreground },
  },
});
globalStyle(`${pillRemove} svg`, { pointerEvents: 'none', width: '0.625rem', height: '0.625rem' });

// ── FilterButton ──────────────────────────────────────────────────────────────

/** Ghost popover-trigger button used in the toolbar filter bar. */
export const filterButton = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '0.25rem',
  border: 'none',
  backgroundColor: 'transparent',
  padding: 0,
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
  cursor: 'pointer',
  transition: 'color 150ms',
  selectors: {
    '&:hover': { color: vars.foreground },
    '&[data-active="true"]': { color: vars.foreground, fontWeight: 400 },
    '&:disabled': { pointerEvents: 'none', opacity: 0.4, cursor: 'not-allowed' },
  },
});
globalStyle(`${filterButton} svg`, {
  pointerEvents: 'none',
  width: '0.875rem',
  height: '0.875rem',
  flexShrink: 0,
});
