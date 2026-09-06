import { systemClock, type Clock } from '../scheduling';

export type WaitForOptions = {
  timeoutMs?: number;
  intervalMs?: number;
  clock?: Clock;
  signal?: AbortSignal;
  message?: string;
};

export async function waitFor(
  predicate: () => boolean | Promise<boolean>,
  options: WaitForOptions = {}
): Promise<void> {
  const timeoutMs = options.timeoutMs ?? 1000;
  const intervalMs = options.intervalMs ?? 1;
  const clock = options.clock ?? systemClock;
  const startedAt = clock.now();

  while (clock.now() - startedAt <= timeoutMs) {
    if (options.signal?.aborted) throw options.signal.reason ?? new Error('waitFor aborted');
    if (await predicate()) return;
    await clock.sleep(intervalMs, { signal: options.signal });
  }

  throw new Error(options.message ?? `Timed out waiting for condition after ${timeoutMs}ms`);
}
