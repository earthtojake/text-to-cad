import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';

/** GenericFileIcon: muted color, no flex shrink. */
export const genericFileIcon = style({
  color: vars.fgMuted,
  flexShrink: 0,
});
