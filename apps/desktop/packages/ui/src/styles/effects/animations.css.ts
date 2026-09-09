/**
 * animations.css.ts — Vanilla Extract keyframes for overlay primitives.
 * (dialog, sheet, popover, dropdown, select, combobox)
 *
 *  - kfPopupIn/Out           fade + zoom (for dialogs and side-less popups)
 *  - kfPopupInSlideFrom*     fade + zoom + 0.5rem slide (for positioner popups)
 *  - kfSlide{In/Out}{From/To}{Right/Left}  full-width slides (for sheets)
 */

import { keyframes } from '@vanilla-extract/css';

// ── Fade (backdrop / overlay) ─────────────────────────────────────────────────

export const kfFadeIn = keyframes({
  from: { opacity: 0 },
  to: { opacity: 1 },
});

export const kfFadeOut = keyframes({
  from: { opacity: 1 },
  to: { opacity: 0 },
});

// ── Popup: fade + zoom (dialog, no-side popups) ───────────────────────────────

export const kfPopupIn = keyframes({
  from: { opacity: 0, transform: 'scale(0.95)' },
  to: { opacity: 1, transform: 'scale(1)' },
});

export const kfPopupOut = keyframes({
  from: { opacity: 1, transform: 'scale(1)' },
  to: { opacity: 0, transform: 'scale(0.95)' },
});

// ── Popup: fade + zoom + slide (positioner popups, 0.5rem offset) ─────────────
// data-side=bottom → popup opens below trigger → slides IN from the top
export const kfPopupInSlideFromTop = keyframes({
  from: { opacity: 0, transform: 'scale(0.95) translateY(-0.5rem)' },
  to: { opacity: 1, transform: 'scale(1) translateY(0)' },
});

// data-side=top → popup opens above trigger → slides IN from the bottom
export const kfPopupInSlideFromBottom = keyframes({
  from: { opacity: 0, transform: 'scale(0.95) translateY(0.5rem)' },
  to: { opacity: 1, transform: 'scale(1) translateY(0)' },
});

// data-side=right / inline-end → popup to the right → slides IN from the left
export const kfPopupInSlideFromLeft = keyframes({
  from: { opacity: 0, transform: 'scale(0.95) translateX(-0.5rem)' },
  to: { opacity: 1, transform: 'scale(1) translateX(0)' },
});

// data-side=left / inline-start → popup to the left → slides IN from the right
export const kfPopupInSlideFromRight = keyframes({
  from: { opacity: 0, transform: 'scale(0.95) translateX(0.5rem)' },
  to: { opacity: 1, transform: 'scale(1) translateX(0)' },
});

// ── Sheet slides (full translate, no zoom) ────────────────────────────────────

export const kfSlideInFromRight = keyframes({
  from: { transform: 'translateX(100%)' },
  to: { transform: 'translateX(0)' },
});

export const kfSlideInFromLeft = keyframes({
  from: { transform: 'translateX(-100%)' },
  to: { transform: 'translateX(0)' },
});

export const kfSlideOutToRight = keyframes({
  from: { transform: 'translateX(0)' },
  to: { transform: 'translateX(100%)' },
});

export const kfSlideOutToLeft = keyframes({
  from: { transform: 'translateX(0)' },
  to: { transform: 'translateX(-100%)' },
});

export const kfSlideInFromTop = keyframes({
  from: { transform: 'translateY(-100%)' },
  to: { transform: 'translateY(0)' },
});

export const kfSlideInFromBottom = keyframes({
  from: { transform: 'translateY(100%)' },
  to: { transform: 'translateY(0)' },
});

export const kfSlideOutToTop = keyframes({
  from: { transform: 'translateY(0)' },
  to: { transform: 'translateY(-100%)' },
});

export const kfSlideOutToBottom = keyframes({
  from: { transform: 'translateY(0)' },
  to: { transform: 'translateY(100%)' },
});

// ── Convenience: selectors blocks for positioner popups ───────────────────────
// Import the individual keyframe constants above and compose into style() calls.
// The per-side selectors use higher specificity ([data-open][data-side=*]) so
// they override the fallback [data-open] animation without !important.
