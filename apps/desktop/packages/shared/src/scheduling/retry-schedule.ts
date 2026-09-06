import { normalizeDelay } from './clock';

export interface RetrySchedule {
  /**
   * Zero is the delay before the first retry.
   * `undefined` means retries are exhausted.
   */
  delayFor(retryIndex: number): number | undefined;
}

export type JitterOptions = {
  ratio?: number;
  random?: () => number;
};

export const retrySchedules = {
  never(): RetrySchedule {
    return { delayFor: () => undefined };
  },

  fixed(delayMs: number, maxRetries: number): RetrySchedule {
    return {
      delayFor(retryIndex) {
        return retryIndex < maxRetries ? normalizeDelay(delayMs) : undefined;
      },
    };
  },

  sequence(delaysMs: readonly number[], options: { repeatLast?: boolean } = {}): RetrySchedule {
    return {
      delayFor(retryIndex) {
        if (retryIndex < delaysMs.length) return normalizeDelay(delaysMs[retryIndex] ?? 0);
        if (options.repeatLast && delaysMs.length > 0) {
          return normalizeDelay(delaysMs[delaysMs.length - 1] ?? 0);
        }
        return undefined;
      },
    };
  },

  exponential(options: {
    initialMs: number;
    factor?: number;
    maxMs?: number;
    maxRetries?: number;
  }): RetrySchedule {
    const factor = options.factor ?? 2;
    const maxMs = options.maxMs ?? Number.POSITIVE_INFINITY;
    const maxRetries = options.maxRetries ?? Number.POSITIVE_INFINITY;
    return {
      delayFor(retryIndex) {
        if (retryIndex >= maxRetries) return undefined;
        const exponent = Math.min(retryIndex, 52);
        return normalizeDelay(Math.min(maxMs, options.initialMs * factor ** exponent));
      },
    };
  },

  limit(maxRetries: number, schedule: RetrySchedule): RetrySchedule {
    return {
      delayFor(retryIndex) {
        if (retryIndex >= maxRetries) return undefined;
        return schedule.delayFor(retryIndex);
      },
    };
  },

  jitter(schedule: RetrySchedule, options: JitterOptions = {}): RetrySchedule {
    const ratio = options.ratio ?? 0.2;
    const random = options.random ?? Math.random;
    return {
      delayFor(retryIndex) {
        const delay = schedule.delayFor(retryIndex);
        if (delay === undefined || delay <= 0) return delay;
        const min = Math.max(0, 1 - ratio);
        const max = 1 + ratio;
        return normalizeDelay(delay * (min + random() * (max - min)));
      },
    };
  },
};

export type RetryScheduleOptions = {
  /**
   * Delay before each retry, walked in order. With `repeatLast` the final
   * delay repeats forever; without it the schedule exhausts past the end.
   */
  delaysMs: readonly number[];
  /** Repeat the final delay indefinitely instead of exhausting the schedule. */
  repeatLast?: boolean;
  /** Cap on the number of retries; omit for no cap beyond the sequence itself. */
  maxRetries?: number;
  /** Randomize each delay; inject a deterministic `random` in tests. */
  jitter?: JitterOptions;
};

/**
 * Builds a {@link RetrySchedule} from a delay sequence — the one-stop
 * constructor beside the `retrySchedules` combinators. Callers with needs
 * beyond a sequence (e.g. exponential growth) can compose `retrySchedules`
 * directly — the result is the same vocabulary.
 */
export function retrySchedule(options: RetryScheduleOptions): RetrySchedule {
  let schedule = retrySchedules.sequence(options.delaysMs, { repeatLast: options.repeatLast });
  if (options.maxRetries !== undefined) {
    schedule = retrySchedules.limit(options.maxRetries, schedule);
  }
  if (options.jitter) schedule = retrySchedules.jitter(schedule, options.jitter);
  return schedule;
}
