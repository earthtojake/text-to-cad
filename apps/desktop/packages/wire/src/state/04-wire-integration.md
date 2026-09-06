# Wire integration: `expose` and `remote`

The kernel is transport-free. Two bridges connect it to the existing wire
live-model machinery — **without protocol changes**: `LiveUpdate` already
carries `mutationIds`, cursors and leases already exist, and the replica
transport already handles gaps, resubscribe, and idempotent mutation retries.

```text
            host process                    │ wire │                client process
                                            │      │
cell/query/derived/family ──▶ expose ──▶ LiveSource ═╪═▶ replica ──▶ remote ──▶ derived/observe
        ▲                        │       (protocol)  │   (protocol)     │
     pokes/settle             mutations ◀════════════╪════ mutations ◀──┘
```

## `expose`

Publishes a reactive (or family of reactives) as a wire live model, generating
the `LeasedLiveModelProvider` that today is written by hand per feature.

```ts
function expose<Def extends LiveModelDef>(
  contract: Def,
  states: ExposedStates<Def>,      // per state name: Readable | Family<Key, Readable>
  options?: {
    scope: Scope;
    mutations?: ExposedMutations<Def>;
    idempotency?: MutationResultCacheOptions | false;      // reuses MutationResultCache
    lingerMs?: number;                                     // default 15s
    instrumentation?: WireInstrumentation;
  }
): LeasedLiveModelProvider<Def>;
```

What the generated provider does, per `(key, stateName)`:

1. **Acquire** — resolves the family member (retaining it), creating demand:
   upstream queries fetch, timers arm. The returned `PendingLease<LiveSource>`
   resolves only after the state has a first non-`loading` snapshot, so cold
   `query` values are not published as schema-invalid `undefined`.
2. **Publish** — internally wraps the node in a `LiveStateSource<T>` (the existing
   class, reused as the wire-edge patch publisher) and `observe`s the node:
   each turn's snapshot becomes `liveState.replace(value, { mutationIds })`.
   `LiveStateSource` then does what it already does well: Immer structural diff,
   no-op suppression, generation/sequence cursors, fan-out.
3. **Release** — lease release starts the record's linger window. When the
   final lease lingers out, the record scope is disposed, dropping the
   observation and releasing upstream demand. Provider `dispose()` disposes the
   root scope and rejects pending waiters.

For same-node writes, node revision and the `LiveStateSource` sequence advance
together (one publish per turn per exposed node). For derived-hop writes,
`ctx.observed` waits for the exposed snapshot that carries the mutation id;
that is what makes cursor-based read-your-writes work end to end.

### Mutations

```ts
type ExposedMutationContext<Def, Name> = Readonly<{
  key: LiveModelKey<Def>;
  input: MutationInput<...>;
  mutationId: string;
  /** Resolve after the named state has published a snapshot containing `revision` (or this mutationId). */
  observed(state: StateName<Def>, revision: Revision | Promise<Revision>): Promise<void>;
}>;
```

A mutation handler:

1. Performs the external write (through the same `lane` the affected queries
   use, when the source needs serialization).
2. Applies the result — `q.settle(reducer, { mutationIds: [ctx.mutationId] })`
   when the outcome is known (file tree), or `channel.poke()` +
   `q.refresh({ mutationIds: [ctx.mutationId] })` when it must be re-read
   (git).
3. `await ctx.observed('tree', revision)` — the analogue of today's
   `context.settle('tree', cursor)` in `resource-host.ts`. The bridge
   translates the node revision to the `LiveCursorEntry` returned in the
   mutation result, so the client-side settled-promise machinery
   (`replica/instance.ts` `settleCursors`/`translateCursors`) keeps working
   unmodified.

Idempotency (`MutationResultCache` keyed by `mutationId`) and
instrumentation hooks are carried over from the existing hosts unchanged.

## Read-your-writes

The end-to-end chain, all pieces of which exist today except the derived hop:

1. Client calls a mutation; the replica attaches a generated `mutationId`.
2. Host handler `settle`s (or `refresh`es) source queries tagged with that
   `mutationId`.
3. **Kernel rule:** a `derived` merges the pending `mutationIds` of the input
   revisions it consumed into its own snapshot. Tags therefore survive any
   depth of derivation — this is the piece `wire/src/state/` adds that no
   legacy class had (today tags only work when the mutated state is the
   exposed state).
4. `expose` publishes the snapshot; `LiveUpdate.mutationIds` carries the tag.
5. The mutation response's cursors resolve; the client's `settled` promise
   (existing `ContractMutationInvocation.settled`) fulfills when its replica
   has applied the tagged update; optimistic overlays drop the corresponding
   patch.

