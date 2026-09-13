# Live Jobs

Live jobs model async work as a live state machine. They are useful when callers
need both a final result and a stream of progress updates.

## State Shape

`liveJobStateSchema(progress, result, error)` creates a schema for:

```ts
type LiveJobState<P, R, E> =
  | { status: 'running'; startedAt: number; progress: P[]; progressCount: number }
  | { status: 'succeeded'; startedAt: number; finishedAt: number; progress: P[]; result: R }
  | { status: 'failed'; startedAt: number; finishedAt: number; progress: P[]; error?: E; cause?: SerializedError }
  | { status: 'cancelled'; startedAt: number; finishedAt: number; progress: P[] };
```

`progress` is a retained ring of recent entries. `progressCount` is the total
number of progress events emitted, including entries that may have rolled out of
the retained ring. Terminal states retain lifecycle timestamps and the most
recent progress entries, but they do not carry `progressCount`.

## Server

`LiveJobSource<I, P, R, E>` accepts a handler that returns `Result<R, E>`:

```ts
const jobs = new LiveJobSource<Input, Progress, Result, ErrorState>(
  async (input, ctx) => {
    ctx.progress({ step: 'checkout' });
    await build(input, ctx.signal);
    ctx.progress({ step: 'package' });
    return ok({ artifact: `${input.target}.zip` });
  },
  { toError: (error) => ({ message: error instanceof Error ? error.message : String(error) }) }
);

const { jobId } = jobs.start({ target: 'desktop' });
```

Options:

- `generation`: optional fixed generation for every job state model.
- `terminalRetainMs`: how long terminal state remains attachable. Default:
  `LIVE_JOB_TERMINAL_RETAIN_MS` (5 minutes).
- `idFactory`: custom job id factory, useful for deterministic tests.
- `clock`: custom timestamp source, useful for deterministic tests.
- `toError`: optional fallback for unexpected thrown errors. Domain failures
  should be returned as `err(error)` from the handler.
- `onRunStarted`, `onRunChanged`, and `onRunEvicted`: optional hooks for callers
  that want to maintain their own job listing.

Handlers receive `LiveJobContext`:

- `ctx.progress(value)` appends retained progress and emits an update.
- `ctx.signal` is an `AbortSignal`. If the signal is aborted, the job finishes
  as `cancelled`.

Return `ok(result)` for successful completion and `err(error)` for expected
domain failures. If the handler throws and `toError` is configured, the thrown
value is mapped into typed `error`; otherwise the failed state carries a
serialized `cause`.

`source(jobId)` returns a read-only live source for that job. `snapshot(jobId)` and
`getState(jobId)` are convenience accessors. `cancel(id)` aborts a running job.
`dispose()` is async: it aborts running jobs, waits for cooperative handlers to
settle, clears eviction timers, and removes all job state.

Terminal job state is retained for `LIVE_JOB_TERMINAL_RETAIN_MS` (5 minutes) so
late clients can reattach by id. This retention is process-local, not durable.

## Consumers

Consumers normally reach jobs through the API layer. The contract client starts,
cancels, and attaches to jobs without retaining local state:

```ts
const { jobId } = await contractClient.build.start({ target: 'desktop' });
const handle = contractClient.build.handle(jobId);

const detach = await handle.attach((update) => {
  console.log(update.delta);
});

await contractClient.build.cancel(jobId);
detach();
```

Use `createLiveJobReplicaCache()` when a consumer wants a `result` promise, progress
callbacks, ref-counted attachment, and terminal-state retention. If the job fails,
`ReplicaJob.result` rejects with `LiveJobFailedError`; if it is cancelled, it
rejects with `LiveJobCancelledError`. Progress emitted by a seed is suppressed so
reattaching clients do not replay old progress as fresh events.

## Contract Endpoint

The API contract layer can expose a job directly:

```ts
const api = defineContract({
  build: liveJob({
    input: z.object({ target: z.string() }),
    progress: z.object({ step: z.string() }),
    result: z.object({ artifact: z.string() }),
    error: z.object({ message: z.string() }),
  }),
});
```

On the server, implement the endpoint with `{ run, toError? }`:

```ts
const controller = createController(api, {
  build: {
    run: async (input, ctx) => {
      ctx.progress({ step: 'compile' });
      return ok({ artifact: `${input.target}.zip` });
    },
    toError: (error) => ({
      message: error instanceof Error ? error.message : String(error),
    }),
  },
});
```

The typed client exposes a live job client handle. Use it directly for
low-level forwarding, or wrap it in `createLiveJobReplicaCache()` when a consumer wants
ref-counted local state:

```ts
const jobs = createLiveJobReplicaCache(api.build, contractClient.build, { lingerMs: 30_000 });
const lease = await jobs.start({ target: 'desktop' });
const handle = await lease.ready();

handle.onProgress((progress) => console.log(progress.step));
console.log(await handle.result);

await lease.release();

const reattachedLease = jobs.acquire(handle.jobId);
const reattached = await reattachedLease.ready();
console.log(await reattached.result);
await reattachedLease.release();
await jobs.dispose();
```

`ReplicaJob` exposes `jobId`, `ready`, `result`, `getState()`,
`onProgress(cb)`, and `cancel()`. The `LiveJobReplicaCache` manager owns ref counting,
subscription sharing, and terminal-state retention.

`LiveJobSource` accepts a `Clock` for deterministic start/finish timestamps and
terminal retention eviction. Server disposal is awaitable: it cancels active job
runs, waits for cooperative handlers to settle, and disposes retention timers
before returning.

Cancellation at the procedure/wire level is documented in
[serving](../api/serving.md#cancellation). Job cancellation is domain-level:
`ReplicaJob.cancel()` calls the generated `<path>.cancel` procedure, which calls
`LiveJobSource.cancel(jobId)`.

See [../../examples/job-contract/client.ts](../../examples/job-contract/client.ts).
