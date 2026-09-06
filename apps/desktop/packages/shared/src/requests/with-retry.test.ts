import { describe, expect, it, vi } from 'vitest';
import { retrySchedules, TimeoutError } from '../scheduling';
import { ManualClock } from '../testing';
import { compose } from './compose';
import { withRetry } from './with-retry';
import { withTimeout } from './with-timeout';

describe('withRetry', () => {
  it('retries classified handler failures', async () => {
    const clock = new ManualClock();
    const spy = vi.fn();
    const handler = async (_input: undefined, _context: { signal?: AbortSignal }) => {
      spy();
      if (spy.mock.calls.length === 1) throw new Error('retry');
      return 'ok';
    };
    const composed = compose(handler, [
      withRetry({
        clock,
        schedule: retrySchedules.fixed(5, 1),
        shouldRetry: (error) => error instanceof Error && error.message === 'retry',
      }),
    ]);

    const result = composed(undefined, {});
    await Promise.resolve();
    await Promise.resolve();
    expect(spy).toHaveBeenCalledTimes(1);
    await clock.advanceBy(5);

    await expect(result).resolves.toBe('ok');
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('does not retry rejected classifications', async () => {
    const spy = vi.fn();
    const handler = async (_input: undefined, _context: { signal?: AbortSignal }) => {
      spy();
      throw new Error('fatal');
    };
    const composed = compose(handler, [
      withRetry({
        schedule: retrySchedules.fixed(0, 1),
        shouldRetry: () => false,
      }),
    ]);

    await expect(composed(undefined, {})).rejects.toThrow('fatal');
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('supports per-attempt and total timeout ordering', async () => {
    const clock = new ManualClock();
    const spy = vi.fn();
    const handler = async (_input: undefined, context: { signal?: AbortSignal }) => {
      spy();
      await new Promise<never>((_resolve, reject) => {
        context.signal?.addEventListener('abort', () => reject(context.signal?.reason), {
          once: true,
        });
      });
    };
    const composed = compose(handler, [
      withTimeout({ timeoutMs: 20, clock }),
      withRetry({
        clock,
        schedule: retrySchedules.fixed(1, 2),
        shouldRetry: () => true,
      }),
      withTimeout({ timeoutMs: 5, clock }),
    ]);

    const result = composed(undefined, {});
    await Promise.resolve();
    await clock.advanceBy(5);
    await clock.advanceBy(1);
    await clock.advanceBy(5);
    await clock.advanceBy(1);
    await clock.advanceBy(5);

    await expect(result).rejects.toBeInstanceOf(TimeoutError);
    expect(spy).toHaveBeenCalledTimes(3);
  });
});
