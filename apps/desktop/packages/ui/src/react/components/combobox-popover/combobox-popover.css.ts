import { style } from '@vanilla-extract/css';
import { fieldShellBase } from '@styles/recipes/field-shell.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const trigger = style({
  display: 'flex',
  height: '1.75rem',
  minWidth: 0,
  alignItems: 'center',
  gap: '0.375rem',
  borderRadius: tokenVars.radiusMd,
  border: '1px solid transparent',
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  fontSize: tokenVars.textXs,
  color: vars.foreground,
  outline: 'none',
  selectors: {
    '&:hover': { backgroundColor: vars.surfaceBaseSelected },
    '&[data-popup-open]': { backgroundColor: vars.surfaceBaseSelected },
    '&[data-disabled], &:disabled': { cursor: 'not-allowed', opacity: 0.6 },
  },
});

export const triggerLabel = style({
  display: 'inline-flex',
  minWidth: 0,
  flex: 1,
  alignItems: 'center',
  lineHeight: 1,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  textAlign: 'left',
});

export const triggerChevron = style({
  flexShrink: 0,
  width: '0.75rem',
  height: '0.75rem',
  color: vars.foregroundMuted,
});

/** Default min-width for the combobox dropdown content. */
export const contentMinWidth = style({ minWidth: '11.25rem' }); // 180px

/**
 * Input-appearance trigger layout.
 * Composed with fieldShellBase for the full input look (border, bg, focus ring).
 */
export const triggerInput = [
  fieldShellBase,
  style({
    display: 'flex',
    width: '100%',
    height: '2rem',
    alignItems: 'center',
    gap: '0.375rem',
    paddingLeft: '0.625rem',
    paddingRight: '0.375rem',
    fontSize: tokenVars.textSm,
    selectors: {
      '&[data-placeholder]': { color: vars.foregroundPassive },
    },
  }),
] as const;
