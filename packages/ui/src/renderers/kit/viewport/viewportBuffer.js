// Changing canvas dimensions clears its displayed pixels immediately. Queue
// quality/resize changes until the draw callback, so a held frame stays visible
// throughout asynchronous scene preparation, including on Retina displays.
export function createViewportBuffer(renderer, initial) {
  let applied = { ...initial };
  let pending = applied;
  return {
    request(next) { pending = { ...pending, ...next }; },
    flush() {
      const next = pending;
      if (next.width === applied.width && next.height === applied.height && next.pixelRatio === applied.pixelRatio) return false;
      renderer.setDrawingBufferSize(next.width, next.height, next.pixelRatio);
      applied = next;
      return true;
    },
  };
}
