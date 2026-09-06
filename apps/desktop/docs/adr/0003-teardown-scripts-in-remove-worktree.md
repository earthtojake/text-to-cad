# Teardown scripts run inside the removeWorktree verb

> **Superseded by ADR 0005.** Workspace removals are no longer queued offline — they are plain
> RPCs that fail fast when the host is unreachable — so the queued-offline case this exception
> existed for is gone. Teardown now runs inside `deactivateWorkspace` (kill-sessions + time-boxed
> non-fatal teardown), which the delete verbs compose server-side. The narrowing constraints
> below (non-fatal, time-boxed, only user script inside a verb) carry over to that placement.

Host verbs are pure inventory mutations — user scripts were deliberately kept out of them:
`scripts.prepare` and `scripts.setup` run in the session plane (stamped workspace
initialization), so a durable host operation never blocks on or fails from user code. We made
one exception: `scripts.teardown` executes as a stage of the `removeWorktree` expansion, between
kill-sessions and the worktree removal itself.

## Why the exception

Teardown's job is to undo what setup/run started — dev servers, containers, tunnels — and those
live on the host, surviving desktop disconnects. Removals can be queued offline: the outbox
submits `removeWorktree` when the host reconnects, possibly hours after the desktop enqueued it.
At execution time the only party present is the host, mid-verb. Every alternative placement
fails exactly the queued-offline case the outbox exists for:

- Desktop-triggered teardown at deactivation runs only when the host is reachable at enqueue
  time — silently skipped otherwise.
- Running it both at deactivation and in the verb executes user scripts twice in the common case
  and leans on an idempotency promise we chose not to rely on for prepare.

## Constraints that keep the exception narrow

- **Non-fatal**: a failed or timed-out teardown records a warning stage and the removal
  proceeds. A broken teardown script must never make a workspace undeletable.
- **Time-boxed**: the stage has a hard timeout; the verb never hangs on user code.
- Teardown remains the *only* user script inside any verb. Creation stays pure git — prepare
  and setup run in the session plane (see the legacy-path-retirement map, ticket 02).
