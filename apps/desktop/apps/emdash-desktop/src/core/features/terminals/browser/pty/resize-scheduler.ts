import { createDebounced } from '@emdash/shared/scheduling';

/**
 * Leading + trailing debounce for PTY resizes.
 *
 * measureAndResize() resizes the xterm grid SYNCHRONOUSLY (reflowing the
 * buffer).  A pure trailing debounce on the matching PTY resize left the child
 * TUI drawing against stale dimensions for the whole debounce window — its
 * in-place redraws (spinners, the input box) landed at the wrong rows and baked
 * overlapping output into scrollback that only a later full repaint cleared
 * (ENG-1577: "Claude Code output overlaps input field, fixed by resizing").
 *
 * Firing on the LEADING edge keeps the SIGWINCH the child receives in lockstep
 * with the xterm grid.  The leading flush consumes the pending value, so a lone
 * resize flushes exactly once; the trailing flush still captures the final
 * value of a burst (e.g. a continuous window drag), with the burst's middle
 * coalesced.  These are exactly the leading-edge semantics of the shared
 * debounce primitive (leading only fires after a full quiet window since the
 * last flush), so this module is a thin adapter over `createDebounced`.
 */
export interface ResizeScheduler<T> {
  /** Record the latest value; flush immediately on the leading edge, else coalesce. */
  schedule: (value: T) => void;
  /** Drop any pending trailing flush (call on teardown). */
  cancel: () => void;
}

export function createResizeScheduler<T>(
  flush: (value: T) => void,
  trailingMs: number
): ResizeScheduler<T> {
  const debounced = createDebounced(flush, { delayMs: trailingMs, leading: true });
  return {
    schedule: (value: T) => debounced.call(value),
    cancel: () => debounced.cancel(),
  };
}
