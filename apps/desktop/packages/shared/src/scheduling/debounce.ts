import { systemClock, type Clock } from './clock';
import type { TimerHandle } from './timer-handle';

export type CreateDebouncedOptions = {
  /** Quiet window: a trailing flush fires after `delayMs` without new calls. */
  delayMs: number;
  /**
   * Also fire on the leading edge. A leading flush consumes the value (a lone
   * call flushes exactly once) and fires only when no trailing flush is
   * pending AND at least `delayMs` has elapsed since the last flush of either
   * edge — so a burst flushes at most once per window, with the trailing
   * flush delivering the burst's final value.
   */
  leading?: boolean;
  clock?: Clock;
};

export interface Debounced<T> {
  /** Whether a trailing flush is currently scheduled. */
  readonly pending: boolean;
  /** Record the latest value; flush now (leading edge) or coalesce. */
  call(value: T): void;
  /** Deliver any pending value immediately and clear the timer. */
  flush(): void;
  /** Drop any pending value and timer without invoking the callback. */
  cancel(): void;
}

export function createDebounced<T>(
  fn: (value: T) => void,
  options: CreateDebouncedOptions
): Debounced<T> {
  const clock = options.clock ?? systemClock;
  const { delayMs, leading = false } = options;

  let timer: TimerHandle | null = null;
  let pending: { value: T } | null = null;
  let lastFlushAt = Number.NEGATIVE_INFINITY;

  const fire = (value: T): void => {
    lastFlushAt = clock.now();
    fn(value);
  };

  const fireTrailing = (): void => {
    timer = null;
    if (!pending) return;
    const { value } = pending;
    pending = null;
    fire(value);
  };

  return {
    get pending() {
      return pending !== null;
    },
    call(value: T) {
      if (leading && timer === null && clock.now() - lastFlushAt >= delayMs) {
        fire(value);
        return;
      }
      pending = { value };
      timer?.dispose();
      timer = clock.schedule(delayMs, fireTrailing);
    },
    flush() {
      if (!pending) return;
      timer?.dispose();
      timer = null;
      const { value } = pending;
      pending = null;
      fire(value);
    },
    cancel() {
      timer?.dispose();
      timer = null;
      pending = null;
    },
  };
}
