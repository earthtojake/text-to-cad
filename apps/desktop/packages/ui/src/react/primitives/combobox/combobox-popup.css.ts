import { globalStyle, style } from '@vanilla-extract/css';
import { kfPopupIn } from '@styles/effects/animations.css';
import { menuItemBase } from '@styles/recipes/menu-item.css';
import { popupShadowSm } from '@styles/recipes/popup-surface.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const popupRoot = style([
  popupShadowSm,
  {
    zIndex: 50,
    minWidth: '220px',
    maxWidth: '340px',
    overflow: 'hidden',
    borderRadius: tokenVars.radiusMd,
    backgroundColor: vars.surface,
    color: vars.foreground,
    animation: `${kfPopupIn} 100ms both`,
  },
]);

export const popupHeader = style({
  borderBottom: `1px solid ${vars.border}`,
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  paddingTop: '0.375rem',
  paddingBottom: '0.375rem',
  fontSize: tokenVars.textXs,
  color: vars.foregroundMuted,
});

export const popupList = style({
  maxHeight: '240px',
  scrollPaddingTop: '0.25rem',
  scrollPaddingBottom: '0.25rem',
  overflowY: 'auto',
  padding: '0.25rem',
});

export const popupItem = style([menuItemBase({ trailingIndicator: true, fullWidth: true }), {}]);

export const popupItemStacked = style({
  alignItems: 'flex-start',
  paddingRight: '0.5rem',
});

export const popupItemTextStack = style({
  display: 'flex',
  minWidth: 0,
  flex: '1 1 0%',
  flexDirection: 'column',
  gap: '0.125rem',
});

export const popupItemDefault = style({
  color: vars.foreground,
  textAlign: 'center',
});

export const popupSectionHeader = style({
  paddingTop: '0.5rem',
  paddingBottom: '0.25rem',
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  fontSize: tokenVars.textXs,
  fontWeight: 400,
  color: vars.foregroundMuted,
});

export const popupItemHighlighted = style({
  backgroundColor: vars.surfaceHover,
  color: vars.foreground,
});

export const popupItemHover = style({
  color: vars.foreground,
  selectors: {
    '&:hover': { backgroundColor: vars.surfaceHover },
  },
});

export const popupItemIcon = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'center',
  fontSize: '1em',
});
globalStyle(`${popupItemIcon} svg`, { width: '1rem', height: '1rem' });

export const popupItemLabel = style({
  // Keep the primary label visible before allowing the description/path to take space.
  flexGrow: 1,
  flexShrink: 0,
  flexBasis: 'auto',
  minWidth: 0,
  maxWidth: '100%',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const popupItemDescription = style({
  // High flex-shrink so the muted description ellipsizes before the (short)
  // primary label, keeping the command/mention name visible.
  flexGrow: 0,
  flexShrink: 100,
  flexBasis: 'auto',
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  fontSize: tokenVars.textXs,
  color: vars.foregroundMuted,
});

export const popupDismiss = style({
  display: 'inline-flex',
  width: '1rem',
  height: '1rem',
  flexShrink: 0,
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: tokenVars.radiusSm,
  opacity: 0.5,
  selectors: {
    '&:hover': { opacity: 1 },
  },
});
