import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const description = style({
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
});
