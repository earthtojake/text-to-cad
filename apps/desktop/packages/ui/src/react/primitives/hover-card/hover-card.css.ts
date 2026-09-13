import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';

/** Default style for HoverCard when no className is passed. */
export const hoverCardDefault = style({
  width: 'auto',
  padding: 0,
  color: vars.foreground,
});
