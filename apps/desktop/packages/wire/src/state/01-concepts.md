# Concepts

The mental model behind `wire/src/state/`. Read this before the primitive
reference — every primitive is a small application of the rules defined here.

## 1. Nodes and the graph

Every reactive value is a **node** in a directed acyclic graph:

- **Source nodes** hold values written from outside the graph: `cell`
  (in-memory writable) and `query` (async snapshot of an external system).
- **Derived nodes** (`derived`) compute their value from other nodes and hold
  no truth of their own.
- **Edges** (dependencies) are discovered automatically for `derived` (see §4)
  and are *not* modeled inside `query` — a query's true dependency is an
  external system, which the graph cannot see (see §5).

Side effects — publishing to the wire, feeding a UI store, logging — attach
only at **observation edges** created by `observe` (or the bridges built on
it, `expose` and renderer adapters). Nodes themselves are pure with respect to
the outside world.

## 2. Snapshots: value + status + metadata

A node never emits bare values. Every publish is a **snapshot**:

```ts
type Snapshot<T> = {
  value: T;
  status: 'live' | 'stale' | 'loading' | 'error';
  revision: number;            // monotonic per node
  observedAt?: number;         // when the external source was last confirmed (query only)
  error?: unknown;             // present when status === 'error'
  mutationIds?: readonly string[]; // pending acknowledgments riding this publish
};
```

- `cell` and `derived` over cells are always `'live'` — they *are* the truth.
- `query` moves through `'loading'` (no value yet) → `'live'` (fetched, no
  pending invalidation) → `'stale'` (poked; a refresh is scheduled or in
  flight) → back to `'live'`. On a failed fetch it keeps its last good value
  and reports `'error'`.
- `derived` computes its status from its inputs: **weakest wins**
  (`error` < `loading` < `stale` < `live`). This happens automatically because
  `read` accumulates status into the running computation (§4).

This is the same shape as SolidJS resource states
(`pending/ready/refreshing/errored`) and a cold/warm/hot temperature model —
cold/warm/hot is `loading`/`stale`/`live`, with the observation time as the
freshness timestamp.

