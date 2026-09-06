import { abortableWait, abortReason } from './abortable-wait';
import { systemClock, type Clock } from './clock';

export type RunWithTimeoutOptions = {
  timeoutMs: number;
  signal?: AbortSignal;
  clock?: Clock;
};

export class TimeoutError extends Error {
  constructor(readonly durationMs: number) {
    super(`Operation timed out after ${durationMs}ms`);
    this.name = 'TimeoutError';
  }
}

export function runWithTimeout<T>(
  work: (signal: AbortSignal) => T | Promise<T>,
  options: RunWithTimeoutOptions
): Promise<T> {
  if (options.signal?.aborted) return Promise.reject(abortReason(options.signal));
  if (options.timeoutMs <= 0) return Promise.reject(new TimeoutError(options.timeoutMs));

  const clock = options.clock ?? systemClock;
  const controller = new AbortController();

  return abortableWait<T>({ signal: options.signal }, (settle) => {
    const timer = clock.schedule(
      options.timeoutMs,
      () => {
        const error = new TimeoutError(options.timeoutMs);
        if (!controller.signal.aborted) controller.abort(error);
        settle.reject(error);
      },
      { unref: true }
    );

    try {
      Promise.resolve(work(controller.signal)).then(settle.resolve, settle.reject);
    } catch (error) {
      settle.reject(error);
    }

    return () => {
      timer.dispose();
      // An outer abort must cancel the in-flight work; success/failure
      // settlements leave the child controller untouched.
      if (options.signal?.aborted && !controller.signal.aborted) {
        controller.abort(abortReason(options.signal));
      }
    };
  });
}
