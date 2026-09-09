# Composition

How the primitives combine, the rules that keep composition sound, and worked
examples drawn from real emdash subsystems (each is the design target for that
subsystem's eventual port — nothing here is implemented yet).

## The composition rules

1. **Sources at the bottom, one per kind of truth.** In-memory truth → `cell`.
   External truth → `query` (+ pokes). Never mirror external truth into a `cell` "for convenience" —
   that creates a second source of truth with no invalidation story.
2. **Everything above sources is `derived`.** Joins, filters, projections,
   overlays, roll-ups: pure sync functions over tracked `snapshot()` reads. If
   you need async in a derivation, the async part is a missing `query`.
3. **Key with `family`, don't key by hand.** Any "per project / per workspace
   / per directory" reactive is a family member. Family + auto-tracking gives
   dynamic dependency sets for free (see the file tree below).
4. **Effects only at the edges.** `observe` (and the bridges `expose`/`remote`
   built on it) is the only place snapshots leave the graph.
5. **Granularity rule (performance):** don't write one big `derived` over many
   volatile inputs; write a `family` of small nodes and a shallow join at the
   top. Equality-gated members are referentially stable when unchanged, so
   joins preserve unchanged substructure by reference and downstream diffing
   stays O(changed subtree). A monolithic derived over N inputs recomputes
   O(N) on every change — that is the one way to make this system slower than
   the hand-rolled code it replaces.
6. **Volatility split:** keep machine-frequency data (git stats, agent
   activity, changed-line counts) in separate nodes from user-action-frequency
   data (task rows, project settings), and join them as late as possible —
   ideally in the consumer-side derived, so a churning overlay never
   republishes the structural model.

## Worked example 1: git runtime (query family, pokes, lanes)

Today: `RepositoryResource` holds four `ComputedLiveState`s, a watch
classifier, a family lane, and manual invalidation fan-out to checkouts.

```ts
const repository = family((key: RepositoryIdentity, scope) => {
  const lane = repositoryLane(key, scope);
  const channels = gitWatchChannels(key, scope);   // classifier → named pokeChannels
  const q = <T>(fetch: () => Promise<T>, on: PokeSubscription[]) =>
    query({ fetch, pokes: on, lane, debounceMs: 100, revalidateEveryMs: 5 * 60_000 });

  return {
    refs:      q(() => git.getRefs(key), [channels.refs.subscription()]),
    remotes:   q(() => git.getRemotes(key), [channels.remotes.subscription()]),
    stashes:   q(() => git.getStashes(key), [channels.stashes.subscription()]),
    worktrees: q(() => git.listWorktrees(key), [channels.worktrees.subscription()]),
    channels,
  };
});

const checkout = family((key: CheckoutIdentity, scope) => {
  const repo = repository(key.repository);
  return {
    status: query({
      fetch: () => git.status(key),
      pokes: [worktreeChannel(key, scope).subscription(), repo.channels.head.subscription()],
    }),
    // history depends on refs: subscribing replaces invalidateCheckoutHistory() fan-out
    history: query({
      fetch: () => git.log(key),
      pokes: [repo.channels.refs.subscription()],
    }),
    aheadBehind: derived(() =>
      computeAheadBehind(
        snapshot(checkout(key).status).value,
        snapshot(repo.refs).value)),
  };
});
```

What changed structurally: mutations (`createBranch`, `fetch`, …) stop calling
`invalidate('refs')` and `invalidateCheckoutHistory()` imperatively — they run
the git command, then `channels.refs.poke()`. Watcher pokes and mutation pokes
are the same channel; every dependent (including checkout histories, which the
repository never knew about) refreshes through its own subscription.

Git mutations stay on the poke path (not `settle`) because they cannot cheaply
compute the resulting refs state — re-reading is the honest move.

## Worked example 2: file tree (dynamic deps, cell + query join, settle)

Today: `TreeResource` — a single mutable `FileTreeModel` with expansion state
baked in, ~200 lines of hand-rolled lanes/resync coalescing, and mutations
that re-read directories they just changed.

Decomposed:

```ts
// Per-directory listing: keyed query. Watch events route to the dir's channel.
const dirListing = family((key: { root: RootId; dir: Path }, scope) =>
  query({
    fetch: () => readChildren(key),
    pokes: [fsChannel(key.root).forDir(key.dir).subscription()],
    equals: entriesEqual,
  }));

// Expansion is per-session interaction state — a cell, not part of the data model.
const expandedDirs = family((key: { root: RootId; sessionId: string }) =>
  cell<ReadonlySet<Path>>(new Set([ROOT])));

// The tree: a derived join whose dependency set follows the expansion cell.
const fileTree = family((key: TreeKey) =>
  derived(() => {
    const expanded = snapshot(expandedDirs(key)).value;
    return buildTree(key.root, [...expanded].map((dir) =>
      [dir, snapshot(dirListing({ root: key.root, dir })).value] as const));
  }));
```

Notes:

- **Dynamic dependencies:** expanding a directory writes the cell; the next
  recompute reads one more `dirListing` member, which retains it, which makes
  it fetch. Collapsing stops reading it; it lingers, then GCs. No subscription
  bookkeeping anywhere.
- **Structural sharing:** `buildTree` reuses unchanged directory entries by
  reference (members are referentially stable when unchanged), so the wire
  diff of the joined tree stays proportional to the actual change.
- **Mutations use `settle`:** `createFile` performs the fs op, then
  `dirListing(parent).settle(prev => applyKnownChanges(prev, changes), { mutationIds: [id] })`
  — no re-read on the mutation path. The watcher echo arrives as a poke; the
  confirming refetch matches under `entriesEqual` and publishes nothing. The
  reducers are the ones already written for the client in
  `runtimes/files/api/tree/optimistic.ts` — shared verbatim between the
  client's optimistic apply and the host's settle.
- **Resync** (watcher overflow) = poke every loaded directory channel; the
  per-query refresh collapse replaces `drainResyncs`/`trailingResyncRequested`.

## Worked example 3: DB-backed list + activity overlay (volatility split)

The tasks/projects LiveQuery plan, expressed in primitives:

```ts
// Structural model: changes at user-action frequency.
const taskList = family((key: { projectId: string }) =>
  query({
    fetch: () => selectTaskListView(appDb, key),        // tasks ⋈ conversations
    pokes: [tasksChannel(key.projectId).subscription(),
            conversationsChannel(key.projectId).subscription()],
  }));

// Volatile overlay: machine frequency, in-memory source.
const agentActivity = cell<Record<ConversationId, AgentActivity>>({});
const taskActivity = family((key: { projectId: string }) =>
  derived(() =>
    sliceActivityForProject(snapshot(agentActivity).value, key.projectId)));
```

The two are exposed as **separate wire models** and joined in the consumer's
derived (rule 6): activity churn republishes a small record, never the task
list. Entity services poke the channels post-commit; there are no imperative
"emit task event" paths left.

## Worked example 4: optimistic overlay (client side)

An optimistic edit is a pending patch composed over the base and dropped when
the base acknowledges the mutation. This pattern is packaged as the
[`optimistic` primitive](./02-primitives.md#optimistic) — under the hood it is
exactly a `cell` of pending patches plus a `derived` over `snapshot(base)`,
but the invariants (exact ack pruning via `mutationIds`, rollback by
projection, submission ordering, cold-base holding, resync pruning on
generation change, TTL safety) are encoded once instead of per feature:

```ts
const tree = optimistic(remoteFiles({ workspaceId }).states.tree);

// One call: apply recipe → invoke mutation → prune on settled, drop on failure.
await tree.run(model.mutations.rename, { from, to }, optimisticRename);
```

The overlay is "just another readable" — the payoff of uniform composition.
The recipes (`optimisticRename`, …) are the same shared reducers the host
uses for `settle` (example 2), and because they apply via Immer, unaffected
subtrees stay reference-equal — which the renderer's granular reconciliation
below depends on.

## Renderer integration (MobX)

The renderer keeps MobX as its reactive system; the kernel graph ends at
`remote`. Running two graph systems for view logic would be a permanent
impedance mismatch, so the boundary is explicit — **kernel up to `remote`,
MobX below** — with a bridge of two layers, each preserving the granularity
the previous one established:

1. **Node level — one MobX atom per remote state** (`createAtom`): the kernel
   `observe` callback calls `reportChanged()`; observer components re-render
   per node. The atom does **not** drive kernel demand — see below.
2. **Entity level — identity-based reconciliation**: the replica applies
   Immer patches, so consecutive snapshots are structurally shared —
   unchanged entities are reference-equal. A generic reconciler walks new
   snapshots into keyed `observable.map`s and skips `prev === next` entries;
   a row component reading `store.tasks.get(id)` re-renders only when *that*
   task changed. The pipeline: wire patch → structural sharing →
   identity-skip reconciliation → per-entity MobX invalidation → per-row
   render.

**Demand comes from pins, not from rendering.** Render observability
(`onBecomeObserved`) is high-frequency and semantically meaningless; fetches
are expensive and pending state needs an owner. So view-scope instantiation
`pin`s the models the view needs (fetch starts at navigation, before render),
scope disposal releases them, and `prefetch` warms models on intent (hover,
palette selection). Reading an unpinned model renders `undefined` and warns
in dev. See [01-concepts.md §6](./01-concepts.md#demand-is-a-policy-not-a-rendering-accident)
and [`pin`/`prefetch`](./02-primitives.md#pin-and-prefetch).

**Where to normalize.** Wire models stay coarse volatility-split slices (a
view is renderable from one or two pinned models); renderer stores normalize
them into entity maps via the reconciler; view models join in MobX
`computed`s (row = task ⋈ activity ⋈ workspace stats) — the renderer-side
analogue of `derived`. Rule of thumb: **normalize where data is *held*
(stores), denormalize where it *travels* (wire), join where it is *consumed*
(computeds).** The initialization tension dissolves because pins and scoped
stores share one lifecycle: the view scope's instantiation both creates the
scoped store and pins the slices that feed it; stores are passive (they
reconcile what pinned models deliver, never fetch), so store lifetime = pin
lifetime = scope lifetime.

## Status propagation in practice

A join like `fileTree` is `'live'` only when every listing it read is live; a
single revalidating directory makes the tree `'stale'` (with the previous
entries still present as values). Consumers get honest per-refresh semantics
for free: UI can render the value and dim/spin on `status !== 'live'` without
any bespoke "isRefreshing" plumbing.

## Anti-patterns

- **`cell` mirroring a query** (`observe(q, v => c.set(v))`): creates dual
  truth. Use `derived` or use the query directly.
- **Async in `derived`**: not supported by design. Model the async step as a
  `query`.
- **Payload-carrying pokes**: a poke is a dirty bit. Payloads are `settle`s or
  event streams.
- **One mega-derived over every volatile input**: see the granularity rule.
- **`peek` to "avoid extra recomputes"** in hot paths: it usually hides a
  granularity problem; fix the shape instead.
- **Fetch-on-render**: letting render observability (`onBecomeObserved`,
  mount effects) initiate fetches for primary data. Demand belongs to
  lifecycle boundaries (`pin`), not to rendering accidents; render reads only
  invalidate.
- **Fetching stores**: renderer stores that pull their own data. Stores are
  passive reconcilers of pinned models; if a store needs data, its owning
  view scope is missing a pin.
