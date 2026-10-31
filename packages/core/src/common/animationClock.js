// The animation TRANSPORT, shared by every player (an engine document's motions, a GLB's
// clips): how fast the clock runs, where it is, and how it advances. What a time poses is the
// player's (`lib/xbf/xbfMotion.js`, `lib/render/glbAnimationRuntime.js`); this module owns only
// the clock around it.

export const ANIMATION_SPEED_MIN = 0.1;
export const ANIMATION_SPEED_MAX = 3;

function clampNumber(value, min, max) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return min;
  }
  return Math.min(Math.max(numericValue, min), max);
}

export function clampAnimationSpeed(value) {
  return clampNumber(value, ANIMATION_SPEED_MIN, ANIMATION_SPEED_MAX);
}

export function clampAnimationElapsed(value, duration) {
  return clampNumber(value, 0, Math.max(Number(duration) || 0, 0));
}

/** Advance the clock one tick. Looping wraps; a non-looping clip stops at its
 * end, which is the one place playback ends on its own. */
export function advanceAnimationElapsed({
  elapsedSec = 0,
  deltaSec = 0,
  speed = 1,
  duration = 1,
  loopEnabled = true
} = {}) {
  const safeDuration = Math.max(Number(duration) || 0, 0.001);
  const next = Math.max(Number(elapsedSec) || 0, 0)
    + (Math.max(Number(deltaSec) || 0, 0) * clampAnimationSpeed(speed));
  if (loopEnabled) {
    return { elapsedSec: next % safeDuration, playing: true };
  }
  if (next >= safeDuration) {
    return { elapsedSec: safeDuration, playing: false };
  }
  return { elapsedSec: next, playing: true };
}

export function animationNowMs() {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}
