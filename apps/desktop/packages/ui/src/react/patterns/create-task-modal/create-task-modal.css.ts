import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const root = style({
  display: 'flex',
  width: '100%',
  height: '22.5rem',
  minHeight: '18rem',
  flexDirection: 'column',
  gap: tokenVars.space2,
  overflow: 'hidden',
  color: vars.foreground,
});

export const header = style({
  display: 'flex',
  minWidth: 0,
  flexShrink: 0,
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: tokenVars.space2,
});

export const headerEnd = style({
  display: 'flex',
  minWidth: 0,
  alignItems: 'center',
  gap: tokenVars.space1,
});

export const selector = style({
  minWidth: 0,
  maxWidth: '14rem',
});

export const selectorText = style({
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const taskName = style({
  display: 'grid',
  flexShrink: 0,
  gridTemplateColumns: 'auto minmax(0, 1fr)',
  alignItems: 'center',
  gap: tokenVars.space2,
});

export const taskNameLabel = style({
  color: vars.foregroundMuted,
  fontSize: tokenVars.textXs,
  fontWeight: 500,
});

export const taskNameInput = style({
  flex: 1,
  fontWeight: 500,
});

export const taskNameControl = style({
  display: 'flex',
  minWidth: 0,
  alignItems: 'center',
  gap: tokenVars.space2,
});

export const taskNameError = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'center',
  gap: tokenVars.space1,
  color: vars.foregroundDestructive,
  fontSize: tokenVars.textXs,
});

export const footer = style({
  display: 'flex',
  minWidth: 0,
  flexShrink: 0,
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: tokenVars.space2,
});

export const footerStart = style({
  display: 'flex',
  minWidth: 0,
  flex: 1,
  alignItems: 'center',
  gap: tokenVars.space1,
});

export const footerEnd = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'center',
  gap: tokenVars.space1,
});

export const flexibleSelector = style({
  minWidth: '2.25rem',
  maxWidth: '9rem',
});

export const popup = style({
  width: '23rem',
  maxHeight: '19rem',
});

export const workspacePopup = style({
  width: '34rem',
  maxWidth: 'calc(100vw - 2rem)',
  height: '23rem',
  maxHeight: 'calc(100vh - 2rem)',
});

export const popupHeader = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: tokenVars.space2,
  padding: tokenVars.space2,
});

export const popupBody = style({
  minHeight: 0,
  flex: 1,
  overflowY: 'auto',
  padding: tokenVars.space1,
});

export const popupFooter = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: tokenVars.space1,
});

export const comboboxHeader = style({
  padding: tokenVars.space2,
  color: vars.foreground,
  fontSize: tokenVars.textSm,
  fontWeight: 600,
});

export const comboboxFooter = style({
  display: 'flex',
  padding: tokenVars.space1,
});

export const search = style({
  margin: tokenVars.space1,
});

export const itemContent = style({
  display: 'flex',
  minWidth: 0,
  flex: 1,
  flexDirection: 'column',
});

export const itemLabel = style({
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const itemDescription = style({
  minWidth: 0,
  overflow: 'hidden',
  color: vars.foregroundMuted,
  fontSize: tokenVars.textXs,
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const state = style({
  display: 'grid',
  minHeight: '6rem',
  placeItems: 'center',
  gap: tokenVars.space2,
  padding: tokenVars.space4,
  color: vars.foregroundMuted,
  fontSize: tokenVars.textSm,
  textAlign: 'center',
});

export const retry = style({
  marginInline: 'auto',
});

export const workspaceBody = style({
  display: 'grid',
  minHeight: 0,
  flex: 1,
  gridTemplateColumns: '10.5rem minmax(0, 1fr)',
  overflow: 'hidden',
});

export const presetRail = style({
  width: '100%',
  minHeight: 0,
  overflowY: 'auto',
  padding: tokenVars.space1,
});

export const preset = style({
  width: '100%',
});

export const presetLabel = style({
  width: '100%',
  textAlign: 'start',
});

export const detail = style({
  minHeight: 0,
  overflowY: 'auto',
  padding: tokenVars.space3,
});

export const detailStack = style({
  display: 'flex',
  flexDirection: 'column',
  gap: tokenVars.space3,
});

export const field = style({
  display: 'flex',
  flexDirection: 'column',
  gap: tokenVars.space1,
});

export const fieldLabel = style({
  color: vars.foregroundMuted,
  fontSize: tokenVars.textXs,
});

export const inline = style({
  display: 'flex',
  alignItems: 'center',
  gap: tokenVars.space2,
});

export const notice = style({
  borderRadius: tokenVars.radiusSm,
  backgroundColor: vars.surfaceHover,
  padding: tokenVars.space2,
  color: vars.foregroundMuted,
  fontSize: tokenVars.textXs,
});

export const error = style({
  color: vars.surfaceDestructiveForeground,
});

export const destination = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'center',
  gap: tokenVars.space2,
  padding: tokenVars.space2,
  backgroundColor: vars.surfaceHover,
  color: vars.foregroundMuted,
  fontSize: tokenVars.textXs,
});

export const destinationStatus = style({
  marginInlineStart: 'auto',
});

export const setupList = style({
  margin: 0,
  paddingInlineStart: tokenVars.space4,
  color: vars.foregroundMuted,
  fontSize: tokenVars.textXs,
});

export const radioDock = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'center',
  gap: '1px',
});

export const visuallyHidden = style({
  position: 'absolute',
  width: 1,
  height: 1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  clipPath: 'inset(50%)',
  whiteSpace: 'nowrap',
});
