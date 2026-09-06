import { abortableWait, throwIfAborted } from './abortable-wait';
import type { TimerHandle } from './timer-handle';

export const MAX_TIMER_DELAY_MS = 2_147_483_647;

export type ScheduleOptions = {
  unref?: boolean;
};

export type SleepOptions = ScheduleOptions & {
  signal?: AbortSignal;
};

export interface Clock {
  now(): number;
  schedule(delayMs: number, callback: () => void, options?: ScheduleOptions): TimerHandle;
  sleep(delayMs: number, options?: SleepOptions): Promise<void>;
}

export const systemClock: Clock = {
  now: () => Date.now(),
  schedule(delayMs, callback, options = {}) {
    let active = true;
    const timer = setTimeout(() => {
      if (!active) return;
      active = false;
      callback();
    }, normalizeDelay(delayMs));
    if (options.unref) {
      (timer as unknown as { unref?: () => void }).unref?.();
    }
    return {
      get active() {
        return active;
      },
      dispose() {
        if (!active) return;
        active = false;
        clearTimeout(timer);
      },
    };
  },
  sleep(delayMs, options = {}) {
    return sleepWithClock(systemClock, delayMs, options);
  },
};

export function normalizeDelay(delayMs: number): number {
  if (!Number.isFinite(delayMs)) return MAX_TIMER_DELAY_MS;
  return Math.min(MAX_TIMER_DELAY_MS, Math.max(0, Math.floor(delayMs)));
}

export function waitWithSignal<T>(
  promise: Promise<T>,
  signal: AbortSignal,
  fallback?: string
): Promise<T> {
  return abortableWait<T>({ signal, fallback }, (settle) => {
    promise.then(settle.resolve, settle.reject);
  });
}

export function sleepWithClock(
  clock: Pick<Clock, 'schedule'>,
  delayMs: number,
  options: SleepOptions = {}
): Promise<void> {
  throwIfAborted(options.signal);
  if (delayMs <= 0) return Promise.resolve();

  return abortableWait<void>({ signal: options.signal }, (settle) => {
    const timer = clock.schedule(delayMs, () => settle.resolve(), options);
    return () => timer.dispose();
  });
}
