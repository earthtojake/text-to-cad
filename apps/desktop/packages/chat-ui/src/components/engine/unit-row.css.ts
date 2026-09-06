import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';

/** Debug overlay: dashed outline around the reserved height slot. */
export const debugOverlay = style({
  pointerEvents: 'none',
  position: 'absolute',
  left: 0,
  right: 0,
  top: 0,
  outlineStyle: 'dashed',
  outlineWidth: '1px',
});

/** Debug overlay in OK state — faint green outline. */
export const debugOk = style({
  outlineColor: 'rgba(52, 211, 153, 0.5)', // emerald-400/50
});

/** Debug overlay in mismatch state — red outline. */
export const debugMismatch = style({
  outlineColor: 'rgba(239, 68, 68, 0.8)', // red-500/80
});

/** Debug label chip — dark background, small monospace text. */
export const debugLabel = style({
  position: 'absolute',
  top: 0,
  left: 0,
  background: 'rgba(0,0,0,0.7)',
  paddingLeft: '4px',
  paddingRight: '4px',
  fontSize: '9px',
  lineHeight: 'tight',
  color: '#fff',
});

/** Debug mismatch text — red. */
export const debugMismatchText = style({
  color: vars.diffDeleted,
});
