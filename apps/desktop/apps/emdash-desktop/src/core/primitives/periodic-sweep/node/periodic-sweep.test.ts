import { createScope } from '@emdash/shared/concurrency';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { startPeriodicSweep } from './periodic-sweep';

describe('startPeriodicSweep', () => {
  afterEach(() => vi.useRealTimers());

  it('runs on demand and periodically until its scope is disposed', async () => {
    vi.useFakeTimers();
    const scope = createScope({ label: 'periodic-sweep-test' });
    const run = vi.fn(async () => undefined);
    const sweep = startPeriodicSweep({
      scope,
      intervalMs: 100,
      run,
      onError: vi.fn(),
    });

    await sweep.runNow();
    await vi.advanceTimersByTimeAsync(100);
    expect(run).toHaveBeenCalledTimes(2);

    await scope.dispose();
    await vi.advanceTimersByTimeAsync(100);
    expect(run).toHaveBeenCalledTimes(2);
  });
});