A `mutationId` is considered *pending* on a node from the tagged
settle/refresh until the next publish that consumes that input revision.
`derived` folds tags only from input revisions that advanced, so tags do not
ride every subsequent publish.

## `remote`

Consumes a wire live model as a reactive family — the client-side mirror of
`expose`, wrapping `createLiveModelReplicaCache` (which keeps owning transport
concerns: snapshot+delta application, gap resync, schema validation,
persistent `StateStore` seeding).

```ts
function remote<Def extends LiveModelDef>(
  contract: Def,
  client: LiveModelClientHandle<Def>,
  options?: {
    scope: Scope;
    stores?: ReplicaStateStores<Def>;    // persistent seed → status 'stale' until live
    lingerMs?: number;                    // maps to replica lingerMs
    clock?: Clock;                        // deterministic family linger in tests
  }
): RemoteModel<Def>;

type RemoteModel<Def> = Family<LiveModelKey<Def>, {
  states: { [Name in StateName<Def>]: Readable<StateData<Def, Name> | undefined> };
  mutations: ReplicaMutations<Def>;      // unchanged passthrough, incl. settled promise
}>;
```

Semantics:

- Reading a state inside an observed computation acquires the replica lease
  (via the family's retention); scope disposal releases it. No manual
  `acquire()`/`release()` in consumers.
- Each state is query-shaped: `undefined`/`'loading'` before the first
  snapshot, `'stale'` when seeded from a persistent store or after a
  connection gap until resynced, `'live'` when following, `'error'` on
  attachment failure (with retry per existing replica behavior).
- `snapshot(state).mutationIds` exposes the tags from `LiveUpdate`, which is
  what the [`optimistic` primitive](./02-primitives.md#optimistic) keys its
  acknowledgment pruning on
  ([03-composition.md, example 4](./03-composition.md#worked-example-4-optimistic-overlay-client-side)).

### Renderer bindings (MobX)

The renderer keeps MobX as its reactive system; the kernel graph ends at
`remote`, and the bridge is deliberately thin (owned by the apps, not this
package). Two rules define it:

1. **Atoms invalidate, pins retain.** Each remote state is wrapped in a MobX
   atom whose `reportChanged()` fires from the kernel `observe` callback —
   but the atom's `onBecomeObserved`/`onBecomeUnobserved` do **not** drive
   kernel demand. Retention comes from `pin`s owned by view-scope lifetimes
   (view-scope instantiation pins the models the view needs, before render;
   disposal releases them; `prefetch` warms on navigation intent). This keeps
   expensive fetches off the render path and gives pending state one owner —
   the boundary's `PinSet.status` — instead of scattered per-component
   spinners. Rationale in
   [01-concepts.md §6](./01-concepts.md#demand-is-a-policy-not-a-rendering-accident).
2. **Reconcile for granularity.** Because the replica applies Immer patches,
   consecutive snapshots are structurally shared; a generic reconciler feeds
   keyed `observable.map`s and skips reference-equal entities, so per-entity
   MobX invalidation (and per-row rendering) survives coarse wire snapshots.
   Composition into view models happens in MobX `computed`s — the
   renderer-side analogue of `derived`. See
   [03-composition.md, Renderer integration](./03-composition.md#renderer-integration-mobx).

Because a `remote` state is an ordinary `Readable`, everything composes
symmetrically: a desktop main process can `derived`-join a `remote` model
from the workspace server with its own local queries and `expose` the result
onward to the renderer — the relay case falls out of the design instead of
needing bespoke code.

## What stays in `live/`, untouched

| Area | Why it stays |
|---|---|
| `live/protocol/` | Wire format: cursors, snapshots, updates, `LiveSource`. The bridges' vocabulary. |
| `live/replica/` transport (`ReplicaState`, gap handling, stores) | Network realities: reconnects, resync, validation, persistence. `remote` wraps it. |
| `live/state/server.ts` (`LiveStateSource`) | Reused *inside* `expose` as the patch publisher. Direct feature use is what migrates. |
| `live/log/`, `live/event-stream/`, `live/job/` | Append-only / job-shaped data; value semantics would lose functionality. |
| `live/mutations/` envelope types + settled-cursor client machinery | Idempotency envelope and read-your-writes transport; reused by `expose`/`remote`. The mutation result cache lives beside `expose` in `state/bridge/result-cache.ts`. |

What `expose`/`remote` make obsolete is listed in
[05-migration.md](./05-migration.md).
