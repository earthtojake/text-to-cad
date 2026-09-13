import { describe, expect, it } from 'vitest';
import { TimeoutError } from '../scheduling';
import { ManualClock, deferred } from '../testing';
import { compose } from './compose';
import { withTimeout } from './with-timeout';

describe('withTimeout', () => {
  it('preserves context and aborts the derived signal', async () => {
    const clock = new ManualClock();
    const started = deferred<void>();
    let aborted = false;
    const handler = async (
      _input: { id: string },
      context: { signal?: AbortSignal; traceId: string }
    ) => {
      expect(context.traceId).toBe('trace-1');
      context.signal?.addEventListener('abort', () => {
        aborted = true;
      });
      started.resolve();
      await new Promise<never>(() => {});
    };
    const composed = compose(handler, [withTimeout({ timeoutMs: 5, clock })]);

    const result = composed({ id: 'same' }, { traceId: 'trace-1' });
    await started.promise;
    await clock.advanceBy(5);

    await expect(result).rejects.toBeInstanceOf(TimeoutError);
    expect(aborted).toBe(true);
  });

  it('preserves caller cancellation', async () => {
    const clock = new ManualClock();
    const abort = new AbortController();
    const reason = new Error('caller stopped');
    const started = deferred<void>();
    const handler = async (_input: undefined, context: { signal?: AbortSignal }) => {
      started.resolve();
      await new Promise<never>((_resolve, reject) => {
        context.signal?.addEventListener('abort', () => reject(context.signal?.reason), {
          once: true,
        });
      });
    };
    const composed = compose(handler, [withTimeout({ timeoutMs: 5, clock })]);

    const result = composed(undefined, { signal: abort.signal });
    await started.promise;
    abort.abort(reason);

    await expect(result).rejects.toBe(reason);
  });
});
