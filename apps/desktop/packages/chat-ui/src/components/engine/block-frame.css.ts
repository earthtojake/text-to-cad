/**
 * block-frame.css.ts — base positioning for all block-level content.
 *
 * BlockFrame renders a div with this class. Block-kind-specific visual styles
 * are applied via a second class prop.
 */

import { style } from '@vanilla-extract/css';

export const pblock = style({
  position: 'absolute',
  left: 0,
  width: '100%',
  overflow: 'visible',
  // Ensure border-box sizing regardless of host preflight.
  boxSizing: 'border-box',
  // Skip layout/paint for off-screen blocks inside tall units (long messages,
  // code blocks, tables). The exact contain-intrinsic-size is set as an inline
  // style in BlockFrame using the measured height, so the browser reserves the
  // correct space while the block is skipped. On-screen blocks are unaffected
  // (content-visibility: auto removes containment for visible elements).
  contentVisibility: 'auto',
});

// ── Debug overlay ─────────────────────────────────────────────────────────────

export const debugOverlay = style({
  pointerEvents: 'none',
  position: 'absolute',
  inset: 0,
  outlineStyle: 'dashed',
  outlineWidth: '1px',
});

export const debugOk = style({
  outlineColor: 'rgba(56, 189, 248, 0.6)', // sky-400/60
});

export const debugMismatch = style({
  outlineColor: 'rgb(239, 68, 68)', // red-500
});

export const debugLabel = style({
  position: 'absolute',
  top: 0,
  right: 0,
  background: 'rgba(0,0,0,0.7)',
  paddingLeft: '4px',
  paddingRight: '4px',
  fontSize: '10px',
  lineHeight: 'tight',
  color: '#fff',
});

export const debugMismatchText = style({
  color: 'rgb(248, 113, 113)', // red-400
});
