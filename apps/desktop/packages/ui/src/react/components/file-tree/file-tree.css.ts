import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';
export {
  chevron,
  label,
  name,
  row,
  secondary,
  spinner,
  state,
  stateError,
  treeViewport,
} from '../tree-rows';

export const root = style({
  display: 'flex',
  // The virtualized viewport can only scroll when the component is height-bounded,
  // so it fills whatever container the consumer provides instead of growing to content.
  height: '100%',
  minHeight: 0,
  minWidth: 0,
  flexDirection: 'column',
  overflow: 'hidden',
  backgroundColor: vars.surfaceBase,
  color: vars.foreground,
});

export const header = style({
  display: 'flex',
  minWidth: 0,
  alignItems: 'center',
  gap: '0.5rem',
  borderBottom: `1px solid ${vars.border}`,
  padding: '0.5rem',
});

export const headerTarget = style({
  minWidth: 0,
  flex: '1 1 auto',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  fontSize: tokenVars.textXs,
  color: vars.foregroundMuted,
});

export const headerActions = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'center',
  gap: '0.25rem',
});

export const body = style({
  position: 'relative',
  minHeight: 0,
  flex: '1 1 auto',
});

export const rowWrapper = style({
  height: '100%',
});

export const indentGuide = style({
  position: 'absolute',
  top: '-1px',
  width: '1px',
  height: 'calc(100% + 2px)',
  backgroundColor: vars.borderSubtle,
  opacity: 0,
  pointerEvents: 'none',
  transition: 'opacity 100ms ease',
  selectors: {
    [`${root}:hover &`]: {
      opacity: 1,
    },
  },
});

export const spacer = style({
  width: '14px',
  height: '14px',
  flexShrink: 0,
});

export const icon = style({
  display: 'inline-flex',
  width: '14px',
  height: '14px',
  flexShrink: 0,
  alignItems: 'center',
  justifyContent: 'center',
  color: vars.foregroundMuted,
});

export const fileIcon = style({
  width: '12px',
  height: '12px',
});

export const devicon = style({
  display: 'inline-block',
  width: '12px',
  height: '12px',
  flexShrink: 0,
  fontSize: '12px',
  lineHeight: '12px',
});

export const decoration = style({
  display: 'flex',
  minWidth: 0,
  flexShrink: 0,
  alignItems: 'center',
  gap: '0.375rem',
});

export const muted = style({
  color: vars.foregroundMuted,
});

export const strikethrough = style({
  textDecoration: 'line-through',
});

export const draftRow = style({
  backgroundColor: vars.background2,
});

export const draftInput = style({
  minWidth: 0,
  width: '100%',
  border: 0,
  background: 'transparent',
  padding: 0,
  color: vars.foreground,
  font: 'inherit',
  fontSize: '13px',
  outline: 'none',
  selectors: {
    '&::placeholder': {
      color: vars.foregroundPassive,
    },
  },
});

export const rootDropTarget = style({
  position: 'absolute',
  right: '0.5rem',
  bottom: '0.5rem',
  left: '0.5rem',
  height: '2px',
  borderRadius: '999px',
  backgroundColor: vars.selection,
  pointerEvents: 'none',
});
