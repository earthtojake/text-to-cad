import { keyframes, style } from '@vanilla-extract/css';

// ── Segment count and timing ───────────────────────────────────────────────────

const SEGMENTS = 8;
const PERIOD_MS = 900;

// ── Fade keyframe ─────────────────────────────────────────────────────────────
//
// Each segment runs this same fade. Because every segment is offset by an equal
// fraction of the period (via a negative animation-delay), the "bright head"
// appears to sweep clockwise around the icon without the SVG itself rotating.

const segmentFade = keyframes({
  '0%': { opacity: 1 },
  '25%': { opacity: 0.55 },
  '50%': { opacity: 0.25 },
  '75%': { opacity: 0.12 },
  '100%': { opacity: 0.08 },
});

// ── Per-segment styles (generated at build time) ──────────────────────────────
//
// Array.from with style() calls is valid VanillaExtract: each style() call is
// evaluated at build time and registers a unique class in the generated CSS.

export const segment = Array.from({ length: SEGMENTS }, (_, i) =>
  style({
    animationName: segmentFade,
    animationDuration: `${PERIOD_MS}ms`,
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
    // Negative delay so each segment starts at a different point in the cycle.
    // Reversing the index (SEGMENTS - i) % SEGMENTS makes the bright head travel
    // clockwise: segment 0 is bright at t=0, segment 1 at t=step, etc.
    animationDelay: `${-((SEGMENTS - i) % SEGMENTS) * (PERIOD_MS / SEGMENTS)}ms`,
    '@media': {
      '(prefers-reduced-motion: reduce)': {
        animationName: 'none',
        // Render a static pattern at reduced opacity so the icon is still visible.
        opacity: `${0.08 + (1 - 0.08) * ((SEGMENTS - 1 - i) / (SEGMENTS - 1))}`,
      },
    },
  })
);
