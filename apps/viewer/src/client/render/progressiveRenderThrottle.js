// While a package publishes progressively, every publish, effect and worker
// arrival asks for a frame; a 3,259-occurrence frame costs ~8 ms, and a main
// thread painting at vsync between publishes starves the decode/compose work
// the load is waiting on. The throttle caps frames to one per interval while
// the load is in flight; the final publish clears the flag and the rate is
// normal again. Pure: the runtime hook feeds it clock and state.
export const PROGRESSIVE_LOAD_FRAME_INTERVAL_MS = 250;

// Milliseconds to wait before the next frame may render (0 = render now).
export function progressiveRenderDelay({
  progressiveLoadActive = false,
  lastRenderAt = 0,
  now = 0,
  intervalMs = PROGRESSIVE_LOAD_FRAME_INTERVAL_MS
} = {}) {
  if (!progressiveLoadActive) {
    return 0;
  }
  const elapsed = Number(now) - Number(lastRenderAt || 0);
  if (!Number.isFinite(elapsed) || elapsed >= intervalMs) {
    return 0;
  }
  return Math.max(1, Math.ceil(intervalMs - elapsed));
}
