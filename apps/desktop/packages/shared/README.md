# @emdash/shared

`@emdash/shared` is the repo's standard library: package-level foundations reused
by Wire, Core, desktop, workspace-server, and tests. These primitives are
intentionally generic — they do not define product domains, Wire protocol
messages, or host-specific process behavior.

## Standard-Library Stance

Working primitives keep their exports regardless of measured consumers. A
`Result` type without `map`/`andThen` is half a type, so the full combinator
API stays exported even when a usage census finds few callers; the same goes
for the request middleware family, `createDurableQueue`,
`createSharedResource`, and the logger utilities. Do not re-litigate
zero-consumer exports in the next census. What this stance does **not** cover
is genuine machinery: internals such as timer-delay normalization stay
unexported.

## The Prelude

The root entrypoint (`@emdash/shared`) is the single home for the blessed
cross-cutting core:

- The result module: `Result<T, E>`, `ok`/`err`/`fail`, guards, combinators
  (`map`, `andThen`, `tryCatch`, `gen`, …), and the serialization/error family
  (`Serializable`, `SerializedError`, `BaseError`, `toSerializedError`,
  `resultSchema`).
- `Unsubscribe` and the lifecycle leases: `Lease`, `PendingLease`,
  `toPendingLease`, `once`.
- `createEmitter` and the `Emitter<T>` interface.
- `isDeepEqual`.
- `Secret`: `secret`, `isSecret`, `reveal`, `REDACTED`.

Every symbol has exactly one home package-wide: prelude symbols come from the
root, domain symbols from their subpath. Nothing is exported from both.

## Entrypoints

- `@emdash/shared` — the prelude (above).
- `@emdash/shared/concurrency`: `Scope` (`createScope`), `createLifecycleRegistry`,
  `createConcurrencyLimiter`, `createKeyedLanes`, `createMailbox`,
  `createAsyncCache`, `createResourceCache`, `createSharedResource`,
  `createDurableQueue`, `createBoundedBuffer`, and `Disposable`.
- `@emdash/shared/scheduling`: `Clock`, `systemClock`, `abortableWait`,
  `abortReason`, `throwIfAborted`, `waitWithSignal`, `retry`, `retrySchedule`
  and the `retrySchedules` combinators, `runWithTimeout`, `TimeoutError`, and
  `TimerHandle`.
- `@emdash/shared/requests`: request orchestration — `compose` middleware,
  `withRetry`, `withTimeout`, `withScheduler`, `deduplicate`,
  `createRequestScheduler`, and `createTokenBucketGate`.
- `@emdash/shared/logger`: the browser-safe logging surface — `log`,
  `runWithLogger`, levels, formatting, field preparation, and redaction.
- `@emdash/shared/logger/node`: the Node-only surface — `initProcessLogging`,
  `createPinoLogger`, `createFileTransport`, and `installAsyncLogContext`.
- `@emdash/shared/plugins`: the plugin framework — capabilities, assets,
  registries, and `PluginIconAsset` (the one icon-asset type; never re-alias it).
- `@emdash/shared/testing`: `deferred`, `createManualClock`,
  `createStubLogger`, and `waitFor`.
- `@emdash/shared/util`: stable utility helpers such as `stableStringify`.
- `@emdash/shared/markdown`: mention grammar helpers.
- `@emdash/shared/config`: layered config parsing with zod schemas.
- `@emdash/shared/perf` and `@emdash/shared/perf/node`: spawn accounting and
  process vitals instrumentation.

## Choosing Lifecycle Primitives

Use `Scope` for ownership, cancellation, cleanup ordering, and async work that
must not outlive its feature. Use `scope.add()` and `scope.use()` for finalizers,
`scope.child()` for nested ownership, and `scope.run()` for tracked async work.

Use `createLifecycleRegistry` when a feature owns a keyed set of local resources
with explicit `start()` and `stop()` commands, typed start/stop results,
queryable state, and state-change observers. It is a state registry, not a lease
cache or protocol primitive.

Use `createResourceCache` when resource lifetime is demand-driven: consumers call
`acquire()`, hold leases, release them, and optionally benefit from an idle TTL.
Use `createSharedResource` for the same lease behavior around one unkeyed
resource, and `createAsyncCache` for retryable cached async values with no
finalizer.

The command/event/effect machine primitive is internal to `@emdash/core`'s acp
runtime (`packages/core/src/runtimes/acp/node/machine/primitive/`) and is not
offered as a shared building block. Use Wire-owned primitives when the lifecycle is
protocol-specific: Wire workers belong to `@emdash/wire/worker` because they
supervise process generations and keep a stable typed Wire client, and
`LiveJobSource` belongs to `@emdash/wire/live` because it publishes cancellable
job state, progress, retention, and remote client handles.

## Package Conventions

- **Ownership-drop**: primitives that take ownership of values fire `onDrop`
  exactly once for every taken-then-discarded value, and never reject because
  of it.
- **Never-silent**: where a failure would otherwise vanish, optional failure
  hooks default to logger-backed reporting rather than swallowing (for example
  the emitter's `onSubscriberError` and keyed-lane coalesce failures fall back
  to `log.warn`).
- **Clock seam**: no raw `Date.now`/`setTimeout` outside `scheduling/clock.ts`;
  time-dependent primitives accept a `Clock`.
