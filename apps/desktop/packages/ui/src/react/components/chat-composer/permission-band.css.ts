import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const band = style({
  display: 'flex',
  alignItems: 'center',
  gap: '0.75rem',
  borderRadius: `${tokenVars.radiusXl} ${tokenVars.radiusXl} 0 0`,
  border: `1px solid ${vars.border}`,
  borderBottomWidth: 0,
  paddingLeft: '0.75rem',
  paddingRight: '0.75rem',
  paddingTop: '0.5rem',
  paddingBottom: '0.5rem',
  backgroundColor: `var(--composer-bg, ${vars.surfaceBaseEmphasis})`,
  color: vars.foreground,
  fontSize: tokenVars.textXs,
});

export const bandIcon = style({
  flexShrink: 0,
  width: '0.875rem',
  height: '0.875rem',
  color: vars.foregroundMuted,
});

export const bandLabel = style({
  flex: 1,
  minWidth: 0,
  display: '-webkit-box',
  overflow: 'hidden',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 2,
  lineHeight: 1.375,
  color: vars.foregroundMuted,
});

export const bandLabelStrong = style({
  fontWeight: 400,
  color: vars.foreground,
});

/** The plan, command, paths, or question the user is deciding on. */
export const bandBody = style({
  display: 'block',
  marginTop: '0.25rem',
  maxHeight: '6rem',
  overflow: 'auto',
  whiteSpace: 'pre-wrap',
  overflowWrap: 'anywhere',
  color: vars.foregroundMuted,
});

export const bandCounter = style({
  marginLeft: '0.375rem',
  opacity: 0.6,
});

export const bandAction = style({
  flexShrink: 0,
});

/** Every answer of a short question, side by side. */
export const bandActions = style({
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  flexShrink: 0,
});

globalStyle(`${bandAction} button, ${bandActions} button`, {
  backgroundColor: vars.surfaceElevated,
  color: vars.foreground,
  borderColor: `color-mix(in srgb, ${vars.foreground} 12%, transparent)`,
});

globalStyle(`${bandAction} button:hover, ${bandActions} button:hover`, {
  backgroundColor: vars.surfaceElevatedHover,
  color: vars.foreground,
});

globalStyle(`${bandAction} button[aria-expanded="true"]`, {
  backgroundColor: vars.surfaceElevatedSelected,
  color: vars.foreground,
});

globalStyle(`${bandAction} button[data-popup-open]`, {
  backgroundColor: vars.surfaceElevatedSelected,
  color: vars.foreground,
});
