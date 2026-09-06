# Serving and Clients

The API layer turns a contract into a server-side `Controller`, serves it over a
`WireTransport`, and creates a typed client over the matching transport.

## Creating a Controller

`createController(contract, impl)` maps each endpoint to server behavior:

```ts
const controller = createController(
  notesApi,
  {
    session: sessionsHost,
    activity: () => activityLogServer,
    clearNotes: (input) => {
      instance.states.notes.produce((draft) => {
        draft.notes = [];
      });
      return instance.states.notes.snapshot().data;
    },
  }
);
```

The `impl` object is keyed by the contract shape. Procedures receive
`(input, meta)`. Jobs use `{ run, toError? }`, a `LiveJobClientHandle`, or a
`LiveJobReplicaCache`. Live logs use resolver functions, `LiveLogClientHandle`s, or
`LiveLogReplicaCache`. Event streams use `createEventStreamHost()`, resolver functions,
or `EventStreamClientHandle`s. Live model contracts use `expose()` or an existing
`LiveModelClientHandle`.

Mutation idempotency is configured on `expose()`, not on the
controller. The controller only routes calls, snapshots, attachments, and live
mutation procedure envelopes.

Live model state is separate from the contract because instances are runtime
resources. A controller can be created once, while conversations, sessions, or
windows create and dispose keyed state through `family()` and scoped `expose()`
lifecycles.

See the state bridge tests under `src/state/bridge/`.

## Serving

`serve(transport, controller, options?)` listens for protocol messages:

- `call` invokes `controller.call(path, input, meta)`.
- `snapshot` calls `LiveSource.snapshot()`.
- `attach` subscribes to a live source and forwards `update` messages.
- `detach` unsubscribes.
- `cancel` aborts an in-flight call by id.

```ts
const pair = memoryTransportPair();
const stop = serve(pair.right, controller, {
  logger,
  instrumentation: { callEnd: (event) => logger.debug('call finished', event) },
});
```

`serve()` returns an unsubscribe. Call it when the transport or server session
goes away. It also aborts in-flight calls and detaches live subscriptions when
the transport disconnects or when the serve loop is disposed.

## Validation

Contract validation is built into `createController()`. Every controller
validates by default, and the default is environment-sensitive: `'full'`
(inputs + outputs) everywhere except production, `'inputs'` in production
(`NODE_ENV === 'production'`). Pass `validate` to override:

```ts
const controller = createController(notesApi, impl, { validate: 'inputs' });
const stop = serve(pair.right, controller);
```

Policies:

- `none`: no schema parsing.
- `inputs`: parse procedure inputs, upload/download inputs, live model mutation
  envelopes, job start/cancel inputs, and live topic keys before delegating.
- `full`: includes `inputs`, then also parses procedure outputs, upload/download
  results, mutation results, and live job start results.

The default rule applies identically to bare controllers, component instances,
component workers, and tests (`createTestWire`), so a contract violation in a
test fails the same way it would in dev. Production boundaries stay on
`inputs`: values crossing a trust boundary are always parsed, while output
validation is skipped where it is too expensive.

Validation covers request/response values that pass through
`Controller.call()` and live topic keys passed to `Controller.resolveLive()`.
Live job progress, result, error values, and event stream payloads are emitted
later as live updates and are not intercepted.

## Connecting

`connect(transport, options?)` creates a low-level `Connection`:

```ts
const connection = connect(pair.left, { instrumentation });
```

`Connection` supports:

- `call(path, input, { signal? })`.
- `snapshot(topic)`.
- `attach(topic, push, { onReattach? })`.
- `onDisconnect(cb)`.
- `dispose()` to release the logical connection without closing its transport.

On disconnect, pending calls reject with `WireError` code `DISCONNECTED`.
Existing attachments are retained locally. If the transport exposes
`onReconnect`, `connect()` re-issues active `attach` requests after the replacement
link is live and then calls each attachment's `onReattach` callback.

Replicas use `onReattach` for live models, logs, and jobs to force a fresh
snapshot after reattach. Direct client-handle consumers can use the same callback when
they need to reseed UI state after reconnect.

`dispose()` rejects pending calls, releases live attachments and blob channels, and
unsubscribes the connection from transport events. It intentionally does not call
`transport.close()`. This allows a short-lived application handshake connection to
validate a candidate transport before handing that same transport to a stable
reconnecting connection.

The protocol layer intentionally has no version handshake. Receivers validate the
message `kind` and required fields in `isWireMessage()`; unknown message kinds are
ignored by transport adapters that parse untrusted frames.

## Typed Clients

`client(contract, connection)` returns a `ContractClient` with the same nested
shape as the contract:

```ts
const contractClient = client(notesApi, connection);

const sessions = createLiveModelReplicaCache(notesApi.session, contractClient.session, {
  onChange: {
    notes: (state, meta) => {
      console.log('notes model:', state, meta.kind);
    },
  },
});
const lease = sessions.acquire({ sessionId: 'demo' });
const session = await lease.ready();

const added = await session.mutations.addNote({ text: 'Typed client mutation' });
await added.settled;
await lease.release();
await sessions.dispose();
```

Live model and live log accessors are client handles. Use `state(key, name)` or
`handle(key)` to snapshot/attach without local state, or pass the client handle
to a replica wrapper.

Mutations return `ContractMutationInvocation`:

```ts
type ContractMutationInvocation<D, E> = {
  result: LiveMutationResult<D, E>;
  settled: Promise<void>;
};
```

`MutationCallOptions` lets callers provide a `mutationId`, a per-call
`timeoutMs` deadline override, and an explicit opt-in retry policy. There is no
automatic retry; retries reuse the mutation id, so opted-in retries stay
idempotent:

