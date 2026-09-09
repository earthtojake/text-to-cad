import { describe, expect, it, vi } from 'vitest';
import { createManualClock } from '../testing/manual-clock';
import { createDebounced } from './debounce';

describe('createDebounced', () => {
  describe('trailing edge (default)', () => {
    it('coalesces a burst into one trailing call with the final value', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, clock });

      debounced.call(1);
      debounced.call(2);
      debounced.call(3);
      expect(fn).not.toHaveBeenCalled();

      await clock.advanceBy(60);
      expect(fn.mock.calls.map((c) => c[0])).toEqual([3]);
    });

    it('restarts the window on every call within a burst', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, clock });

      debounced.call(1);
      await clock.advanceBy(30);
      debounced.call(2);
      await clock.advanceBy(30);
      expect(fn).not.toHaveBeenCalled();

      await clock.advanceBy(30);
      expect(fn.mock.calls.map((c) => c[0])).toEqual([2]);
    });

    it('treats separated calls as separate flushes', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, clock });

      debounced.call(1);
      await clock.advanceBy(60);
      debounced.call(2);
      await clock.advanceBy(60);
      expect(fn.mock.calls.map((c) => c[0])).toEqual([1, 2]);
    });

    it('supports void payloads', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<void>(fn, { delayMs: 10, clock });

      debounced.call();
      debounced.call();
      await clock.advanceBy(10);
      expect(fn).toHaveBeenCalledTimes(1);
    });
  });

  describe('leading edge (opt-in)', () => {
    it('flushes immediately on the leading edge and captures the final value on the trailing edge', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, leading: true, clock });

      debounced.call(1); // leading -> fn(1)
      debounced.call(2); // within burst -> coalesced
      debounced.call(3); // within burst -> coalesced
      expect(fn.mock.calls.map((c) => c[0])).toEqual([1]);

      await clock.advanceBy(60);
      expect(fn.mock.calls.map((c) => c[0])).toEqual([1, 3]);
    });

    it('flushes a lone call exactly once (leading consumes the pending value)', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, leading: true, clock });

      debounced.call(1);
      expect(fn).toHaveBeenCalledTimes(1);

      await clock.advanceBy(120);
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('treats a call after a full quiet window as a new leading edge', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, leading: true, clock });

      debounced.call(1); // leading
      await clock.advanceBy(60);
      debounced.call(2); // new burst -> leading again
      expect(fn.mock.calls.map((c) => c[0])).toEqual([1, 2]);
    });

    it('coalesces a call arriving within the cooldown after a trailing flush', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, leading: true, clock });

      debounced.call(1); // leading -> fn(1)
      debounced.call(2); // trailing pending
      await clock.advanceBy(60); // trailing -> fn(2)
      debounced.call(3); // within cooldown -> coalesced, not leading
      expect(fn.mock.calls.map((c) => c[0])).toEqual([1, 2]);

      await clock.advanceBy(60);
      expect(fn.mock.calls.map((c) => c[0])).toEqual([1, 2, 3]);
    });
  });

  describe('cancel', () => {
    it('drops pending work and never fires afterwards', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, clock });

      debounced.call(1);
      debounced.cancel();
      await clock.advanceBy(240);
      expect(fn).not.toHaveBeenCalled();
    });

    it('drops a pending trailing flush after a leading flush', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, leading: true, clock });

      debounced.call(1); // leading -> fn(1)
      debounced.call(2); // trailing pending
      debounced.cancel();
      await clock.advanceBy(240);
      expect(fn.mock.calls.map((c) => c[0])).toEqual([1]);
    });

    it('is idempotent and leaves the handle usable', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, clock });

      debounced.cancel();
      debounced.cancel();
      debounced.call(1);
      await clock.advanceBy(60);
      expect(fn.mock.calls.map((c) => c[0])).toEqual([1]);
    });
  });

  describe('flush', () => {
    it('invokes pending work immediately and clears the timer', async () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, clock });

      debounced.call(1);
      debounced.flush();
      expect(fn.mock.calls.map((c) => c[0])).toEqual([1]);

      await clock.advanceBy(120);
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('does nothing when no work is pending', () => {
      const clock = createManualClock();
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 60, clock });

      debounced.flush();
      expect(fn).not.toHaveBeenCalled();
    });
  });

  it('reports whether a trailing flush is pending', async () => {
    const clock = createManualClock();
    const fn = vi.fn();
    const debounced = createDebounced<number>(fn, { delayMs: 60, clock });

    expect(debounced.pending).toBe(false);
    debounced.call(1);
    expect(debounced.pending).toBe(true);
    await clock.advanceBy(60);
    expect(debounced.pending).toBe(false);
  });

  it('defaults to the system clock', async () => {
    vi.useFakeTimers();
    try {
      const fn = vi.fn();
      const debounced = createDebounced<number>(fn, { delayMs: 20 });
      debounced.call(7);
      expect(fn).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(20);
      expect(fn.mock.calls.map((c) => c[0])).toEqual([7]);
    } finally {
      vi.useRealTimers();
    }
  });
});
