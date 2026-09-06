import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';

/** Story viewport box — sizes the scroll viewport for chat stories. */
export const storyViewport = style({
  border: `1px solid ${vars.border}`,
  background: vars.bg,
  overflow: 'hidden',
  borderRadius: '8px',
});
