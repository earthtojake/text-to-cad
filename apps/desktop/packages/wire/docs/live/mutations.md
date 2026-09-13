# Mutations

Mutations connect API calls to live model updates. A mutation can update one
model, many instances of one model, or several model refs. The key extra piece
is the `mutationId`: it tags emitted `LiveUpdate`s so clients can prove their
bound live models have observed the mutation.

## Why Mutation IDs Exist

An RPC result only tells the caller that the server handler finished. It does
not prove every live subscription in the UI has applied the corresponding
patches. Mutation ids bridge that gap:

```ts
server.produce(
  (draft) => {
    draft.tasks.push({ id: 'task-2', title: 'Apply the first patch', done: false });
  },
  { mutationIds: ['example-add-task'] }
);
```

The update carries `mutationIds: ['example-add-task']`. A replica can resolve
`waitForMutation('example-add-task')` when its local model applies that update.

## Providers and Context

Live model contract mutations run against a `LiveModelProvider` — most commonly
one produced by `expose()` from `@emdash/wire/state`, which bridges kernel state
onto the endpoint. Mutation handlers update kernel cells and await the observed
revision so the returned cursor is settled:

```ts
const sessions = expose(api.session, { metadata: (key) => metadataCell(key) }, {
  mutations: {
    async setTitle(ctx) {
      const revision = metadataCell(ctx.key).update(
        (previous) => ({ ...previous, title: ctx.input.title }),
        { mutationIds: [ctx.mutationId] }
      );
      await ctx.observed('metadata', revision);
      return ok({ title: ctx.input.title });
    },
  },
});
```

Keys use `stableStringify()`, so object key order does not matter when providers
and client bindings look up an instance. The mutation context is instance-bound:
`ctx.key` identifies the addressed member and `ctx.observed(name, revision)`
records the cursor of every touched member state. The wire result is:

```ts
type LiveMutationResult<D, E> =
  | { success: true; data: { data: D; cursors: LiveCursorEntry[] } }
  | { success: false; error: E };
```

The `data.data` value is the domain result. `data.cursors` tells the client which
live model bindings need to catch up.

## Client Settling

`LiveModelReplicaCache.acquire(key)` returns a `ReplicaInstance` for one group key. Its
mutation methods call the live model client handle and then settle against the local
`ReplicaState`s.

Group mutation methods return `{ result, settled }`:

```ts
const sessions = createLiveModelReplicaCache(api.session, contractClient.session);
const lease = sessions.acquire({ sessionId: 'demo' });
const session = await lease.ready();

const added = await session.mutations.addNote({ text: 'Typed client mutation' });
await added.settled;
await lease.release();
await sessions.dispose();
```

`settled` waits for every cursor in the mutation result. For each cursor entry,
it resolves when either:

- the matching binding applies an update tagged with the mutation id, or
- the matching binding reaches the returned cursor.

This lets UI code safely read live client snapshots after `await settled`.

## Group Contract Mutations

The API layer integrates mutations through `liveModel()` member
mutations. Each group mutation becomes a client method:

```ts
const updated = await session.mutations.setTitle({ title: 'Grouped wire' }, {
  mutationId: 'custom-mutation',
});
await updated.settled;
```

If no id is provided, the replica mutation helper generates one with
`createMutationId()`.
Explicit ids are useful for optimistic previews, where the preview and server
mutation must share the same confirmation id.

## Idempotency and Retries

The server-side idempotency cache used by `expose()` stores settled mutation
results by `mutationId` and shares one in-flight execution for concurrent
duplicates.

By default the cache keeps entries for 5 minutes with a 1000-entry cap.
Configure or disable it through the `idempotency` option:

```ts
const sessions = expose(api.session, states, {
  mutations,
  idempotency: { ttlMs: 60_000, maxEntries: 500 },
});

const withoutDedupe = expose(api.session, states, { mutations, idempotency: false });
```

The client never retries mutations automatically. Callers opt in per call with
an explicit retry schedule; retries reuse the same `mutationId`, so the
server-side cache deduplicates them:

```ts
await session.addNote(input, {
  mutationId: 'add-note-1',
  retry: { schedule: retrySchedule({ delaysMs: [250, 1_000], maxRetries: 2 }) },
});
```

Opted-in retries fire only for `DISCONNECTED` and `TIMEOUT` errors; they never
happen for `CANCELLED` errors.

The cache is process-local and temporary. It provides at-most-once behavior
within one server process lifetime, not durable exactly-once semantics. If a
mutation has durable side effects such as database writes, store the
`mutationId` in that domain layer too.

Use `procedure()` for API calls that do not need live model cursor settling.
`mutation()` is only valid as a member of `liveModel().mutations`
in the contract API.

