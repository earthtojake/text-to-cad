import { abortReason, throwIfAborted } from './abortable-wait';
import { systemClock, type Clock } from './clock';
import type { RetrySchedule } from './retry-schedule';

export type RetryAttempt = {
  attempt: number;
  signal?: AbortSignal;
};

export type RetryOptions = {
  clock?: Clock;
  schedule: RetrySchedule;
  signal?: AbortSignal;
  shouldRetry: (error: unknown, context: RetryAttempt) => boolean;
  onRetry?: (event: {
    error: unknown;
    attempt: number;
    retryIndex: number;
    delayMs: number;
  }) => void;
};

export async function retry<T>(
  operation: (context: RetryAttempt) => Promise<T>,
  options: RetryOptions
): Promise<T> {
  const clock = options.clock ?? systemClock;
  let attempt = 0;

  for (;;) {
    throwIfAborted(options.signal);

    try {
      const value = await operation({ attempt, signal: options.signal });
      throwIfAborted(options.signal);
      return value;
    } catch (error) {
      if (options.signal?.aborted) throw abortReason(options.signal);
      if (!options.shouldRetry(error, { attempt, signal: options.signal })) throw error;

      const retryIndex = attempt;
      const delayMs = options.schedule.delayFor(retryIndex);
      if (delayMs === undefined) throw error;

      options.onRetry?.({ error, attempt, retryIndex, delayMs });
      await clock.sleep(delayMs, { signal: options.signal });
      attempt += 1;
    }
  }
}
