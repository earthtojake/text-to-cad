/**
 * reset.css.ts — minimal CSS reset to replace the box-sizing + element resets
 * that Tailwind's preflight provided.
 *
 * KEY RISK: this reset must NOT change any element heights that pretext measures.
 * Run prose/diff/table/execute contract tests after any edit here.
 *
 * We intentionally do NOT include a full Tailwind preflight equivalent — only
 * the rules that chat-ui components actually rely on:
 *   - box-sizing: border-box on all elements
 *   - margin: 0 on block elements used in chat (p, h1-h6, etc.)
 *   - list-style: none on ul/ol
 * These are the rules Tailwind's preflight sets that affect layout height.
 *
 * Font-face @imports stay in chat.module.css (to be renamed chat-fonts.css).
 */

import { globalStyle } from '@vanilla-extract/css';

// Border-box sizing — prevents padding from bloating element dimensions.
globalStyle('*, *::before, *::after', {
  boxSizing: 'border-box',
});

// Zero out default browser margins on block elements used inside chat.
globalStyle('p, h1, h2, h3, h4, h5, h6, ul, ol, li, blockquote, pre, table, figure', {
  margin: 0,
  padding: 0,
});

// Remove bullet points that would shift list geometry.
globalStyle('ul, ol', {
  listStyle: 'none',
});

// Tables use border-collapse + border-spacing:0 inline; ensure no extra gaps.
globalStyle('table', {
  borderCollapse: 'separate',
  borderSpacing: 0,
});
