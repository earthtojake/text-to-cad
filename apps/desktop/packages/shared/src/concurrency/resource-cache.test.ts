import { describe, expect, it, vi } from 'vitest';
import { createManualClock } from '../testing';
import { acquireResourceAsResult, createResourceCache } from './resource-cache';
import type { Scope } from './scope';

describe('createResourceCache', () => {
  it('shares one in-flight creation for the same key', async () => {
    const cleanup = vi.fn();
    const create = vi.fn(async (key: string, scope: Scope) => {
      scope.add(cleanup);
      return { key };
    });
    const cache = createResourceCache({ key: (key: string) => key, create });

    const first = cache.acquire('same');
    const second = cache.acquire('same');
    const firstValue = await first.ready();
    const secondValue = await second.ready();

    expect(create).toHaveBeenCalledTimes(1);
    expect(secondValue).toBe(firstValue);
    await first.release();
    expect(cleanup).not.toHaveBeenCalled();
    await second.release();
    expect(cleanup).toHaveBeenCalledTimes(1);
  });

  it('registers the idle-timer cleanup once per entry regardless of release cycles', async () => {
    const clock = createManualClock();
    // Counts scope.add() calls made after entry creation; the idle-timer cleanup
    // must be registered once at creation, not once per release cycle.
    let addCallsAfterCreate = 0;
    const cache = createResourceCache({
      key: (key: string) => key,
      idleTtlMs: 1_000,
      clock,
      create: (key: string, scope: Scope) => {
        const originalAdd = scope.add.bind(scope);
        (scope as { add: Scope['add'] }).add = (cleanup) => {
          addCallsAfterCreate += 1;
          originalAdd(cleanup);
        };
        return { key };
      },
    });

    for (let cycle = 0; cycle < 5; cycle += 1) {
      const lease = cache.acquire('same');
      await lease.ready();
      await lease.release();
      await clock.advanceBy(500);
    }

    expect(addCallsAfterCreate).toBe(0);
    expect(cache.peek('same')).toBeDefined();

    // The entry still disposes when the idle window finally elapses.
    await clock.advanceBy(1_000);
    await vi.waitFor(() => expect(cache.peek('same')).toBeUndefined());

    await cache.dispose();
  });

  it('maps expected acquire errors to err results', async () => {
    const expected = { type: 'test-error', message: 'boom' } as const;
    const cache = createResourceCache({
      key: (key: string) => key,
      create: async () => {
        throw expected;
      },
    });

    const result = await acquireResourceAsResult(cache, 'same', isTestError);

    expect(result.success).toBe(false);
    if (result.success) return;
    expect(result.error).toBe(expected);
  });
});

type TestError = { type: 'test-error'; message: string };

function isTestError(error: unknown): error is TestError {
  return (
    typeof error === 'object' &&
    error !== null &&
    (error as { type?: unknown }).type === 'test-error'
  );
}
