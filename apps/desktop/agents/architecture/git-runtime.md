# Git Runtime Architecture

Git is split into a transport contract and a host-scoped runtime. Renderer, desktop, and
workspace-server code share the Wire vocabulary without importing Git execution, canonical host
paths, watchers, or lease ownership.

## Ownership

- `packages/core/src/runtimes/git/api/` owns selectors, contracts, serialized states, inputs,
  results, errors, and client-used pure helpers.
- `packages/core/src/runtimes/git/node/` owns provisioning, identity resolution, canonical
  resources, watchers, reconciliation, Git execution, and `gitComponent`.
- `packages/wire/` owns live-state publication, `ComputedLiveState`, resource-backed live-model
  hosts, mutation cursors, jobs, replicas, and transport behavior.
- Portable API modules never import Node runtime implementation code. Canonical identities and
  canonical host paths are runtime-only.

## Runtime Shape

`GitRuntime` is the host-scoped composition root. It exposes three deep entry points:

- `provisioning` inspects, initializes, and clones paths before a canonical resource exists;
- `repository` resolves repository selectors and serves repository procedures, jobs, and live
  models;
- `checkout` resolves checkout selectors and serves checkout procedures, jobs, and live models.

The API layer delegates directly to these entry points:

```ts
getLog: (input) => runtime.checkout.getLog(input)
```

It does not acquire leases, classify effects, dispatch mutation names, or translate cursors.

## Canonical Resources

`GitAllocationGraph` is a private resource registry. It resolves path aliases, pools resources by
canonical identity, retains a repository for every checkout, applies the idle TTL, and disposes
failed or idle resources.

The pooled values are deep resource objects:

1. `RepositoryResource` represents one canonical common Git directory. It owns repository live
   states, the common-directory watcher, repository-family command ordering, object-store locking,
   active checkout registration, explicit repository operations, and their reconciliation.
2. `CheckoutResource` represents one canonical worktree. It owns checkout live states, the
   worktree watcher, file-diff staleness, explicit checkout operations, and their reconciliation.

The checkout head state is authoritative for the current branch's canonical full ref, configured
upstream, tracking ref, and divergence. Upstream state distinguishes local tracking from remote
tracking; only a remote upstream means the branch is published. Repository refs are inventory for
branch selection and repository policy; they are not joined with checkout state to infer whether
the current branch is published. Current-branch publication resolves the checked-out full ref on
the host and travels through the dedicated checkout publication job.

Repository identity is the canonical common Git directory. Checkout identity combines the
canonical checkout root and private Git directory. Linked worktrees share one repository resource
while retaining distinct checkout resources.

`GitRepository` and `GitCheckout` are the low-level command drivers composed by those resources.
They build commands, invoke `BoundExec`, parse output, and return typed operational results. They do
not own Wire hosts, resource leases, or cross-state reconciliation. `GitRepository` lazily keeps a
repository-scoped `git cat-file --batch` process for repeated blob reads; process creation remains
owned by `BoundExec`, so repository scoping and dynamic executable selection apply uniformly.

## Live Models

Wire's `expose()` (from `@emdash/wire/state`) adapts keyed, externally authoritative resources to
live models as a `LeasedLiveModelProvider`. It owns generic resource acquisition, keyed state
retention, mutation idempotency, typed handler dispatch, and settled cursor construction.

Git supplies exhaustive mutation-handler maps:

```ts
mutations: {
  stage: (context) => context.resource.stage(context),
  commit: (context) => context.resource.commit(context),
}
```

Each resource method receives its exact contract input. There is no untyped envelope, mutation-name
switch, or Git-side input cast. Mutation-free file-diff models use the same host without a fake
mutation implementation.

## Reconciliation

Reconciliation is local to the operation that changes external Git state:

- staging operations synchronously refresh and settle checkout status, then invalidate affected
  file diffs;
- history-changing operations invalidate checkout status, head, mutable-ref file diffs, and
  repository refs as appropriate;
- repository ref operations invalidate active linked checkouts;
- jobs reconcile immediately after success or partial failure according to their own semantics;
- successful current-branch publication refreshes checkout head before the job settles, and the
  invoking renderer performs an additional head refresh as its observation barrier;
- filesystem watchers call the same direct resource invalidation methods.

There is no operation classifier or global effect plan. Small shared methods such as
`historyChanged()` express repeated domain effects without redispatching on operation names.

## Error Model

Declared Git command failures and selector-resolution failures use contract `Result` channels.
`api/errors.ts` recognizes only `ExecError` and `GitResolutionException` at runtime boundaries.
Programming errors, broken invariants, unexpected watcher failures, and callback bugs keep
throwing and are recorded by Wire as causes.

## Source Organization

- `git-runtime.ts` is the host-facing composition root.
- `api/` contains controller composition and thin procedure delegates.
- `allocation/` contains canonical identities, selector resolution, pooling, parent retention, and
  idle disposal.
- `repository/` contains the repository manager, canonical resource, command driver, family
  scheduler, watcher classifier, provisioner, and repository operations.
- `checkout/` contains the checkout manager, canonical resource, command driver, file-diff registry,
  and checkout operations.
- `exec/` contains Git process construction and scoping, operation context, and transfer progress.

Only runtime and component composition are exported from `@emdash/core/runtimes/git/node`.
Allocation, resources, and command drivers remain implementation details.
