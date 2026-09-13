# Primitive reference

Signatures are the design contract for the implementation in this folder.
Names are deliberately boring: `cell`, `derived`, `query`, `family`,
`observe`, `peek`, `batch`, `pokeChannel` — plus the wire
bridges `expose` and `remote` documented in
[04-wire-integration.md](./04-wire-integration.md).

Common to everything below:

```ts
interface Readable<T> {
  /** Kernel-internal: tracked read, status/mutationId folding. Use snapshot()/peek(). */
}

declare function peek<T>(node: Readable<T>): T;      // never tracks
declare function snapshot<T>(node: Readable<T>): Snapshot<T>; // value + status + revision + metadata;
                                                              // tracked inside derived
```

`Snapshot<T>` is defined in [01-concepts.md §2](./01-concepts.md#2-snapshots-value--status--metadata).

---

## `cell`

A writable in-memory value. The leaf node for state the process itself owns:
agent activity, machine projections, expansion sets, optimistic overlays.

```ts
function cell<T>(initial: T, options?: {
  equals?: (a: T, b: T) => boolean;   // default Object.is
  name?: string;                       // instrumentation label
  onObservedChange?: (observed: boolean) => void;
}): Cell<T>;

interface Cell<T> extends Readable<T> {
  set(next: T, meta?: { mutationIds?: readonly string[] }): void;
  update(fn: (prev: T) => T, meta?: { mutationIds?: readonly string[] }): void;
}
```

Semantics:

- `set`/`update` mark dependents dirty and schedule a turn; consecutive
  synchronous writes coalesce into one turn automatically.
- Writes equal under `equals` are no-ops (no publish, no dirty marking).
- A normal cell write publishes `'live'`; status metadata can be supplied at
  bridge edges (for example `remote` uses a cell with initial `'loading'`).
- Treat values as immutable — replace, never mutate in place. (The wire edge
  diffs consecutive values structurally; in-place mutation breaks both
  equality gating and diffing.)

Replaces: direct feature use of `LiveStateSource` for in-memory state. The deleted
`BatchedLiveState` microtask scheduler is covered by turn coalescing; use
`query.debounceMs` or an edge debounce where timer windows were previously
needed.

## `derived`

A pure computation over other nodes. Lazy, cached, equality-gated,
auto-tracked, glitch-free.

```ts
function derived<T>(compute: () => T, options?: {
  equals?: (a: T, b: T) => boolean;   // default Object.is
  name?: string;
}): Readable<T | undefined>;
```

Semantics:

- `compute` must be synchronous and side-effect-free. Async work belongs in
  `query`; side effects belong in `observe`.
- Dependencies are re-discovered on every run: conditional reads, dynamic
  `family` member reads, and data-dependent joins all work. Members read on
  the previous run but not this one are released (they linger, then GC).
- Recomputes at most once per turn, only when observed, only when a
  dependency actually published.
- Status = weakest of the statuses read; `mutationIds` from input revisions
  that advanced since the previous compute are merged into the output snapshot.
  Tags therefore ride the derived publish that consumed them, but do not leak
  onto unrelated later publishes. This is what makes read-your-writes compose
  through derivations — see
  [04-wire-integration.md](./04-wire-integration.md#read-your-writes).
- Throwing inside `compute` puts the node in `'error'` status holding its
  last good value; it retries on the next turn in which an input publishes.

Replaces: `deriveLiveModel`-style glue, projection code that manually
subscribes to multiple `LiveStateSource`s, and `bindMachineToLiveState`'s `project`
step.

## `query`

An async computed whose truth lives in an external system (SQLite, the
filesystem, git, a remote API). The workhorse primitive; carries over
`ComputedLiveState`'s semantics as options and adds pokes and `settle`.

```ts
function query<T>(options: {
  fetch: (ctx: { signal: AbortSignal }) => Promise<T>;
  pokes?: readonly PokeSubscription[];   // declared invalidation inputs
  equals?: (a: T, b: T) => boolean;      // default: deep-equality fingerprint
  initial?: T;                            // makes the snapshot value T instead of T | undefined
  debounceMs?: number;                    // poke → refetch coalescing window (default 0)
  revalidateEveryMs?: number;             // periodic freshness while observed
  lane?: Lane;                            // serialize fetch/settle against other work
  name?: string;
  onError?: (error: unknown) => void;
  scope?: Scope;                         // optional owner for dispose()
}): Query<T>;

interface Query<T> extends Readable<T | undefined> {
  invalidate(): void;                                    // what pokes call
  refresh(meta?: { mutationIds?: readonly string[] }): Promise<Revision>; // force, ordered
  settle(
    update: T | ((prev: T | undefined) => T),
    meta?: { mutationIds?: readonly string[] }
  ): Revision;                                           // authoritative write-through
  dispose(): void;
}
```

Lifecycle and scheduling (all inherited from `ComputedLiveState`, renamed):

- **Demand-gated**: unobserved queries never fetch and hold no timers; a poke
  just marks them dirty. First observation (direct or via an observed
  `derived`) triggers the fetch.
- **Debounce**: N pokes within `debounceMs` produce one refetch.
- **Refresh collapse**: at most one fetch in flight plus one queued; further
  invalidations fold into the queued run.
- **Revalidate**: while observed, refetches every `revalidateEveryMs` as a
  safety net for missed pokes.
- **Equality gate**: a refetch whose result equals the current value (per
  `equals`) publishes nothing. This is also what absorbs watcher echoes of
  the query's own `settle`s.
- **Errors**: a failed fetch keeps the last good value, sets status
  `'error'`, reports via `onError`, and retries on the next explicit
  invalidation/manual refresh, fresh observation, or revalidation tick.

The two write channels ([01-concepts.md §8](./01-concepts.md#8-two-write-channels-into-a-query)):

- `invalidate()` / pokes: "truth may have changed" — refetch, maybe publish.
- `settle()`: "truth changed; here is the result" — publish now, without IO.
  Ordering rules: refreshes run on the query's `lane`; `settle` is a
  synchronous write-through that bumps the revision, and any fetch *started
  before* the settle is discarded when it resolves (stale-fetch guard). A
  reducer-style `settle(prev => ...)` on a cold query (no `prev`) is dropped —
  there is nothing to patch, and the next observation fetches anyway.

Replaces: `ComputedLiveState` (1:1), plus every hand-rolled
dirty-flag/debounce/refresh-queue in runtime resources.

## `family`

Keyed instantiation of any reactive structure, with refcounted retention and
linger GC. The keyed-provider bookkeeping that today lives in resource caches
and allocation graphs, as a primitive.

```ts
function family<K, R>(
  factory: (key: K, scope: Scope) => R,     // R: a node or a record of nodes
  options?: {
    key?: (key: K) => string;               // default stableStringify
    lingerMs?: number;                       // warm retention after last observer (default e.g. 15s)
    name?: string;
  }
): Family<K, R>;

interface Family<K, R> {
  (key: K): R;                // stable instance per key while retained
  peekMember(key: K): R | undefined;
  retain(key: K): () => void; // explicit pin; release starts linger
  dispose(): Promise<void>;
}
```

Semantics:

- `factory` runs once per key while the member is retained; the passed
  `scope` is the member's lifetime — register watches, lanes, and cleanups on
  it. Disposal (after linger) disposes the scope.
- Retention is explicit at the family level (`retain(key)`) and can be wired to
  observation at member nodes via `onObservedChange` (the `remote` bridge does
  this for its per-state cells). Plain `family(key)` access creates a warm
  member and immediately starts its linger window; re-access during linger
  re-arms that window.
- During linger the member stays warm: cached values survive, pokes accumulate
  as dirty flags (no fetches — demand gating still applies). Re-observation
  is instant and refreshes if dirty.

Implementation note: retention/TTL semantics match
`createResourceCache` (`@emdash/shared/concurrency`), which the
implementation should reuse or mirror.

Replaces: per-key instance maps in providers (`createLiveModelHost`'s
`entries`), resource allocation graphs' keyed lifetimes, and the keyed lease
plumbing in `createResourceLiveModelHost`.

## `observe`

The only side-effect edge. Everything that leaves the graph — wire publishes,
UI store feeds, logging — goes through it.

```ts
function observe<T>(
  node: Readable<T>,
  listener: (snapshot: Snapshot<T>) => void,
  options: { scope: Scope; immediate?: boolean }   // immediate: fire with current snapshot (default true)
): void;   // teardown via scope disposal
```

Semantics:

- Fires at most once per turn per node, after the graph has settled — the
  listener always sees a consistent world.
- Observation is what creates *demand* (fetches, timers) upstream.
- Listener errors are isolated and reported through instrumentation; one
  failing observer cannot prevent other queued notifications from flushing.
- No return value on purpose: lifetime is the scope's. (Tests can pass a
  locally created scope and dispose it.)

Replaces: manual `LiveStateSource.subscribe` + lifecycle pairs scattered through
providers and stores.

## `peek` and untracked reads

```ts
peek(node)      // read without tracking, without status folding
snapshot(node)  // full Snapshot<T> — status, revision, mutationIds
```

Use `peek` inside `derived` when a value should inform but not invalidate
(rare; document each use). Equivalent of Solid's `untrack`.

## `batch`

```ts
function batch<T>(fn: () => T, meta?: { mutationIds?: readonly string[] }): T;
```

Writes inside `fn` land in a single turn (they would anyway if synchronous —
`batch` exists to make the grouping explicit across helper calls) and share
`meta.mutationIds`, so one logical mutation touching several cells/settles is
acknowledged as one unit. Not required for coalescing; required only for
shared metadata.

## `pokeChannel`

The bridge from external change detection into queries. Channels are cheap,
named, and hierarchical-by-convention (key-scoped instances via closures or
`family`).

```ts
function pokeChannel(name: string): PokeChannel;

interface PokeChannel {
  poke(): void;                          // dirty all subscribed queries; coalesces per turn
  subscription(): PokeSubscription;      // what query({ pokes }) accepts
}
```

Typical producers:

- **DB poke bus**: entity services poke `tasksChannel(projectId)` after commit
  (post-commit, per-channel coalesced — per the tasks/projects LiveQuery
  plan).
- **fs watchers**: `RootResource`-style watch → route each event batch to
  per-directory channels (the watch *classifier* becomes the poke *router*).
- **git watch classifier**: `classifyGitWatchEvents` fires
  `refs`/`remotes`/`stashes`/`worktrees` channels.
- **Mutations**: after performing an external write the mutation either pokes
  the covering channel (cheap re-read) or `settle`s the query directly
  (write-through) — see [03-composition.md](./03-composition.md).

A poke carries no payload. If a change signal has a payload worth keeping,
it is either a `settle` (known new truth) or an event stream (append-only
data), not a poke.

## `optimistic`

A reusable overlay for pending local edits over an authoritative base:
apply-now, confirm-later, rollback-for-free. This lives in the kernel (not in
a UI utility) because its correctness inputs — snapshot `mutationIds` for
acknowledgment, generation changes for resync — are kernel metadata invisible
to any UI framework, and because it is needed on both sides of the wire (the
desktop main process is itself a wire *client* of the workspace server).

```ts
function optimistic<T>(base: Readable<T | undefined>): OptimisticView<T>;

interface OptimisticView<T> extends Readable<T | undefined> {
  /** Apply an Immer recipe until the base acknowledges (or the handle is dropped). */
  apply(recipe: (draft: T) => void, opts: {
    mutationId: string;
    ttlMs?: number;                    // safety prune for lost acks
  }): PendingHandle;                   // handle.drop() = rollback

  /** Convenience: apply recipe → invoke mutation → prune on settled, drop on failure. */
  run<I, D, E>(
    mutation: (input: I) => Promise<ContractMutationInvocation<D, E>>,
    input: I,
    recipe: (draft: T, input: I) => void
  ): Promise<Result<D, E>>;
}
```

Internals: a `cell<readonly PendingPatch[]>` plus a `derived` that reads
`snapshot(base)` (it needs the metadata, not just the value) and applies —
via Immer, preserving structural sharing — every recipe whose `mutationId`
the base has not yet acknowledged. The invariants it encodes once:

- **Rollback is free.** The overlay is a projection, never baked into the
  base; dropping a patch (mutation failed, TTL expired) recomputes to base
  with zero undo logic.
- **Ack pruning is exact**: keyed on the `mutationIds` riding the base's
  snapshots (the read-your-writes chain), not heuristics. Acknowledged or
  generation-stale patches are removed from the visible projection; their
  handles/timers are cleaned up by `drop`, TTL expiry, or `run(...).settled`.
- **Ordering**: patches apply in submission order. **Cold base**: recipes
  hold until the base has a value. **Resync**: a generation change prunes
  everything — the fresh snapshot is post-truth.
- **Structural sharing**: Immer application keeps unaffected subtrees
  reference-equal, which downstream granularity (MobX reconciliation,
  wire diffing) depends on.

The recipes are the same pure reducers used by host-side `settle` (e.g.
`runtimes/files/api/tree/optimistic.ts`) — one implementation, three uses:
client optimistic apply, host write-through, tests.

Replaces: the `ctx.produce` optimistic recipes of `mutations/group.ts`.

## `pin` and `prefetch`

Demand helpers built on `observe` — the client-side answer to *when does
state initialize* (see
[01-concepts.md §6](./01-concepts.md#demand-is-a-policy-not-a-rendering-accident)).
A pin is observation owned by a lifecycle scope: the fetch starts at the
boundary (mount, navigation, intent), not at render.

```ts
function pin(scope: Scope, nodes: readonly Readable<unknown>[]): PinSet;

interface PinSet {
  readonly status: 'loading' | 'stale' | 'live' | 'error';  // aggregate, weakest-wins
  settled(): Promise<void>;          // resolves when all pins leave 'loading'
}

/** A pin on a detached, timer-disposed scope — for navigation-intent warming. */
function prefetch(node: Readable<unknown>, opts: { ttlMs: number }): void;
```

Usage pattern (renderer): view-scope instantiation pins the models the view
needs; scope disposal releases them (they linger, then GC). Pending state gets
one owner — `pins.status` per boundary — instead of per-component spinners.
The anti-spinner stack is four independent layers: persistent-store seeding
(render `'stale'` immediately), pin-at-intent (fetch before render),
linger (instant back-navigation), and boundary-level gating via
`pins.settled()`.

## `lane`

Not a new abstraction — `query` accepts a `Lane` compatible with the existing
keyed-lane machinery (`KeyedLanes`, `RepositoryFamilyLane`) so fetches and
settles serialize against mutation commands hitting the same external
resource (git's object-store lock, per-file mutation mutexes). The kernel
only *awaits* lanes; it does not own them.
