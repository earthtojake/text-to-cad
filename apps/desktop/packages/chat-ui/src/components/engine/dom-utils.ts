/**
 * Shared lightweight DOM helpers for imperative operations in components.
 */

export function scheduleIdle(fn: () => void): number {
  if (typeof requestIdleCallback === 'function') {
    return requestIdleCallback(fn);
  }
  return window.setTimeout(fn, 0) as unknown as number;
}

export function cancelIdle(handle: number): void {
  if (typeof cancelIdleCallback === 'function') {
    cancelIdleCallback(handle);
  } else {
    clearTimeout(handle);
  }
}
