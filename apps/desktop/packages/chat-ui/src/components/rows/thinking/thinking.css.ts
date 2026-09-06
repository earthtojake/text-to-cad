import { keyframes, style } from '@vanilla-extract/css';
import { createVariableThemeContract } from '@styles/variable-theme-contract.css';

// ── Runtime geometry contract ─────────────────────────────────────────────────

export type ThinkingStyleVars = {
  height: number;
};

export const thinkingCardVars = createVariableThemeContract<ThinkingStyleVars>({
  height: null,
});

// overflow: hidden ensures that any transient measure-vs-render height desync
// (e.g. during a mid-tween frame or a stale virtualizer size) degrades to
// clipped content rather than spilling over the following row.
export const thinkingRoot = style({ height: thinkingCardVars.height, overflow: 'hidden' });

const thinkingArrive = keyframes({
  from: { opacity: 0, transform: 'translateY(2px)' },
  to: { opacity: 1, transform: 'translateY(0)' },
});

export const thinkingActive = style({
  animation: `${thinkingArrive} 180ms cubic-bezier(0.215, 0.61, 0.355, 1) both`,
  '@media': {
    '(prefers-reduced-motion: reduce)': {
      animation: 'none',
      transform: 'none',
    },
  },
});

export const thinkingLabel = style({
  fontVariantNumeric: 'tabular-nums',
});

export const thinkingStatus = style({
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  borderWidth: 0,
});
