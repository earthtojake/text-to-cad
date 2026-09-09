# Lifecycle Utilities

`Scope`, `LifecycleRegistry`, and the resource cache primitives are
dependency-light Shared lifecycle utilities exported from
`@emdash/shared/concurrency`. Scheduling utilities are exported separately from
`@emdash/shared/scheduling`. Wire uses these primitives, but they do not define
Wire protocol messages.

- `Scope` owns cleanup and async work for a tree of resources.
- `LifecycleRegistry` owns explicit keyed start/stop state machines.
- `Clock` owns sleeps, deadlines, retry backoff, and disposable timers.
- `ResourceCache` turns keyed demand into retained resources with ref-counted leases.
- `SharedResource` is the unkeyed form for one lazily created resource.
- `AsyncCache` caches async values that do not have finalizers.
- `Mailbox` is a bounded async handoff queue for one logical consumer.

They do not define wire messages and can run in browser, renderer, main process,
or tests.

## Scope

Use a scope when a feature creates more than one disposable resource and those
resources should die together:

```ts
import { createScope } from '@emdash/shared/concurrency';

const scope = createScope({ label: 'conversation:abc', logger });

scope.add(() => detachLiveState());
scope.add(() => removeWindowListener());
scope.use({ dispose: () => runtime.dispose() });
scope.run('refresh', async (signal) => {
  await clock.sleep(250, { signal });
  await refreshVisibleState({ signal });
});

await scope.dispose();
```

Semantics:

- `state` is `open`, `closing`, or `closed`.
- `signal` aborts synchronously when disposal begins.
- `run(label, fn)` starts a tracked async operation with its own abort signal.
- Cleanups run in reverse registration order.
- Child scopes and active runs settle before the parent's own cleanups.
- Cleanup errors are reported through `onCleanupError` and do not stop later
  cleanups.
- `dispose()` is idempotent.
- `add()` on an already disposed scope runs the cleanup immediately.
- `Run.exit` never rejects; use `Run.value()` when ordinary promise rejection is
  desired.

That last rule makes async attach/dispose races easier to handle:

```ts
const scope = createScope();
await scope.dispose();

scope.add(() => detachTopic()); // runs immediately
```

## Scope Logging

Every scope has `scope.log`. If a logger is supplied at the root, children
inherit it with a `scope` binding for the accumulated label path:

```ts
const runtimeScope = createScope({ label: 'runtime', logger });
const sessionScope = runtimeScope.child('session:one');

sessionScope.log.info('session attached');
```

Default cleanup error handling logs through the scope logger:

```ts
const scope = createScope({ label: 'view', logger });
scope.add(() => {
  throw new Error('cleanup failed');
});

await scope.dispose(); // logger.warn('scope cleanup failed', ...)
```

Custom cleanup handlers receive `{ label, labelPath, logger }`:

```ts
const scope = createScope({
  label: 'root',
  onCleanupError: (error, context) => {
    context.logger.warn('custom cleanup failure', {
      labelPath: context.labelPath,
      error,
    });
  },
});
```

Use `describeScope(scope)` to inspect the live label tree:

```ts
console.log(describeScope(runtimeScope));
```

The description contains labels, label paths, lifecycle state, active runs, and
child descriptions. It does not expose cleanup callbacks.

When `createScope({ clock })` is used, child scopes inherit the same clock and
run diagnostics use deterministic timestamps.

## Scope Runs

Use `run()` when async work must not outlive the scope:

```ts
const run = sessionScope.run('attach-transcript', async (signal) => {
  const detach = await transcript.attach(updateView, { signal });
  sessionScope.add(detach);
});

await run.exit;
```

Disposing `sessionScope` cancels the run and waits for it before running the
scope's cleanups. Cancellation is cooperative: pass the provided signal to any
operation that can wait, sleep, perform I/O, or subscribe.

Use `run()` for background jobs, process transitions, replica attachment,
renderer bindings, and async setup. Use `add()` or `use()` for finalizers. Use
`ResourceCache` when a keyed resource should be shared by leases.

For the full lifecycle model and invariants, see
[Structured concurrency](./structured-concurrency.md).

## LifecycleRegistry

Use `LifecycleRegistry` when a feature owns a keyed set of resources that are
started and stopped by explicit commands and callers need observable lifecycle
state:

```ts
import { createLifecycleRegistry } from '@emdash/shared/concurrency';
import { ok } from '@emdash/shared';

const runtimes = createLifecycleRegistry<
  { workspaceId: string },
  Runtime,
  StartRuntimeError,
  { reason: string },
  StopRuntimeError
>({
  label: 'workspace-runtimes',
  scope: appScope,
  keyOf: (input) => input.workspaceId,
  start: async (input, scope, signal) => {
    const runtime = await createRuntime(input.workspaceId, { signal });
    scope.add(() => runtime.dispose());
    return ok(runtime);
  },
  stop: async (_key, runtime, context, _scope, signal) => {
    await runtime.stop({ reason: context?.reason, signal });
    return ok(undefined);
  },
  onStateChanged: ({ key, current }) => {
    logger.info('runtime state changed', { key, state: current.kind });
  },
});
```

Selection guidance:

- Use `Scope` for ownership, cancellation, cleanup ordering, and async work that
  must not outlive its feature. It is not a keyed start/stop registry.
