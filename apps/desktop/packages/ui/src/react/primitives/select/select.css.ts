import { globalStyle, style } from '@vanilla-extract/css';
import { menuItemBase } from '@styles/recipes/menu-item.css';
import { popupShadowMd, popupSurface } from '@styles/recipes/popup-surface.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const positioner = style({
  isolation: 'isolate',
  zIndex: 50,
});

export const selectGroup = style({
  scrollMarginTop: '0.25rem',
  scrollMarginBottom: '0.25rem',
  padding: '0.25rem',
});

export const selectValue = style({
  display: 'flex',
  flex: 1,
  textAlign: 'left',
});

export const selectContent = style([
  popupSurface,
  popupShadowMd,
  {
    isolation: 'isolate',
    maxHeight: 'var(--available-height)',
    maxWidth: 'var(--available-width)',
    overflowX: 'hidden',
    overflowY: 'auto',
    padding: '0.25rem',
    selectors: {
      '&[data-width="trigger"]': {
        width: 'var(--anchor-width)',
        minWidth: 'var(--anchor-width)',
      },
      '&[data-width="content"]': {
        width: 'max-content',
        minWidth: '9rem',
      },
      '&[data-width="content-at-least-trigger"]': {
        width: 'max-content',
        minWidth: 'max(9rem, var(--anchor-width))',
      },
      // When aligned with trigger, skip the popup animation.
      '&[data-align-trigger="true"]': { animation: 'none' },
    },
  },
]);

export const selectLabel = style({
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  paddingTop: '0.25rem',
  paddingBottom: '0.25rem',
  fontSize: tokenVars.textTiny,
  color: vars.foregroundMuted,
});

export const selectItem = style([
  menuItemBase({ trailingIndicator: true, fullWidth: true }),
  {
    selectors: {
      '&:focus:not([data-selected])': {
        backgroundColor: vars.surfaceHover,
        color: vars.foreground,
      },
      '&[data-selected]': { backgroundColor: vars.surfaceSelected, color: vars.foreground },
      '&[data-disabled]': { pointerEvents: 'none', opacity: 0.5 },
    },
  },
]);

export const selectItemText = style({
  display: 'flex',
  minWidth: 0,
  flex: 1,
  alignItems: 'center',
  gap: '0.5rem',
  overflow: 'hidden',
  whiteSpace: 'nowrap',
});

export const selectItemIndicator = style({
  pointerEvents: 'none',
  position: 'absolute',
  right: '0.5rem',
  display: 'flex',
  width: '1rem',
  height: '1rem',
  alignItems: 'center',
  justifyContent: 'center',
});

export const selectSeparator = style({
  pointerEvents: 'none',
  marginLeft: '-0.25rem',
  marginRight: '-0.25rem',
  marginTop: '0.25rem',
  marginBottom: '0.25rem',
  height: '1px',
  backgroundColor: vars.border,
});

export const scrollButton = style({
  zIndex: 10,
  display: 'flex',
  width: '100%',
  cursor: 'default',
  alignItems: 'center',
  justifyContent: 'center',
  backgroundColor: vars.surface,
  paddingTop: '0.25rem',
  paddingBottom: '0.25rem',
});
globalStyle(`${scrollButton} svg:not([class*='size-'])`, { width: '1rem', height: '1rem' });

export const triggerInvalidOverride = style({
  selectors: {
    '&[aria-invalid="true"]': {
      borderColor: vars.borderDestructive,
      boxShadow: `0 0 0 3px color-mix(in srgb, ${vars.borderDestructive} 20%, transparent)`,
    },
  },
});
