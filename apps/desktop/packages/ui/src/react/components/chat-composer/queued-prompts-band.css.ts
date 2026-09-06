import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const band = style({
  position: 'relative',
  display: 'flex',
  flexDirection: 'column',
  gap: '0.375rem',
  borderRadius: `${tokenVars.radiusXl} ${tokenVars.radiusXl} 0 0`,
  border: `1px solid ${vars.border}`,
  borderBottomWidth: 0,
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  paddingTop: '0.5rem',
  paddingBottom: '0.5rem',
  backgroundColor: vars.surface,
  color: vars.foreground,
  fontSize: tokenVars.textXs,
});

export const bandConnectedBelow = style({
  selectors: {
    '&::after': {
      content: '',
      position: 'absolute',
      left: '-1px',
      right: '-1px',
      bottom: `calc(-1 * ${tokenVars.radiusXl})`,
      height: tokenVars.radiusXl,
      borderLeft: `1px solid ${vars.border}`,
      borderRight: `1px solid ${vars.border}`,
      pointerEvents: 'none',
    },
  },
});

export const header = style({
  display: 'flex',
  alignItems: 'center',
  gap: '0.375rem',
  paddingLeft: '0.25rem',
  paddingRight: '0.25rem',
  color: vars.foregroundMuted,
  lineHeight: 1.375,
});

export const headerIcon = style({
  width: '0.875rem',
  height: '0.875rem',
  flexShrink: 0,
});

export const headerStrong = style({
  fontWeight: 400,
  color: vars.foreground,
});

export const list = style({
  display: 'flex',
  flexDirection: 'column',
  gap: '0.25rem',
});

export const row = style({
  display: 'grid',
  position: 'relative',
  gridTemplateColumns: 'auto minmax(0, 1fr)',
  alignItems: 'center',
  gap: '0.5rem',
  minHeight: '1.875rem',
  borderRadius: tokenVars.radiusMd,
  paddingLeft: '0.25rem',
  paddingRight: '0.25rem',
  outline: 'none',
  cursor: 'text',
  selectors: {
    '&:hover': { backgroundColor: vars.surfaceHover },
    '&:focus-within': { backgroundColor: vars.surfaceHover },
    '&:focus-visible': {
      boxShadow: `0 0 0 1px ${vars.border1}`,
    },
    '&[data-dragging]': {
      opacity: 0.56,
    },
    '&[data-drag-over]': {
      backgroundColor: vars.surfaceSelected,
    },
  },
});

export const indexSlot = style({
  position: 'relative',
  width: '1rem',
  height: '1rem',
  flexShrink: 0,
});

export const indexNumber = style({
  position: 'absolute',
  inset: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: vars.foregroundMuted,
  fontVariantNumeric: 'tabular-nums',
  transition: 'opacity 120ms',
  selectors: {
    [`${row}:hover &`]: { opacity: 0 },
    [`${row}:focus-within &`]: { opacity: 0 },
    [`${row}[data-dragging] &`]: { opacity: 0 },
  },
});

export const dragHandle = style({
  position: 'absolute',
  inset: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  border: 0,
  borderRadius: tokenVars.radiusSm,
  backgroundColor: 'transparent',
  padding: 0,
  color: vars.foregroundMuted,
  cursor: 'grab',
  opacity: 0,
  outline: 'none',
  transition: 'opacity 120ms, color 120ms, background-color 120ms',
  selectors: {
    [`${row}:hover &`]: { opacity: 1 },
    [`${row}:focus-within &`]: { opacity: 1 },
    [`${row}[data-dragging] &`]: { opacity: 1, cursor: 'grabbing' },
    '&:hover': {
      backgroundColor: vars.surfaceSelected,
      color: vars.foreground,
    },
    '&:focus-visible': {
      opacity: 1,
      boxShadow: `0 0 0 1px ${vars.border1}`,
    },
  },
});

export const dragHandleIcon = style({
  width: '0.875rem',
  height: '0.875rem',
});

export const promptText = style({
  minWidth: 0,
  border: 0,
  backgroundColor: 'transparent',
  padding: 0,
  color: 'inherit',
  font: 'inherit',
  textAlign: 'left',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  lineHeight: 1.375,
  outline: 'none',
  cursor: 'text',
  selectors: {
    '&:focus-visible': {
      textDecoration: 'underline',
      textUnderlineOffset: '2px',
    },
  },
});

export const emptyText = style({
  color: vars.foregroundMuted,
  fontStyle: 'italic',
});

export const actions = style({
  position: 'absolute',
  right: '0.125rem',
  top: '50%',
  transform: 'translateY(-50%)',
  display: 'flex',
  alignItems: 'center',
  gap: '0.125rem',
  paddingLeft: '0.75rem',
  backgroundColor: vars.surfaceHover,
  opacity: 0,
  pointerEvents: 'none',
  transition: 'opacity 120ms',
  selectors: {
    [`${row}:hover &`]: { opacity: 1, pointerEvents: 'auto' },
    [`${row}:focus-within &`]: { opacity: 1, pointerEvents: 'auto' },
  },
});

export const editArea = style({
  display: 'flex',
  alignItems: 'center',
  gap: '0.375rem',
  minWidth: 0,
});

export const editInput = style({
  flex: 1,
  minWidth: 0,
  resize: 'vertical',
  maxHeight: '7rem',
  border: `1px solid ${vars.border}`,
  borderRadius: tokenVars.radiusMd,
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  paddingTop: '0.375rem',
  paddingBottom: '0.375rem',
  backgroundColor: vars.surfaceBaseEmphasis,
  color: vars.foreground,
  font: 'inherit',
  lineHeight: 1.375,
  outline: 'none',
  selectors: {
    '&:focus': {
      borderColor: vars.border1,
      boxShadow: `0 0 0 1px ${vars.border1}`,
    },
  },
});
