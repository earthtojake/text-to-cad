import { globalStyle, style } from '@vanilla-extract/css';
import { svgDefaultSize } from '@styles/effects/svg-helpers.css';
import { menuItemBase } from '@styles/recipes/menu-item.css';
import { popupSurface, popupShadowSm } from '@styles/recipes/popup-surface.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const positioner = style({
  isolation: 'isolate',
  zIndex: 50,
});

export const comboboxTrigger = style([svgDefaultSize, {}]);

export const comboboxContent = style([
  popupSurface,
  popupShadowSm,
  {
    maxHeight: 'var(--available-height)',
    maxWidth: 'var(--available-width)',
    overflow: 'hidden',
    padding: '0.25rem',
    selectors: {
      '&[data-width="trigger"]': {
        width: 'var(--anchor-width)',
        minWidth: 'var(--anchor-width)',
      },
      '&[data-width="content"]': {
        width: 'max-content',
        minWidth: '11.25rem',
      },
      '&[data-width="content-at-least-trigger"]': {
        width: 'max-content',
        minWidth: 'max(11.25rem, var(--anchor-width))',
      },
    },
  },
]);

/** Outer wrapper that ScrollContainer renders — position context for the fade overlay. */
export const comboboxListScroller = style({});

/**
 * Applied to the scroll viewport inside ScrollContainer.
 * overscrollBehavior must be on the actual scrolling element.
 */
export const comboboxListViewport = style({
  overscrollBehavior: 'contain',
});

export const comboboxList = style({
  scrollPaddingTop: '0.25rem',
  scrollPaddingBottom: '0.25rem',
});

export const comboboxItem = style([
  menuItemBase({ trailingIndicator: true, fullWidth: true }),
  {
    selectors: {
      '&[data-highlighted]:not([data-selected])': { backgroundColor: vars.surfaceHover },
      '&[data-selected]': { backgroundColor: vars.surfaceSelected },
      '&[data-highlighted]': { color: vars.foreground },
      '&[data-disabled]': { pointerEvents: 'none', opacity: 0.5 },
      '&[data-disabled][data-hoverable-when-disabled]': {
        pointerEvents: 'auto',
        cursor: 'not-allowed',
      },
    },
  },
]);

export const comboboxItemIndicator = style({
  pointerEvents: 'none',
  position: 'absolute',
  right: '0.5rem',
  display: 'flex',
  width: '0.875rem',
  height: '0.875rem',
  alignItems: 'center',
  justifyContent: 'center',
});

export const comboboxLabel = style({
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  paddingTop: '0.25rem',
  paddingBottom: '0.25rem',
  fontSize: tokenVars.textTiny,
  color: vars.foregroundMuted,
});

export const comboboxEmpty = style({
  display: 'none',
  width: '100%',
  justifyContent: 'center',
  paddingTop: '0.5rem',
  paddingBottom: '0.5rem',
  textAlign: 'center',
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
  selectors: {
    // show when data-empty is on the parent popup
    '[data-slot="combobox-content"][data-empty] &': {
      display: 'flex',
    },
  },
});

export const comboboxSeparator = style({
  marginLeft: '-0.25rem',
  marginRight: '-0.25rem',
  marginTop: '0.25rem',
  marginBottom: '0.25rem',
  height: '1px',
  backgroundColor: vars.border,
});

export const comboboxChips = style({
  display: 'flex',
  minHeight: '2rem',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: '0.375rem',
  borderRadius: tokenVars.radiusMd,
  border: `1px solid ${vars.border}`,
  backgroundColor: 'transparent',
  backgroundClip: 'padding-box',
  paddingLeft: '0.625rem',
  paddingRight: '0.625rem',
  paddingTop: '0.375rem',
  paddingBottom: '0.375rem',
  fontSize: tokenVars.textSm,
  boxShadow: '0 1px 2px 0 rgba(0,0,0,0.05)',
  transition: 'color 150ms, box-shadow 150ms',
  selectors: {
    '&:focus-within': {
      borderColor: vars.borderPrimary,
      boxShadow: `0 0 0 3px color-mix(in srgb, ${vars.borderPrimary} 30%, transparent)`,
    },
    '&:has([aria-invalid="true"])': {
      borderColor: vars.borderDestructive,
      boxShadow: `0 0 0 3px color-mix(in srgb, ${vars.borderDestructive} 20%, transparent)`,
    },
    '&:has([data-slot="combobox-chip"])': {
      paddingLeft: '0.375rem',
    },
  },
});

export const comboboxChip = style({
  display: 'flex',
  height: '1.375rem',
  width: 'fit-content',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '0.25rem',
  borderRadius: tokenVars.radiusSm,
  backgroundColor: vars.surfaceHover,
  paddingLeft: '0.375rem',
  paddingRight: '0.375rem',
  fontSize: tokenVars.textXs,
  fontWeight: 400,
  whiteSpace: 'nowrap',
  color: vars.foreground,
  selectors: {
    '&:has([disabled])': { pointerEvents: 'none', cursor: 'not-allowed', opacity: 0.5 },
    '&:has([data-slot="combobox-chip-remove"])': { paddingRight: 0 },
  },
});

export const comboboxChipRemove = style({
  marginLeft: '-0.25rem',
  opacity: 0.5,
  selectors: {
    '&:hover': { opacity: 1 },
  },
});

export const comboboxChipsInput = style({
  minWidth: '4rem',
  flex: 1,
  outline: 'none',
});

/**
 * Applied to the trigger InputGroupButton inside ComboboxInput.
 * Hides when a sibling combobox-clear button is present; clears pressed bg.
 */
export const triggerButtonHideIfClear = style({
  selectors: {
    '&[data-pressed]': { backgroundColor: 'transparent' },
  },
});
globalStyle(
  `[data-slot="input-group"]:has([data-slot="combobox-clear"]) ${triggerButtonHideIfClear}`,
  { display: 'none' }
);
