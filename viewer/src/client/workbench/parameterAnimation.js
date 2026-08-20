// "Does this definition ship animation clips?" — the same question for a STEP sidecar
// and an implicit module, so the toolbar's Play button can ask it without knowing which
// store it is looking at.
export function hasParameterAnimations(definition) {
  return Array.isArray(definition?.animations) && definition.animations.length > 0;
}

export function findParameterAnimation(definition, animationId) {
  const animations = Array.isArray(definition?.animations) ? definition.animations : [];
  if (!animations.length) {
    return null;
  }
  const normalizedId = String(animationId || "").trim();
  return animations.find((animation) => animation.id === normalizedId) || animations[0] || null;
}

// Frame pacing for animation playback.  The floor sits under a display frame so
// an unsaturated model publishes on every rAF; the ceiling stops a very heavy
// model from pacing itself below 4 fps.
export const MIN_ANIMATION_FRAME_MS = 8;
export const SATURATED_ANIMATION_FRAME_MS = 32;
export const MAX_ANIMATION_FRAME_MS = 250;

// How long to wait before publishing the next animation frame.
//
// Publishing costs far more than the tick that publishes it -- the store notify
// re-renders the workspace, reapplies every module effect across the display
// records and redraws the scene.  On a large assembly that lands well over a
// display frame, so publishing on every rAF saturates the main thread: the
// clock keeps advancing but the browser never gets a slot to composite, and
// playback reads as frozen even though dragging the same parameter still works
// (a drag pays the cost once).
//
// The cost of a frame is measured as the gap to the following callback, which
// is the one number that includes the downstream render.  While that gap stays
// inside a couple of display frames nothing is overrunning -- rAF is simply
// running at the refresh rate -- so pace at the floor and publish every time.
// Once it climbs past that, frames ARE overrunning, so budget at twice what the
// last one cost: the browser gets roughly half the wall clock back for
// compositing and input, and playback degrades to a lower frame rate instead of
// locking up the tab.
//
// Budgeting at exactly the measured cost would do nothing -- the callback that
// measures a 73 ms frame arrives 73 ms after it, already clearing a 73 ms
// budget -- so the factor is what actually buys the idle time.
export function animationFrameBudgetMs(publishCostMs) {
  const cost = Number(publishCostMs);
  if (!Number.isFinite(cost) || cost <= SATURATED_ANIMATION_FRAME_MS) {
    return MIN_ANIMATION_FRAME_MS;
  }
  return Math.min(cost * 2, MAX_ANIMATION_FRAME_MS);
}

export function shouldPublishAnimationFrame({ timeMs, publishedAtMs, publishCostMs }) {
  if (!Number.isFinite(publishedAtMs)) {
    return true;
  }
  return (timeMs - publishedAtMs) >= animationFrameBudgetMs(publishCostMs);
}

export function buildDefaultParameterAnimationState(definition) {
  const animation = findParameterAnimation(definition, "");
  return {
    activeId: animation?.id || "",
    playing: false,
    elapsedSec: 0,
    speed: 1
  };
}
