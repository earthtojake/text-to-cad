/**
 * storybook.css.ts — VE styles used by the Storybook preview decorator.
 *
 * Kept under src/ (not .storybook/) so the vanillaExtractPlugin reliably
 * processes it as part of the chat-ui source graph.
 */

import { style } from '@vanilla-extract/css';
import { vars } from './theme.css';

/** Story decorator wrapper — fills the viewport with the chat surface colors. */
export const storyDecorator = style({
  minHeight: '100vh',
  padding: '32px',
  background: vars.bg,
  color: vars.fg,
});
