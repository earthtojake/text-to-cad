/**
 * Decides which ResizeObserver height observations should trigger an
 * animation.
 *
 * The first observation is always swallowed: ResizeObserver fires once
 * immediately after `observe()` with the size that was already measured
 * synchronously before first paint, so animating it would replay the initial
 * mount. Later observations only signal when the height actually changed
 * from the last known value.
 */
export function createHeightChangeTracker(initialHeight: number | undefined) {
  let lastHeight = initialHeight;
  let isFirstObservation = true;

  return {
    /** Returns the height to animate to, or null when nothing should happen. */
    observe(height: number): number | null {
      if (isFirstObservation) {
        isFirstObservation = false;
        // Never overwrite a real initial measurement: if the content changed
        // between that measurement and this first callback, the next
        // observation must still register as a change from the measured
        // baseline. Only adopt the observation when no baseline exists.
        if (lastHeight === undefined) {
          lastHeight = height;
        }
        return null;
      }
      if (height === lastHeight) {
        return null;
      }
      lastHeight = height;
      return height;
    },
  };
}
