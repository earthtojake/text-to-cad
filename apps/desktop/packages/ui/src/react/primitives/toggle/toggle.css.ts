import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

/** Container for a group of Toggle buttons. */
export const toggleGroup = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '0.125rem',
  borderRadius: tokenVars.radiusMd,
  backgroundColor: vars.surface,
  padding: '0.125rem',
});
