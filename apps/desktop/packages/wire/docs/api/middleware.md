# Composable Middleware

Wire uses explicit composition for execution policy. Contracts describe protocol
shape; middleware wraps handlers or controllers at the composition site.

```ts
import { compose, deduplicate, withRetry, withTimeout } from '@emdash/shared/requests';
import { retrySchedules } from '@emdash/shared/scheduling';
import { createController } from '@emdash/wire/rpc';

const loadStats = compose(
  async (input: { repo: string }, meta: { signal?: AbortSignal }) => {
    return await fetchStats(input.repo, { signal: meta.signal });
  },
  [
    withTimeout({ timeoutMs: 20_000 }),
    withRetry({
      schedule: retrySchedules.exponential({
        initialMs: 250,
        maxMs: 2_000,
        maxRetries: 3,
      }),
      shouldRetry: isTransient,
    }),
    withTimeout({ timeoutMs: 5_000 }),
  ]
);

const controller = createController(api, { loadStats });
```

## `compose()`

`compose(target, middlewares)` accepts the value being wrapped first and a
readonly middleware array second:

```ts
type Middleware<T> = (next: T) => T;
```

The first array entry is outermost. It sees the request first and settles last:

```mermaid
flowchart LR
  composeCall["compose(handler, middlewares)"] --> totalTimeout[TotalTimeout]
  totalTimeout --> retry[Retry]
  retry --> attemptTimeout[AttemptTimeout]
  attemptTimeout --> handler[RawHandler]
```

This order makes policy boundaries explicit. In the first example, the outer
timeout bounds the complete retry program, while the inner timeout bounds each
individual attempt.

## Handler Middleware

Handler middleware wraps procedure implementations before `createController()`:

```ts
const handler = compose(rawHandler, [
  withTimeout({ timeoutMs: 10_000 }),
  deduplicate({ key: (input) => input.repo }),
]);
```

Use handler middleware for endpoint-specific execution policy:

- Timeout and deadline policy.
- Retry policy for idempotent or externally safe operations.
- In-flight request deduplication.
- Per-endpoint rate limiting or concurrency limits when those utilities exist.

Procedure handlers receive `(input, meta)`. Middleware must preserve every field
on `meta` and replace only `meta.signal` when it needs derived cancellation:

```ts
const wrapped = async (input, meta) => {
  return await next(input, { ...meta, signal: derivedSignal });
};
```

Middleware functions are intentionally not contract annotations. Two endpoints can
share the same schema and still have different execution policy depending on
where they are served.

## Controller Middleware

Controller middleware wraps a complete `Controller` and satisfies
`Middleware<Controller>` from `@emdash/shared/requests`. The seam exists as the
sanctioned extension point for future cross-cutting concerns (for example
observability), even though Wire ships no controller middleware today.

Contract validation is not middleware: it is a `createController()` option.
Every controller validates by default — `'full'` (inputs + outputs) outside
production, `'inputs'` in production — with an explicit `validate` override:

```ts
const controller = createController(api, impl, { validate: 'inputs' });
```

Use controller middleware for boundary-wide behavior:

- Logging and request instrumentation.
- Session or authorization checks that apply to every procedure on the served
  controller.

Prefer handler middleware when the policy belongs to one endpoint. Prefer
controller middleware when the policy belongs to the served boundary.

## Timeout

`withTimeout({ timeoutMs, clock? })` from `@emdash/shared/requests` is handler
middleware backed by Shared `runWithTimeout()` from `@emdash/shared/scheduling`.
It derives a child `AbortSignal`, passes that signal to the wrapped handler, and
converts an expired deadline to a timeout error.

```ts
const startSession = compose(rawStartSession, [
  withTimeout({ timeoutMs: 10_000, clock }),
]);
```

Timeout is infrastructure failure, not a domain result. If callers should handle
a timeout as expected data, model it in the endpoint's `Result` error schema
instead.

Caller cancellation still wins over timeout. If the caller aborts the request,
the wire call rejects with `CANCELLED`.

## Retry

`withRetry()` from `@emdash/shared/requests` is handler middleware backed by
Shared `retry()` from `@emdash/shared/scheduling`. It requires an explicit
`shouldRetry` classifier:

```ts
const loadRemote = compose(rawLoadRemote, [
  withRetry({
    schedule: retrySchedules.fixed(250, 2),
    shouldRetry: (error) => isWireError(error, 'DISCONNECTED'),
  }),
]);
```

Do not retry arbitrary procedure failures. A retry policy should be attached only
when the operation is idempotent, deduplicated by request identity, or otherwise
safe to repeat. Contract mutations already have their own retry behavior and
retry only `DISCONNECTED` by default.

## Deduplication

`deduplicate(options?)` from `@emdash/shared/requests` is handler middleware for
sharing one in-flight execution for identical inputs:

```ts
const expensiveStats = compose(rawExpensiveStats, [
  deduplicate({ key: (input) => `${input.repo}:${input.branch}` }),
]);
```

The default key is stable JSON identity. Settled calls are not cached and
rejections are not cached.

Caller cancellation is independent from shared execution. One caller may stop
waiting without aborting the underlying request for other waiters. Set
`cancelWhenUnused: true` only when it is correct to abort shared work after the
final waiter leaves.

## What Stays Out Of Middleware

Keep protocol-visible behavior in contracts:

- Endpoint kind.
- Input and output schemas.
- Upload size and MIME constraints.
- Live model, log, stream, and job semantics.
- Mutation idempotency envelopes.

Keep UI presentation policy, such as command visibility or context keys, outside
Wire middleware. Keep domain failures in `Result` payloads when callers are
expected to handle them.
