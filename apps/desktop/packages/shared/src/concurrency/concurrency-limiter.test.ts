import { describe, expect, it, vi } from 'vitest';
import { deferred } from '../testing';
import { createConcurrencyLimiter } from './concurrency-limiter';

describe('ConcurrencyLimiter', () => {
  it('queues excess operations in FIFO order', async () => {
    const limiter = createConcurrencyLimiter(1);
    const releaseFirst = deferred<void>();
    const started: string[] = [];
    const signal = new AbortController().signal;
    const first = limiter.run(signal, async () => {
      started.push('first');
      await releaseFirst.promise;
      return 1;
    });
    const second = limiter.run(signal, async () => {
      started.push('second');
      return 2;
    });

    await vi.waitFor(() => expect(started).toEqual(['first']));
    releaseFirst.resolve();
    await expect(Promise.all([first, second])).resolves.toEqual([1, 2]);
    expect(started).toEqual(['first', 'second']);
  });

  it('removes an aborted waiter without consuming capacity', async () => {
    const limiter = createConcurrencyLimiter(1);
    const releaseFirst = deferred<void>();
    const first = limiter.run(new AbortController().signal, async () => {
      await releaseFirst.promise;
    });
    const waiting = new AbortController();
    const cancelled = limiter.run(waiting.signal, async () => 'cancelled operation ran');
    waiting.abort(new Error('cancel queued operation'));

    await expect(cancelled).rejects.toThrow('cancel queued operation');
    releaseFirst.resolve();
    await first;
    await expect(limiter.run(new AbortController().signal, async () => 'next')).resolves.toBe(
      'next'
    );
  });
});
