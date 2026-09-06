import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const selectableCard = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '100%',
  border: `1px solid ${vars.border}`,
  borderRadius: tokenVars.radiusLg,
  backgroundColor: vars.surfaceElevated,
  color: vars.foregroundMuted,
  transition: 'background-color 150ms, color 150ms, border-color 150ms',
  cursor: 'pointer',
  selectors: {
    '&:hover': {
      backgroundColor: vars.surfaceElevatedHover,
    },
    '&[data-selected="true"], &[aria-selected="true"]': {
      backgroundColor: vars.surfaceElevatedSelected,
      color: vars.foreground,
      borderColor: vars.borderPrimary,
    },
    '&[data-interactive="false"]': {
      color: vars.foregroundPassive,
      cursor: 'default',
    },
    '&[data-interactive="false"]:hover': {
      backgroundColor: vars.surfaceElevated,
    },
    '&:focus-visible': {
      outline: 'none',
      borderColor: vars.borderPrimary,
      boxShadow: `0 0 0 3px color-mix(in srgb, ${vars.borderPrimary} 30%, transparent)`,
    },
  },
});
