import { style } from '@vanilla-extract/css';
import { menuItemBase } from '@styles/recipes/menu-item.css';
import { popupShadowMd, popupSurface } from '@styles/recipes/popup-surface.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const positioner = style({
  isolation: 'isolate',
  zIndex: 50,
  outline: 'none',
});

export const menuContent = style([
  popupSurface,
  popupShadowMd,
  {
    maxHeight: 'var(--available-height)',
    maxWidth: 'var(--available-width)',
    overflowX: 'hidden',
    overflowY: 'auto',
    padding: '0.25rem',
    selectors: {
      '&[data-width="trigger"]': {
        width: 'var(--anchor-width)',
        minWidth: '12rem',
      },
      '&[data-width="content"]': {
        width: 'max-content',
        minWidth: '12rem',
      },
      '&[data-width="content-at-least-trigger"]': {
        width: 'max-content',
        minWidth: 'max(12rem, var(--anchor-width))',
      },
      '&[data-slot="dropdown-menu-sub-content"][data-width="content"]': {
        minWidth: '6rem',
      },
      '&[data-closed]': { overflow: 'hidden' },
    },
  },
]);

export const menuLabel = style({
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  paddingTop: '0.25rem',
  paddingBottom: '0.25rem',
  fontSize: tokenVars.textTiny,
  fontWeight: 400,
  color: vars.foregroundMuted,
  selectors: {
    '&[data-inset]': { paddingLeft: '2rem' },
  },
});

export const menuItem = style([
  menuItemBase(),
  {
    selectors: {
      '&:focus': { backgroundColor: vars.surfaceHover, color: vars.foreground },
      '&[data-inset]': { paddingLeft: '2rem' },
      '&[data-variant="destructive"]': { color: vars.foregroundDestructive },
      '&[data-variant="destructive"]:focus': {
        backgroundColor: vars.backgroundDestructive,
        color: vars.foregroundDestructive,
      },
      '&[data-disabled]': { pointerEvents: 'none', opacity: 0.5 },
    },
  },
]);

export const menuSubTrigger = style([
  menuItemBase(),
  {
    selectors: {
      '&:focus': { backgroundColor: vars.surfaceHover, color: vars.foreground },
      '&[data-inset]': { paddingLeft: '2rem' },
      '&[data-popup-open]': { backgroundColor: vars.surfaceHover, color: vars.foreground },
      '&[data-open]': { backgroundColor: vars.surfaceHover, color: vars.foreground },
    },
  },
]);

export const menuCheckboxItem = style([
  menuItemBase({ trailingIndicator: true, muted: true }),
  {
    selectors: {
      '&[data-checked]': { color: vars.foreground, backgroundColor: vars.surfaceSelected },
      '&:focus': { backgroundColor: vars.surfaceHover, color: vars.foreground },
      '&[data-inset]': { paddingLeft: '2rem' },
      '&[data-disabled]': { pointerEvents: 'none', opacity: 0.5 },
    },
  },
]);

export const menuRadioItem = style([
  menuItemBase({ trailingIndicator: true, muted: true }),
  {
    selectors: {
      '&[data-checked]': { color: vars.foreground, backgroundColor: vars.surfaceSelected },
      '&:focus': { backgroundColor: vars.surfaceHover, color: vars.foreground },
      '&[data-inset]': { paddingLeft: '2rem' },
      '&[data-disabled]': { pointerEvents: 'none', opacity: 0.5 },
    },
  },
]);

export const menuItemIndicator = style({
  pointerEvents: 'none',
  position: 'absolute',
  right: '0.5rem',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
});

export const menuSeparator = style({
  marginLeft: '-0.25rem',
  marginRight: '-0.25rem',
  marginTop: '0.25rem',
  marginBottom: '0.25rem',
  height: '1px',
  backgroundColor: vars.border,
});

export const menuShortcut = style({
  marginLeft: 'auto',
  fontSize: tokenVars.textXs,
  letterSpacing: '0.1em',
  color: vars.foregroundMuted,
  // When the parent menu item is focused, shortcut adapts to foreground color
  selectors: {
    '[data-slot="dropdown-menu-item"]:focus &': { color: vars.foreground },
  },
});
