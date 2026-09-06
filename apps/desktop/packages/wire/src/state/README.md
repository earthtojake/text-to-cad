# `@emdash/wire` reactive state (`wire/src/state/`)

> **Status: implemented in parallel to `wire/src/live/`.** The primitives in
> this folder are available as `@emdash/wire/state` and are in production use:
> desktop feature slices (tasks, workspaces, source-control, editor, projects)
> author providers with `expose` and consume them with `remote`. See
> [05-migration.md](./05-migration.md) for the remaining migration plan.

This folder holds the reactive state kernel for wire: a small set of
signals-style primitives that unify how authoritative state is produced,
derived, and published over the wire — and how replicas of it are consumed on
the other side.

It replaces the *value-reactivity* portion of `wire/src/live/` (the four ad-hoc
"a value that changes" flavors: `LiveStateSource` used directly by features,
`ComputedLiveState`, deleted `BatchedLiveState`, `bindMachineToLiveState`) and the
hand-written provider/lease boilerplate around them. It does **not** replace
the wire protocol (`live/protocol/`), the replica transport, live logs, event
streams, or live jobs — those stay. See
[04-wire-integration.md](./04-wire-integration.md) for the exact boundary.

## Why

Today every stateful runtime hand-rolls the same machinery: dirty flags,
debounce timers, one-in-flight-plus-one-queued refresh collapse, lease
lifecycles, imperative invalidation fan-out, and per-provider
`acquireState`/`ready`/`release` plumbing. `TreeResource` spends ~200 lines on
scheduling; `RepositoryResource` manually fans invalidations out to every
checkout; every `LeasedLiveModelProvider` implementation repeats the same ~40
lines. The kernel moves all of that into one tested core and leaves feature
code with declarations:

```ts
// A keyed, DB-backed live query — the whole provider.
const taskList = family((key: { projectId: string }, scope) =>
  query({
    fetch: () => selectTaskListView(db, key),
    pokes: [tasksChannel.match(key), conversationsChannel.match(key)],
    scope,
  }));

expose(tasksContract.taskList, taskList);
```

## The primitives at a glance

| Primitive | One-liner | Doc |
|---|---|---|
| `cell` | Writable value; the leaf for in-memory sources | [02](./02-primitives.md#cell) |
| `derived` | Pure, auto-tracked computation over other reactives | [02](./02-primitives.md#derived) |
| `query` | Async computed from an *external* source (DB, git, fs); declared invalidation via pokes; write-through via `settle` | [02](./02-primitives.md#query) |
| `family` | Keyed instantiation of any reactive, refcounted with linger GC | [02](./02-primitives.md#family) |
| `observe` | The only side-effect edge: subscribe a callback, owned by a `Scope` | [02](./02-primitives.md#observe) |
| `peek` | Untracked read | [02](./02-primitives.md#peek-and-untracked-reads) |
| `batch` | Group synchronous writes into one turn with shared metadata | [02](./02-primitives.md#batch) |
| `pokeChannel` | Named invalidation channel connecting external change signals to queries | [02](./02-primitives.md#pokechannel) |
| `optimistic` | Pending-edit overlay over an authoritative base: apply-now, ack-prune, rollback-for-free | [02](./02-primitives.md#optimistic) |
| `pin` / `prefetch` | Explicit demand at lifecycle boundaries: fetch at mount/intent, not at render | [02](./02-primitives.md#pin-and-prefetch) |
| `expose` | Publish a reactive/family as a wire live model (generates the provider) | [04](./04-wire-integration.md#expose) |
| `remote` | Consume a wire live model as a reactive family (wraps the replica) | [04](./04-wire-integration.md#remote) |

Ownership and disposal always flow through `Scope` from
`@emdash/shared/concurrency` — there is no manual `release()` in the common
path. On the client side, demand is driven by `pin`s owned by lifecycle
boundaries (view scopes), never by render-time observability — see
[01-concepts.md §6](./01-concepts.md#demand-is-a-policy-not-a-rendering-accident).

## Testing

The state module is tested in four deterministic tiers:

- Kernel tests in `core/kernel.test.ts` and `core/family.test.ts` cover turns,
  dynamic dependencies, error recovery, observer isolation, mutation-id
  folding, and linger GC.
- Primitive tests in `query.test.ts`, `optimistic.test.ts`, and `pin.test.ts`
  cover async races, write-through, TTL rollback, generation pruning, and
  demand aggregation.
- Bridge tests in `bridge/expose.test.ts` cover readiness, leases, and
  derived-hop mutation observation.
- `bridge/roundtrip.test.ts` runs `expose -> wire transport -> remote ->
  optimistic` over the real test wire harness to protect read-your-writes and
  no-flicker behavior end to end.

## Reading order

1. [01-concepts.md](./01-concepts.md) — the mental model: nodes, turns,
   observation, statuses, the tracked/declared boundary, publish metadata.
2. [02-primitives.md](./02-primitives.md) — reference for each primitive:
   signatures, semantics, options, edge cases.
3. [03-composition.md](./03-composition.md) — how primitives compose; worked
   examples (git runtime, file tree, DB-backed lists, optimistic overlays);
   the granularity rule that keeps performance flat.
4. [04-wire-integration.md](./04-wire-integration.md) — `expose`/`remote`,
   mutations, read-your-writes cursors, and the exact mapping onto the
   existing `live/protocol/` machinery.
5. [05-migration.md](./05-migration.md) — legacy class → primitive mapping,
   what gets deleted, and the incremental migration order.

## Design lineage

The API descends from SolidJS (ownership tree, `createResource`'s async
states, `untrack`, lazy equality-gated memos, `from()` interop), Jotai/Recoil
(`atomFamily` → `family`), and TanStack Query (`setQueryData` vs
`invalidateQueries` → `settle` vs pokes). The one deliberate departure from
Solid: dependency tracking is automatic only where reads are interceptable
(`derived` over in-process reactives); at the external-source boundary
(`query` over DB/fs/git), dependencies are *declared* as pokes so that "poke
coverage = query inputs" stays a greppable, auditable property.
