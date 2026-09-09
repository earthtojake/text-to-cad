import { describe, expect, it, vi } from 'vitest';
import { ManualClock } from '../testing';
import { retry } from './retry';
import { retrySchedules } from './retry-schedule';

describe('retry', () => {
  it('retries retryable failures after scheduled delays', async () => {
    const clock = new ManualClock();
    const operation = vi.fn(async ({ attempt }: { attempt: number }) => {
      if (attempt === 0) throw new Error('first');
      return 'ok';
    });

    const result = retry(({ attempt }) => operation({ attempt }), {
      clock,
      schedule: retrySchedules.fixed(10, 1),
      shouldRetry: () => true,
    });

    await Promise.resolve();
    expect(operation).toHaveBeenCalledTimes(1);
    await clock.advanceBy(10);

    await expect(result).resolves.toBe('ok');
    expect(operation).toHaveBeenNthCalledWith(2, { attempt: 1 });
  });
});