- Use `LifecycleRegistry` for local keyed resources with explicit `start()`,
  `stop()`, `register()`, `state()`, and state-change observation.
- Use `ResourceCache` when demand is lease-driven and the resource should exist
  only while consumers hold leases or while an idle TTL retains it.
- Use `WireWorkerHost.create(component, ...)` when the resource is a Wire worker process with
  readiness, a stable typed client returned by `ready()`, supervision, restart backoff, and child
  process generations.
- Use `LiveJobSource` when callers need a Wire-visible cancellable job with progress,
  terminal state, retention, and remote client handles.

`LifecycleRegistry` differs from `Scope` by modeling resource state rather than
general cleanup. It differs from `ResourceCache` by not ref-counting leases or
creating resources on demand from `acquire()`. It differs from Wire workers and
`LiveJobSource` by staying local and protocol-free: it does not supervise processes,
serve clients, publish progress, or retain terminal job state.

## Mailbox Ownership

Use `Mailbox` when local producers and one consumer need an explicit bounded
handoff. Register it with the owning scope, then run the consumer loop under the
same scope:

```ts
import { createMailbox } from '@emdash/shared/concurrency';

const mailbox = sessionScope.use(createMailbox<Event>({ capacity: 256 }));

sessionScope.run('drain-events', async () => {
  for await (const event of mailbox) {
    await handleEvent(event);
  }
});
```

Disposing `sessionScope` disposes the mailbox and unblocks pending producers or
consumers. For state machines, overflow guarantees, and the deferred Broadcast
contract, see [Mailbox and Broadcast](./mailbox-and-broadcast.md).

## Child Scopes

Use child scopes to model ownership:

```ts
const runtimeScope = createScope({ label: 'runtime' });
const sessionScope = runtimeScope.child('session:one');

sessionScope.add(() => stopSession());
runtimeScope.add(() => stopRuntime());

await runtimeScope.dispose();
```

Disposing `runtimeScope` disposes `sessionScope` first, then `stopRuntime()`.
Disposing `sessionScope` directly deregisters it from the parent so it does not
dispose twice later.

## ResourceCache

`ResourceCache` is useful when a resource should exist only while somebody is
using it: a live topic binding, a renderer view model, a preview server, or a
process-backed session.

```ts
import { createResourceCache } from '@emdash/shared/concurrency';

const sessions = createResourceCache({
  scope: runtimeScope,
  label: 'sessions',
  key: (input: { conversationId: string }) => input.conversationId,
  idleTtlMs: 30_000,
  create: async ({ conversationId }, scope) => {
    const session = await startSession(conversationId);
    scope.add(() => session.stop());
    return session;
  },
  onError: (error, key) => logger.warn('session creation failed', { key, error }),
});
```

`create(key, scope)` is also the disposal hook. Register teardown on the supplied
scope as soon as resources are acquired. If creation later fails, the scope is
disposed and partial resources are cleaned up.

Behavior:

- The first `acquire()` for a key calls `create()`.
- Concurrent acquires for the same key share the in-flight creation.
- In-flight creation is tracked as a scope run and is cancelled when the entry is
  invalidated or the parent scope closes.
- Each lease increments the refcount.
- `release()` is idempotent.
- The last release starts the grace timer.
- Acquire during the grace timer cancels teardown and reuses the active value.
- Failed creation is not cached; the next acquire retries.
- `peek(key)` returns the active value if creation has completed.
- `dispose()` force-disposes every active or retained entry.
- Passing `scope` attaches the source and all keyed entries to a parent scope.
  Disposing that parent scope force-disposes the source and rejects later
  acquisitions. `label` names the source node in `describeScope()` output.
- Every input that affects provisioning must be in `K` or fixed in the factory
  closure. There is no acquire-time creation context.

Usage:

```ts
const lease = sessions.acquire({ conversationId: 'abc' });
const session = await lease.ready();

await lease.release();
await sessions.dispose();
```

Parent scopes are useful for runtimes with several keyed resources:

```ts
const authScope = runtimeScope.child('auth');
const logins = createResourceCache({
  scope: authScope,
  label: 'login-source',
  key: (key: { providerId: string; methodId: string; generation: string }) =>
    `${key.providerId}:${key.methodId}:${key.generation}`,
  create: async (key, scope) => {
    const login = await startLoginPty(key.providerId, key.methodId);
    scope.add(() => login.dispose());
    return login;
  },
});

await authScope.dispose(); // also disposes every active login entry
```

## Grace Windows

Use `idleTtlMs` for resources whose demand can flap briefly. For example, a window
reload may detach and reattach live model bindings within a few hundred
milliseconds. A short grace window avoids tearing down the underlying resource
only to recreate it immediately.

```ts
const bindings = createResourceCache({
  key: (key: { taskId: string }) => key.taskId,
  idleTtlMs: 5_000,
  create: async (key, scope) => {
    const binding = client.task.transcript(key, (state) => render(state));
    scope.add(() => binding.dispose());
    await binding.ready;
    return binding;
  },
});
```

Use `ResourceCache`, `SharedResource`, or `AsyncCache` for new shared lifetime
work. Avoid adding compatibility lifecycle adapters around new code.

See [../../examples/scope/client.ts](../../examples/scope/client.ts) and
[../../examples/resource-cache/client.ts](../../examples/resource-cache/client.ts).
