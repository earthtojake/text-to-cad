# @emdash/wire Examples

These examples show the public surface of `@emdash/wire`. Every example imports
the package entrypoints only (`/rpc`, `/live`, `/state`, via their in-repo
source paths) and splits the authoritative server side from the client-side
binding so the boundary looks like a real transport without adding an adapter.

## Documentation

For conceptual docs that explain how the examples fit together, see
[../docs/README.md](../docs/README.md).

Run them from the repository root:

```bash
pnpm --filter @emdash/wire run example:state-kernel
pnpm --filter @emdash/wire run example:live-log
pnpm --filter @emdash/wire run example:event-stream
pnpm --filter @emdash/wire run example:mailbox
pnpm --filter @emdash/wire run example:cancellation
pnpm --filter @emdash/wire run example:api-definition
pnpm --filter @emdash/wire run example:dedupe
pnpm --filter @emdash/wire run example:job-contract
```

Examples:

- `state-kernel/` demonstrates the state kernel end to end: `cell` + `family`
  + `expose` on the server, `remote()` + `observe` + `optimistic` on the
  client, including an optimistic mutation settling against the authoritative
  cursor.
- `live-log/` demonstrates a contract-level `liveLog()` endpoint served by a
  `LiveLogSource`, consumed through `createLiveLogReplicaCache` and
  `ReplicaLog`.
- `event-stream/` demonstrates a contract-level `eventStream()` endpoint served
  by `createEventStreamHost` with client-side subscribe and gap handling.
- `mailbox/` demonstrates bounded local producer/consumer handoff, graceful close,
  and explicit overflow.
- `cancellation/` demonstrates procedure cancellation with `AbortSignal` and
  server-side abort on disconnect.
- `api-definition/` isolates contract definition with `defineContract`,
  `procedure`, `liveModel`, `liveLog`, and live model contract
  mutations.
- `dedupe/` demonstrates server-side `deduplicate()` middleware from
  `@emdash/shared/requests` for in-flight procedure calls.
- `job-contract/` demonstrates the contract-level `liveJob()` endpoint with start,
  progress, cancellation, terminal result, and reattach.
- `scope/` and `resource-cache/` demonstrate the `@emdash/shared/concurrency`
  primitives the live layer builds on.
