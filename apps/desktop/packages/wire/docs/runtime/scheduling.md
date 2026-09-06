# Scheduling

`@emdash/shared/scheduling` centralizes time, retry, and
cancellation-sensitive waits. Wire uses these Shared primitives, and runtime
code should depend on `Clock` instead of calling platform timer APIs directly.

```ts
import { retry, retrySchedules, systemClock } from '@emdash/shared/scheduling';

await retry(
  () => transport.connect(),
  {
    clock: systemClock,
    schedule: retrySchedules.exponential({ initialMs: 100, maxMs: 2_000 }),
    shouldRetry: (error) => isTransient(error),
  }
);
```

## Clock

`Clock` has three operations:

- `now()` returns wall-clock milliseconds for diagnostics and deadlines.
- `schedule(delayMs, callback)` returns a disposable `TimerHandle`.
- `sleep(delayMs, { signal })` returns an abortable promise.

Use `Clock` for sleeps, backoff, debounce, retention, idle TTLs, readiness
deadlines, and test polling. Keep direct `Date.now()` or `performance.now()` for
protocol timestamps, generated IDs, and duration measurement where the wall clock
or monotonic timer is the data being recorded.

## TimerHandle Ownership

Every scheduled callback must have one owner. Register the handle with a `Scope`,
store it on the owning entry, or dispose it in all terminal paths:

```ts
const handle = clock.schedule(5_000, () => expire(id), { unref: true });
scope.add(() => handle.dispose());
```

`TimerHandle.dispose()` is idempotent. The `active` flag becomes false before the
callback runs, so callback and disposal races remain at-most-once.

## Timeouts

`runWithTimeout(work, { timeoutMs, signal, clock })` derives a child
`AbortSignal`, schedules a deadline on the provided `Clock`, and disposes its
timer in every terminal path. The returned promise rejects with `TimeoutError`
when the deadline expires, but parent cancellation still rejects with the
parent's abort reason.

```ts
const result = await runWithTimeout(
  (signal) => loadWorkspace({ signal }),
  { timeoutMs: 5_000, signal: parentSignal, clock }
);
```

The timeout rejects promptly even when work ignores the derived signal, but the
underlying JavaScript work can only stop cooperatively. Pass the derived signal
into sleeps, process waits, transports, and any helper that can observe
cancellation.

## ManualClock

Tests should import `ManualClock` from `@emdash/shared/testing`. It preserves FIFO
ordering for timers with the same deadline and flushes resumed promise
microtasks while advancing:

```ts
const clock = new ManualClock(1_000);
const done = clock.sleep(250);

await clock.advanceBy(250);
await done;
```

Use `runAll({ maxTimers })` only when the test expects the scheduled work to
drain. The guard prevents accidental infinite timer loops.

## Retry Semantics

`RetrySchedule.delayFor(0)` is the delay before the first retry. Attempt `0` is
the initial operation call, attempt `1` is the first retry, and so on.
`undefined` means retries are exhausted.

Schedules are stateless and composable: fixed, finite sequence, repeat-last
sequence, exponential, limited, and deterministic jitter. Inject a deterministic
random function into jittered schedules in tests.

`retry()` is exception-based. Domain errors that are expected API results should
remain `Result<T, E>` values; use `shouldRetry` to classify thrown transport or
runtime failures.

## Wire Retry Vocabulary

Wire expresses all retry timing through one schedule vocabulary:
`RetrySchedule` and the `retrySchedule()` constructor from
`@emdash/shared/scheduling`. The reconnecting transport's reconnect delays,
worker-slot supervision, the follower's `resyncRetry` policy, and per-call
opt-in retries all consume it. Shared vocabulary, not shared state — each site
keeps its own independently tunable schedule:

```ts
import { retrySchedule } from '@emdash/shared/scheduling';

const supervision = {
  restart: 'on-failure',
  schedule: retrySchedule({ delaysMs: [250, 1_000, 2_500], repeatLast: true, maxRetries: 5 }),
};
```

## Periodic Work

Prefer abortable loops or chained one-shot timers over overlapping intervals.
That keeps disposal ordered and avoids installing work after an owner has begun
closing:

```ts
scope.run('poll', async (signal) => {
  while (!signal.aborted) {
    await refresh({ signal });
    await clock.sleep(1_000, { signal });
  }
});
```