```ts
await session.mutations.addNote({ text: 'Optimistic title' }, {
  mutationId: 'custom-mutation',
  retry: { schedule: retrySchedule({ delaysMs: [250, 1_000], maxRetries: 2 }) },
});
```

## Cancellation

Wire supports cooperative cancellation for request messages. The client sends a
protocol message for the request id:

```ts
{ kind: 'cancel', id: callId }
```

Typed procedure clients accept an optional `{ signal }` argument:

```ts
const abort = new AbortController();
const result = client.slowOperation({ id: 'task' }, { signal: abort.signal });

abort.abort();
await result; // rejects with WireError code CANCELLED
```

If the signal is already aborted, the call rejects locally without posting.
Server procedure handlers receive the same signal through `CallMeta`:

```ts
const controller = createController(api, {
  slowOperation: async (input, meta) => {
    await abortableWork(input, meta.signal);
    return { ok: true };
  },
});
```

Cancellation is cooperative. Long-running handlers should pass the signal into
their own async work, listen for `abort`, or periodically check
`meta.signal?.aborted`. `snapshot` and `attach` requests also share the same
server-side cancellation registry, though most live sources complete those
requests synchronously.

Mutations are intentionally not cancellable through this API; they use
`mutationId` for idempotency and retry. See [mutations](../live/mutations.md).
Cancelling a `liveJob().start` wire call does not cancel the spawned job; job
cancellation is domain-level through the generated `<path>.cancel` procedure.

## Composing Controllers

Middle tiers compose by creating a typed client for the upstream contract and
passing client handles, local handlers, or replicas into a new controller. This
keeps forwarding typed and makes the chosen interception points explicit:

If the middle tier should only relay the entire upstream contract, use
`forwardController(contract, client)` instead of spelling out every endpoint:

```ts
const upstream = client(workspaceApi, connect(upstreamTransport));
const controller = forwardController(workspaceApi, upstream);
```

Use explicit `createController()` composition when the hop needs local behavior:

```ts
const upstreamConnection = connect(upstreamTransport);
const upstream = client(workspaceApi, upstreamConnection);

const conversations = createLiveModelReplicaCache(workspaceApi.conversation, upstream.conversation, {
  lingerMs: 10 * 60_000,
});

const controller = createController(workspaceApi, {
  // Local override.
  ping: async () => 'desktop-main',

  // Stateless forwarding.
  git: upstream.git,

  // Stateful interception/cache before serving downstream clients.
  conversation: conversations,
});
```

For nested contracts, object destructuring is enough to assemble the
implementation shape:

```ts
const controller = createController(appApi, {
  ...upstream,
  settings: {
    ...upstream.settings,
    save: async (input, meta) => {
      await auditSettingsChange(input, meta.signal);
      return upstream.settings.save(input, meta);
    },
  },
});
```

Use replicas when the middle tier needs to inspect, cache, or transform live
state before exposing it downstream. Use client handles directly when the middle
tier is only forwarding calls and live sources.

## Multi-Window Sessions

`createWireSessionHub(controller)` serves the same controller to multiple
transport sessions:

```ts
const hub = createWireSessionHub(controller);
const pair = memoryTransportPair();

hub.open('window-1', pair.right);
const contractClient = client(api, connect(pair.left));
```

Opening the same session id closes the previous transport. `close(id)` closes
one session and calls `transport.close?.()` after disposing the serve loop.
`dispose()` is async: it closes all sessions and awaits `controller.dispose?.()`.

`Controller.dispose`, when present, returns `Promise<void>`. Wrappers such as
validation, logging, session hubs, tests, process runtimes, and Electron exposure
propagate that promise so LiveJobSource servers and resource hosts can finish shutdown
before their owner reports disposed.

## Server-Side Call Helpers

For the full middleware pattern, including handler middleware versus controller
middleware, see [composable middleware](./middleware.md).

`compose(target, middlewares)` from `@emdash/shared/requests` applies target-first
middleware arrays to handlers or controllers. The first array entry is outermost:
it sees the request first and settles last.

```ts
const loadStats = compose(
  async (input, meta) => {
    return await fetchStats(input.repo, { signal: meta.signal });
  },
  [
    withTimeout({ timeoutMs: 20_000 }),
    withRetry({ schedule, shouldRetry: isTransient }),
    withTimeout({ timeoutMs: 5_000 }),
  ]
);

const controller = createController(api, { loadStats });
```

In this example the outer timeout bounds the complete retry program, while the
inner timeout bounds each attempt. Handler middleware must preserve the handler's
shape. Procedure handlers receive `(input, meta)` and middleware should preserve
all `meta` fields while deriving a replacement `meta.signal` when it needs
cooperative cancellation.

`deduplicate(options?)` from `@emdash/shared/requests` wraps procedure
implementations to share one in-flight promise for identical inputs:

```ts
const controller = createController(api, {
  expensiveStats: compose(
    async (input, meta) => {
      return await loadStats(input.repo, input.branch, { signal: meta.signal });
    },
    [deduplicate({ key: (input) => `${input.repo}:${input.branch}` })]
  ),
});
```

Behavior:

- Default key is `stableStringify(input)`, so object property order does not
  matter.
- Only in-flight calls are deduplicated. Settled calls are not cached.
- Rejections are not cached.
- `meta.signal` is not part of the key and shared execution is not aborted by
  one caller.
- Do not wrap mutations; mutation idempotency is handled by `mutationId`.

See [../../examples/dedupe/server.ts](../../examples/dedupe/server.ts).
