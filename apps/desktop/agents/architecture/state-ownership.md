# State Ownership

Emdash has two durable state authorities:

- Desktop SQLite owns desktop entities such as projects, tasks, conversations,
  and the bindings from those entities to host resources.
- Each workspace host owns the resources on its machine: repositories, worktrees,
  branches, process state, and the per-record outcome annotations its registry writes.

Do not treat a desktop workspace row as the workspace itself. For host-owned resources,
desktop rows are a materialized cache plus desktop-owned metadata and links. The host's
registry and its observations are the observed truth (ADR 0001, ADR 0005).

## Ownership Classes

| Class | Examples | Authority | Desktop row meaning |
| --- | --- | --- | --- |
| Desktop entities | project, task, automation, conversation | Desktop SQLite | The entity itself; tombstones are authoritative. |
| Host resources | repository, worktree, branch, path | Workspace host | Cached observation and optional desktop metadata. |
| Bindings | task to workspace, project to host | Desktop SQLite | A desktop-owned reference to a host resource. |

This means `deletedAt` on a desktop entity means the entity is deleted. A deletion
tombstone on a mirror row for a host resource means the desktop intends removal; the
resource exists until the host executes the delete verb or observes it gone.

## Mutation Model

Host mutations are plain fail-fast RPCs against the host's registry verbs — no durable
command queue, no operation log, no desktop-held claims (ADR 0005). Deletion is the one
host mutation that must survive host unreachability, and it does so through data, not
machinery (ADR 0006):

- Deleting a host-resident entity writes a durable **tombstone** on its mirror row,
  freezing the deletion options and the target record's UUID. The tombstoned row is the
  visible pending state and the queue; nothing else is enqueued anywhere.
- An entity-generic **reconcile sweep** runs whenever a host is reachable (boot,
  reconnect, tombstoned-while-reachable, 10-minute backstop) and calls each kind's
  idempotent delete verb for that host's tombstones, purging a tombstone only when the
  mirror confirms the host record gone.
- Verb outcomes live on host records (stage, class, message, timestamp) and sync to the
  mirror, which is the only thing the UI reads. RPC returns are loop control, never UI
  truth.

Placement follows the same line: entity knowledge, cascading intent, and user
confirmation live in desktop delete flows; disk/process facts and verb serialization
(a keyed mutex, per-repo for worktree create/delete, per-workspace for
activate/deactivate/delete) live on the host.

## Decisions

- Use one writer per resource. Convergence happens through live models and snapshot
  sync, not by merging concurrently-written state.
- Creation and lifecycle verbs fail fast against unreachable hosts; interrupted creates
  recover via the host's durable record plus idempotent client replay (same UUID,
  identical spec).
- Deletion intent is durable client data (the tombstone), converged by the reconcile
  sweep. Every tombstone has user-operable release paths: Retry and Untrack-anyway.
- Status machines are per authority, but each status set should have an explicit
  transition table and a pure severity fold for UI rollups.
- Contribute behavior through manifests and definitions. Keep shared vocabulary, such
  as statuses and outcome classes, centrally owned and mechanically reviewable.

See ADR 0005 (`docs/adr/0005-host-workspace-registry-plain-rpc-verbs.md`) and ADR 0006
(`docs/adr/0006-tombstone-and-reconcile-deletion.md`) for the full model, and the
glossary in `CONTEXT.md` for the vocabulary.
