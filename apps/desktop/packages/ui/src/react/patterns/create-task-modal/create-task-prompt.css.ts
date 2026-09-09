import { style } from '@vanilla-extract/css';
import { svgContainer, svgSmSize } from '@styles/effects/svg-helpers.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const root = style({
  position: 'relative',
  display: 'flex',
  minHeight: 0,
  flex: 1,
  flexDirection: 'column',
  overflow: 'hidden',
});

export const editor = style({
  minHeight: '7rem',
  flex: 1,
  overflowY: 'auto',
  paddingBlock: tokenVars.space2,
});

export const readOnlyReason = style({
  flexShrink: 0,
  color: vars.foregroundMuted,
  fontSize: tokenVars.textXs,
});

export const completionStatus = style([
  svgContainer,
  svgSmSize,
  {
    display: 'flex',
    flexShrink: 0,
    alignItems: 'center',
    gap: tokenVars.space2,
    borderRadius: tokenVars.radiusSm,
    backgroundColor: vars.surfaceHover,
    padding: tokenVars.space2,
    color: vars.foregroundMuted,
    fontSize: tokenVars.textXs,
  },
]);

export const fileMentions = style({
  display: 'flex',
  flexShrink: 0,
  flexWrap: 'wrap',
  gap: tokenVars.space1,
  paddingBlockEnd: tokenVars.space1,
});

export const fileMention = style([
  svgContainer,
  svgSmSize,
  {
    display: 'inline-flex',
    maxWidth: '14rem',
    alignItems: 'center',
    gap: tokenVars.space1,
    borderRadius: tokenVars.radiusSm,
    backgroundColor: vars.surfaceHover,
    padding: `${tokenVars.space1} ${tokenVars.space2}`,
    color: vars.foreground,
    fontSize: tokenVars.textXs,
  },
]);

export const resourceName = style({
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const resourceError = style({
  color: vars.surfaceDestructiveForeground,
});

export const imageShelf = style({
  display: 'flex',
  minHeight: 0,
  flexShrink: 0,
  gap: tokenVars.space2,
  overflowX: 'auto',
  paddingBlock: tokenVars.space1,
});

export const image = style({
  position: 'relative',
  display: 'grid',
  width: '8.5rem',
  height: '3.75rem',
  flexShrink: 0,
  gridTemplateColumns: '3.25rem minmax(0, 1fr)',
  alignItems: 'center',
  gap: tokenVars.space1,
  overflow: 'hidden',
  border: `1px solid ${vars.border}`,
  borderRadius: tokenVars.radiusMd,
  backgroundColor: vars.surface,
  padding: tokenVars.space1,
  color: vars.foreground,
});

export const thumbnail = style({
  width: '3.25rem',
  height: '3.25rem',
  borderRadius: tokenVars.radiusSm,
  objectFit: 'cover',
});

export const imagePlaceholder = style([
  svgContainer,
  svgSmSize,
  {
    display: 'grid',
    width: '3.25rem',
    height: '3.25rem',
    placeItems: 'center',
    borderRadius: tokenVars.radiusSm,
    backgroundColor: vars.surfaceHover,
    color: vars.foregroundMuted,
  },
]);

export const imageActions = style({
  position: 'absolute',
  insetBlockStart: tokenVars.space1,
  insetInlineEnd: tokenVars.space1,
  display: 'flex',
  gap: tokenVars.space1,
});

export const dropOverlay = style({
  pointerEvents: 'none',
  position: 'absolute',
  zIndex: 2,
  inset: tokenVars.space1,
  display: 'grid',
  placeItems: 'center',
  border: `1px dashed ${vars.borderPrimary}`,
  borderRadius: tokenVars.radiusMd,
  backgroundColor: `color-mix(in srgb, ${vars.surface} 88%, transparent)`,
  color: vars.foreground,
  fontSize: tokenVars.textSm,
});
