/**
 * reset.css.ts — mini preflight, assigned to the reset layer.
 *
 * Keeps box-sizing predictable, strips default browser margins/paddings,
 * and opts form controls into the design-system font. Intentionally minimal —
 * no opinionated colour or layout rules belong here.
 */

import { globalStyle } from '@vanilla-extract/css';
import { tokenVars } from '@theme/tokens.css';
import './layers.css';

globalStyle('*, *::before, *::after', {
  '@layer': {
    reset: {
      boxSizing: 'border-box',
    },
  },
});

globalStyle('html, body', {
  '@layer': {
    reset: {
      margin: 0,
      lineHeight: 'inherit',
      fontFamily: tokenVars.fontSans,
    },
  },
});

// Native form controls do not inherit fonts by default — opt them in so
// inputs, textareas, selects, and buttons use the design-system font.
globalStyle('button, input, optgroup, select, textarea', {
  '@layer': {
    reset: {
      font: 'inherit',
      letterSpacing: 'inherit',
      color: 'inherit',
    },
  },
});

// Strip native button chrome so the User-Agent ButtonFace background does not
// bleed through theme-driven styles (matches Tailwind Preflight). Without this,
// resting buttons that omit a background (e.g. ghost) show a theme-independent
// system gray instead of the surface behind them.
globalStyle('button', {
  '@layer': {
    reset: {
      appearance: 'none',
      backgroundColor: 'transparent',
      backgroundImage: 'none',
      cursor: 'pointer',
    },
  },
});

// Remove default block margins — matches Tailwind Preflight.
globalStyle('blockquote, dl, dd, h1, h2, h3, h4, h5, h6, hr, figure, p, pre', {
  '@layer': {
    reset: {
      margin: 0,
    },
  },
});

// Headings inherit type styles; size/weight come from utilities or component styles.
globalStyle('h1, h2, h3, h4, h5, h6', {
  '@layer': {
    reset: {
      fontSize: 'inherit',
      fontWeight: 'inherit',
    },
  },
});

// Lists: drop default indentation and margins.
// Does not set list-style: none — left to component/utility intent.
globalStyle('ol, ul', {
  '@layer': {
    reset: {
      margin: 0,
      padding: 0,
    },
  },
});
