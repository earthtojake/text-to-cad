import { describe, expect, it } from 'vitest';
import { ManualClock } from '../testing';
import { createTokenBucketGate } from './rate-gate';

describe('createTokenBucketGate', () => {
  it('allows a burst up to capacity and refills over time', async () => {
    const clock = new ManualClock();
    const gate = createTokenBucketGate({ capacity: 2, refillPerSec: 1, clock });
    const signal = new AbortController().signal;

    await gate.acquire(1, signal);
    await gate.acquire(1, signal);
    let acquired = false;
    const third = gate.acquire(1, signal).then(() => {
      acquired = true;
    });

    await Promise.resolve();
    expect(acquired).toBe(false);
    await clock.advanceBy(999);
    expect(acquired).toBe(false);
    await clock.advanceBy(1);
    await expect(third).resolves.toBeUndefined();
  });

  it('pauses until retry-after expires', async () => {
    const clock = new ManualClock(1_000);
    const gate = createTokenBucketGate({ capacity: 10, refillPerSec: 10, clock });
    gate.observe({ retryAfterMs: 5_000 });
    let acquired = false;
    const pending = gate.acquire(1, new AbortController().signal).then(() => {
      acquired = true;
    });

    await clock.advanceBy(4_999);
    expect(acquired).toBe(false);
    await clock.advanceBy(1);
    await expect(pending).resolves.toBeUndefined();
  });

  it('applies server pauses to zero-cost scheduling checks', async () => {
    const clock = new ManualClock();
    const gate = createTokenBucketGate({ capacity: 10, refillPerSec: 10, clock });
    gate.observe({ retryAfterMs: 1_000 });
    let acquired = false;
    const pending = gate.acquire(0, new AbortController().signal).then(() => {
      acquired = true;
    });

    await clock.advanceBy(999);
    expect(acquired).toBe(false);
    await clock.advanceBy(1);
    await expect(pending).resolves.toBeUndefined();
  });

  it('reserves reported server budget until reset', async () => {
    const clock = new ManualClock(1_000);
    const gate = createTokenBucketGate({
      capacity: 10,
      refillPerSec: 10,
      reserve: 2,
      clock,
    });
    gate.observe({ remaining: 2, resetAtMs: 6_000 });
    let acquired = false;
    const pending = gate.acquire(1, new AbortController().signal).then(() => {
      acquired = true;
    });

    await clock.advanceBy(4_999);
    expect(acquired).toBe(false);
    await clock.advanceBy(1);
    await expect(pending).resolves.toBeUndefined();
  });

  it('does not let stale feedback increase the current server budget', async () => {
    const clock = new ManualClock();
    const gate = createTokenBucketGate({
      capacity: 100,
      refillPerSec: 100,
      reserve: 5,
      clock,
    });
    gate.observe({ remaining: 6, resetAtMs: 10_000 });
    gate.observe({ remaining: 50, resetAtMs: 10_000 });
    let acquired = false;
    const pending = gate.acquire(2, new AbortController().signal).then(() => {
      acquired = true;
    });

    await clock.advanceBy(9_999);
    expect(acquired).toBe(false);
    await clock.advanceBy(1);
    await expect(pending).resolves.toBeUndefined();
  });

  it('accounts for observed request cost in the local bucket', async () => {
    const clock = new ManualClock();
    const gate = createTokenBucketGate({ capacity: 5, refillPerSec: 1, clock });
    await gate.acquire(0, new AbortController().signal);
    gate.observe({ cost: 5 });
    let acquired = false;
    const pending = gate.acquire(1, new AbortController().signal).then(() => {
      acquired = true;
    });

    await clock.advanceBy(999);
    expect(acquired).toBe(false);
    await clock.advanceBy(1);
    await expect(pending).resolves.toBeUndefined();
  });

  it('cancels while waiting', async () => {
    const clock = new ManualClock();
    const gate = createTokenBucketGate({ capacity: 1, refillPerSec: 1, clock });
    const abort = new AbortController();
    await gate.acquire(1, abort.signal);

    const pending = gate.acquire(1, abort.signal);
    abort.abort(new Error('cancelled'));

    await expect(pending).rejects.toThrow('cancelled');
  });

  it('validates configuration and costs', async () => {
    expect(() => createTokenBucketGate({ capacity: 0, refillPerSec: 1 })).toThrow('capacity');
    expect(() => createTokenBucketGate({ capacity: 1, refillPerSec: 0 })).toThrow('refill rate');
    const gate = createTokenBucketGate({ capacity: 1, refillPerSec: 1 });
    await expect(gate.acquire(-1, new AbortController().signal)).rejects.toThrow('cost');
  });
});
