import { style } from '@vanilla-extract/css';

/**
 * Overrides applied on top of inputVariants to turn a fixed-height input into
 * an auto-growing textarea.
 */
export const textareaOverride = style({
  height: 'auto',
  // field-sizing: content makes the textarea grow with its text content (modern browsers).
  // @ts-ignore — non-standard property, not yet in TypeScript's CSSType
  fieldSizing: 'content',
  minHeight: '4rem',
  paddingTop: '0.5rem',
  paddingBottom: '0.5rem',
});
