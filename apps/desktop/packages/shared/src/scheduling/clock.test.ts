import { describe, expect, it, vi } from 'vitest';
import { abortReason, throwIfAborted } from './abortable-wait';
import { systemClock, waitWithSignal } from './clock';

describe('systemClock', () => {
  it('cancels scheduled callbacks through timer handles', async () => {
    vi.useFakeTimers();
    const callback = vi.fn();
    const handle = systemClock.schedule(1, callback);

    expect(handle.active).toBe(true);
    handle.dispose();
    expect(handle.active).toBe(false);

    await vi.advanceTimersByTimeAsync(5);
    expect(callback).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('rejects sleep when aborted', async () => {
    const abort = new AbortController();
    const sleep = systemClock.sleep(10_000, { signal: abort.signal });

    abort.abort(new Error('stop'));

    await expect(sleep).rejects.toThrow('stop');
  });

  it('uses a caller fallback when an abort signal has no explicit reason', () => {
    const signal = { aborted: true, reason: undefined } as AbortSignal;
    const nonErrorReason = { aborted: true, reason: 'cancelled' } as AbortSignal;

    expect(() => throwIfAborted(signal, 'operation cancelled')).toThrow('operation cancelled');
    expect(abortReason(signal, 'operation cancelled')).toEqual(new Error('operation cancelled'));
    expect(abortReason(nonErrorReason)).toBe('cancelled');
    expect(abortReason(nonErrorReason, 'operation cancelled')).toEqual(
      new Error('operation cancelled')
    );
  });

  it('settles a promise from the first of completion or cancellation', async () => {
    const completed = Promise.resolve('done');
    await expect(waitWithSignal(completed, new AbortController().signal)).resolves.toBe('done');

    const abort = new AbortController();
    const pending = waitWithSignal(new Promise<never>(() => {}), abort.signal, 'wait cancelled');
    abort.abort();
    await expect(pending).rejects.toThrow('This operation was aborted');
  });
});
