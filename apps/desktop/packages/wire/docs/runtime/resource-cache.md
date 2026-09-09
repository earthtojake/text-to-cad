# Resource Caches

`ResourceCache`, `SharedResource`, and `AsyncCache` are Shared primitives from
`@emdash/shared/concurrency`. Wire uses them for shared lifetimes and cached
async values, but they do not define Wire protocol messages.

## Choose A Primitive

- Use `ResourceCache<K, T>` for keyed resources that need leases and teardown:
  process sessions, replicas, file watchers, tree resources, and connection pools.
- Use `SharedResource<T>` for one lazily created resource with the same lease
  semantics: a lazy worker, singleton client, or shared runtime helper.
- Use `AsyncCache<K, T>` for data without finalizers: auth status probes,
  metadata lookups, or other retryable reads.
- Use `deduplicate()` middleware only when you want in-flight sharing without
  retaining successful values.

## Resource Identity

Every input that can change provisioning must be part of `K` or captured by the
factory closure. The cache only receives `acquire(key)`, so there is no separate
creation context:

```ts
const logins = createResourceCache({
  key: (key: { providerId: string; methodId: string; generation: string }) =>
    `${key.providerId}:${key.methodId}:${key.generation}`,
  create: async (key, scope) => {
    const pty = await startLoginPty(key.providerId, key.methodId);
    scope.add(() => pty.dispose());
    return pty;
  },
});
```

## Scope Ownership

Each cache owns an internal scope. Each entry gets a child scope, and creation runs
under `scope.run('create', ...)`. Register teardown on the entry scope as soon as
resources are acquired. If creation fails, the entry scope is disposed and the
next acquire retries.

`invalidate(key)` and `dispose()` force-close entries even if leases are still
held. Releasing a stale lease later is a no-op. This keeps owner shutdown from
waiting forever on leaked consumers.

## Lease Behavior

- Concurrent `acquire(key)` calls share one in-flight creation.
- Every acquire receives its own idempotent lease.
- `peek(key)` returns only completed active values.
- Failed creation is not cached.
- `idleTtlMs` retains a zero-ref entry briefly so flapping demand can reuse it.
- Acquiring during teardown waits for teardown to finish, then provisions fresh.

## AsyncCache

`AsyncCache` shares concurrent loads and caches only successes:

```ts
const statuses = createAsyncCache({
  key: (providerId: string) => providerId,
  ttlMs: 15 * 60 * 1000,
  load: (providerId, signal) => checkAuthStatus(providerId, { signal }),
});
```

`get()` uses a cached value when fresh, `refresh()` cancels the current load and
starts a new generation, `set()` publishes an explicit value, and failures are
never retained.
