/**
 * code.css.ts — styles for Code.tsx.
 *
 * The complex patterns replaced here:
 *   [&_span]:text-(--shiki-light)         → globalStyle for spans inside wrapper
 *   emdark:[&_span]:text-(--shiki-dark)   → globalStyle with .emdark ancestor
 *   scrollbar-thin                         → custom scrollbar styles
 */

import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';

/** Scroll + card container (inner div, no .pblock so overflow-x-auto wins). */
export const codeWrapper = style({
  position: 'absolute',
  inset: 0,
  overflowX: 'auto',
  overflowY: 'hidden',
  borderRadius: vars.radiusLg,
  border: `1px solid ${vars.border}`,
  paddingLeft: '8px',
  background: 'transparent',
  // Thin scrollbar
  scrollbarWidth: 'thin',
});

/** Shiki token color: light mode — spans inside the wrapper. */
globalStyle(`${codeWrapper} span`, {
  color: 'var(--shiki-light)',
});

/** Shiki token color: dark mode — when .emdark is an ancestor. */
globalStyle(`.emdark ${codeWrapper} span`, {
  color: 'var(--shiki-dark)',
});

/** Each code line div — font metrics come from --chat-type-code-* variables. */
export const codeLine = style({
  position: 'absolute',
  whiteSpace: 'pre',
  fontFamily: vars.typeCodeFontFamily,
  fontSize: vars.typeCodeFontSize,
  lineHeight: vars.typeCodeLineHeight,
  fontWeight: vars.typeCodeFontWeight,
  color: vars.fg,
});
