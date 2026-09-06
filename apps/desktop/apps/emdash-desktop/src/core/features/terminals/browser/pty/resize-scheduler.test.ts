import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createResizeScheduler } from './resize-scheduler';

// Regression guard for ENG-1577: the PTY resize must fire on the LEADING edge
// (in lockstep with the synchronous xterm grid resize), not deferred behind a
// pure trailing debounce — otherwise the child TUI draws against stale
// dimensions and overlaps its output with the input line.

describe('createResizeScheduler', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('flushes synchronously on the leading edge (single resize)', () => {
    const flush = vi.fn();
    const s = createResizeScheduler<number>(flush, 60);
    s.schedule(1);
    // The fix: value is delivered immediately, before any timer elapses.
    expect(flush).toHaveBeenCalledTimes(1);
    expect(flush).toHaveBeenLastCalledWith(1);
  });

  it('does not flush again on the trailing edge when nothing else was scheduled', () => {
    const flush = vi.fn();
    const s = createResizeScheduler<number>(flush, 60);
    s.schedule(1);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(60);
    // Leading flush consumed the value; the lone resize flushes exactly once.
    expect(flush).toHaveBeenCalledTimes(1);
  });

  it('coalesces a burst: leading first value + trailing final value', () => {
    const flush = vi.fn();
    const s = createResizeScheduler<number>(flush, 60);
    s.schedule(1); // leading -> flush(1)
    s.schedule(2); // within burst -> coalesced
    s.schedule(3); // within burst -> coalesced
    expect(flush.mock.calls.map((c) => c[0])).toEqual([1]);
    vi.advanceTimersByTime(60); // trailing -> flush(3)
    expect(flush.mock.calls.map((c) => c[0])).toEqual([1, 3]);
  });

  it('treats a resize after the trailing window as a new leading edge', () => {
    const flush = vi.fn();
    const s = createResizeScheduler<number>(flush, 60);
    s.schedule(1); // leading
    vi.advanceTimersByTime(60); // trailing window closes (no pending)
    s.schedule(2); // new burst -> leading flush again
    expect(flush.mock.calls.map((c) => c[0])).toEqual([1, 2]);
  });

  it('cancel() drops a pending trailing flush', () => {
    const flush = vi.fn();
    const s = createResizeScheduler<number>(flush, 60);
    s.schedule(1); // leading flush(1)
    s.schedule(2); // pending trailing = 2
    s.cancel();
    vi.advanceTimersByTime(120);
    expect(flush.mock.calls.map((c) => c[0])).toEqual([1]); // trailing(2) never fired
  });
});