`revision` and `mutationIds` exist for the wire edge: they become the
`LiveCursor` sequence and the `LiveUpdate.mutationIds` of the published model.
See [04-wire-integration.md](./04-wire-integration.md#read-your-writes).

## 3. Turns: how change propagates

Propagation is **push-dirty, pull-value, once per turn**:

1. A write happens: `cell.set`, a poke delivery, a `query` fetch resolving, a
   `settle`. The written node and its transitive dependents are marked dirty.
2. A **turn** is scheduled (one `queueMicrotask` per burst of writes — writes
   in the same tick coalesce automatically, like React 18 / the TC39 signals
   proposal; there is no need to call `batch` for correctness).
3. When the turn flushes, dirty nodes that are **observed** (§6) recompute in
   topological order. Each node recomputes **at most once per turn** — this is
   glitch-freedom: a `derived` reading two inputs that both changed in the
   turn sees the final value of both and publishes one consistent snapshot.
4. A recomputed node publishes only if its value changed under its `equals`
   function (default: `Object.is` for `derived`/`cell`, deep-equality
   fingerprint for `query`). No-op recomputes propagate nothing.

Async fits in naturally: a `query`'s *fetch* runs outside the turn (it is IO);
only its *resolution* is a write that schedules a turn. The graph itself is
always synchronous and glitch-free; asynchrony lives at the source nodes.

## 4. Tracked reads (`snapshot`) — inside the graph

Inside a `derived` computation, `snapshot(node)`:

- returns the node's full `Snapshot<T>` — `.value` holds the current value
  (`T` for `cell`/`derived`; `T | undefined` for a `query` that has never
  fetched, unless it declares `initial`),
- registers a dependency edge for exactly this recompute (dependencies are
  re-discovered every run, so conditional and dynamic reads work — including
  reading different `family` members on different runs),
- folds the node's **status** into the computation's status (weakest wins),
- and folds the node's pending **mutationIds** into the computation's output
  snapshot.

`peek(node)` reads the current value without any of the above — the escape
hatch, equivalent to Solid's `untrack`.

Outside a computation (event handlers, tests), `snapshot(node)` returns the
current `Snapshot<T>` without registering anything.

## 5. The tracked/declared boundary

**Auto-track where reads are interceptable; declare where they are not.**

- `derived` auto-tracks: its inputs are in-process nodes whose reads the
  kernel can intercept. This is where the ergonomics come from — no
  dependency lists, no manual fan-out.
- `query` cannot auto-track: its dependency is "whatever rows/files/refs the
  fetch touched", which is invisible to the kernel. So a query **declares**
  its invalidation inputs as `pokes` — named channels that external change
  detectors (DB write hooks, fs watchers, git watch classifiers) fire into.

This boundary is a feature, not a limitation: "does every write that can
change this query's result poke one of its channels?" remains an auditable,
greppable property of the codebase rather than dissolving into magic.

## 6. Observation and demand

The graph is **lazy**. A node does work only when it is *observed*:

- `observe(node, cb, { scope })` makes a node observed directly.
- Observation propagates through dependencies: if an observed `derived` read a
  `query` on its last run, that query is observed too.
- An unobserved `query` that gets poked just stays dirty — zero fetches, zero
  timers (this carries over `ComputedLiveState`'s demand gating exactly). It
  fetches when observation arrives or when explicitly `refresh()`ed.
- When the last observer leaves, a `family` member enters its **linger**
  window: it stays warm (retaining its cached value, absorbing pokes as
  dirty-flags) for a TTL, then is disposed. Re-observation within the window
  is instant.

### Demand is a policy, not a rendering accident

`observe` is the *mechanism*; **who observes, and when, is policy** — and the
policy differs by side:

- **Host side**: demand arrives through `expose` leases — a remote client
  acquiring a model state *is* the observation. Nothing to decide.
- **Client side (renderer)**: demand must **not** be driven by render-time
  observability (e.g. MobX `onBecomeObserved`). Render observation is
  high-frequency and semantically meaningless — virtualized lists scrolling,
  collapsed panels, conditional branches — while fetch initiation is expensive
  and semantically meaningful, and pending state needs a clear owner. Instead,
  demand is **pinned imperatively at lifecycle boundaries** (app bootstrap,
  project mount, view-scope instantiation, navigation intent) with
  [`pin`/`prefetch`](./02-primitives.md#pin-and-prefetch); render-level
  reactivity only *invalidates* components, it never acquires or releases
  demand. A render read of an unpinned model returns `undefined` and warns in
  dev — a surfaced lifecycle bug, not a silent expensive fetch. See
  [04-wire-integration.md](./04-wire-integration.md#renderer-bindings-mobx)
  for the full renderer story.

## 7. Ownership: Scope, not release()

Every subscription, lease, and family retention is owned by a `Scope`
(`@emdash/shared/concurrency`). Disposing the scope tears down everything
under it, transitively — `observe` requires a scope, `remote` leases release
on scope disposal, `family` members are retained by the scopes observing
them. Manual release exists only as an escape hatch. This is SolidJS's
ownership tree (`createRoot`/`onCleanup`) mapped onto the primitive emdash
already has.

## 8. Two write channels into a `query`

External sources are written to by many actors, so `query` distinguishes two
kinds of change notification (the TanStack Query split —
`invalidateQueries` vs `setQueryData`):

- **`poke` → invalidate**: "truth may have changed." Schedules a
  (debounced, demand-gated) refetch; publishes only if the result differs.
- **`settle(update, { mutationIds })` → write-through**: "I performed the
  change, and here is the result (or a reducer producing it)." Publishes
  immediately without touching the external source; lane-ordered against
  fetches; wins over any fetch that started earlier (stale-fetch guard).

Echoes of your own writes (an fs watcher firing for a file you just created)
arrive later as pokes; the resulting refetch is a *confirmation* that the
equality gate absorbs without publishing. This is deliberate: external
sources are multi-writer, so echo suppression is unsound — cheap confirming
reads are the price of correctness, and they never reach subscribers.

## 9. What this kernel is not

- **Not a transport.** Cursors, snapshots/deltas, gap recovery, resubscribe,
  lease negotiation, and mutation idempotency stay in `live/protocol/` and the
  replica machinery. The kernel plugs into them via `expose`/`remote`.
- **Not for append-only data.** Live logs (seq-tailed text), event streams,
  and live jobs (progress + terminal result) keep their own primitives —
  forcing them into value semantics would lose functionality.
- **Not a renderer framework.** React/MobX bindings are thin adapters over
  `observe`, owned by the apps, not by this package.
