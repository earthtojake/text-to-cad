import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';

/** Full-width 1px separator line. Positioned absolutely within BlockFrame. */
export const ruleLine = style({
  position: 'absolute',
  inset: 0,
  background: vars.border,
});
