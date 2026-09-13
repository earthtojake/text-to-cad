# Tombstone-and-reconcile deletion; the operation log retires

Deletion of host-resident entities is the one host mutation that must survive host
unreachability. It no longer rides a durable command queue: deleting an entity **tombstones
its mirror row** — a durable client-side mark carrying the frozen deletion options — and an
**entity-generic reconcile sweep** runs whenever the host is reachable, calling the owning
surface's idempotent delete verb for each tombstoned entity and purging the tombstone when
the mirror confirms the host record gone. The tombstoned row is the durable intent and the
queue; there is no ledger, no minted idempotency keys, and no drain ordering.

With that, the durable-operation machinery retires on both planes: the kernel (operation
records, claims, admission, conflict policies, dispatch, its SQLite stores), the desktop
outbox/ledger engine, the host command inbox, the desktop↔host operation bridge, and the
operation projections. Host verb handlers serialize with a `KeyedMutex` (per-repo exclusive
for worktree create/delete, per-workspace for activate/deactivate/delete, fixed
repo-before-workspace acquisition order). This supersedes ADR 0001's command clause
generally — ADR 0005 already superseded it for workspace mutations; this ADR extends the
plain-RPC + tombstone model to every host-resident entity kind (conversations included) and
removes the machinery itself. ADR 0001's snapshot half — host authority, the
positive-assertion invariant, adopt/missing convergence — stands unchanged.

## The model

- **Creation and lifecycle verbs are plain fail-fast RPCs** (ADR 0005). Nothing is queued
  for them; interrupted creates recover via the host's own durable record plus idempotent
  client replay.
- **Deletion intent is a tombstone**: written atomically at delete time on the mirror row,
  freezing the deletion options and the target record's UUID. Identity-keyed removal — the
  verb no-ops when the record at the path carries a different id — closes the
  delete-racing-create hole; a tripped guard counts as converged. Creation admission
  refuses a path carrying a pending tombstone (a data check, replacing claim conflicts).
- **The sweep is entity-generic**: one thin primitive (sweep + retry + purge), per-kind
  idempotent removal functions contributed by each registry. Triggers: boot, reconnect,
  tombstoned-while-reachable, plus a 10-minute backstop that doubles as the retry vehicle
  (per-item backoff). Failure classes are host-written on the record (transient retries
  silently; terminal stops and surfaces Retry / Untrack-anyway). No cross-kind ordering —
  verbs are self-sufficient; refusals resolve by later retry.
- **Outcomes live on host records, not operation records**: verbs annotate the record
  (stage, class, message, timestamp) before returning; the annotation syncs to the mirror,
  which is the only thing the UI reads. RPC returns are loop control, never UI truth.
- **No tombstone expiry**: the tombstoned row is visible with affordances; boundedness comes
  from visibility, the terminal-failure stop, and Untrack-anyway — not from a timer.
- **Forget-host purges mirror rows, tombstones included.**

## Consequences

- **ADR 0004 is retired.** With no outbox there is no pending desktop record to cancel;
  "cancelled" as a desktop-local terminal state disappears. The cancellations that remain
  are forget-host and Untrack-anyway (both purge intent) and aborting an in-flight create
  via the RPC signal. Orphaned host effects still surface through the observation plane —
  that half of 0004's reasoning lives on in the adoption path.
- The desktop keeps no admission guard, no claims, and no cross-client coordination; the
  only client-side concurrency mechanism is an in-memory per-tombstone single-flight marker.
  The never-implemented "Host claim" concept is dropped.
- Automation runs await the plain `createWorktree` RPC; failure attribution stays on the
  run record, fed by the RPC error.
- History becomes per-step durable last-outcomes on host records (`lastCreateOutcome`,
  `lastRemovalAttempt`, per-script outcomes) — no event list; nothing rendered one.
- Tombstones are the future multi-client sync unit for deletions: the reconcile tombstone
  and the planned remove-wins CRDT tombstone are one record, and any client may execute one
  (safe by host serialization + idempotency + mirror-confirmed purge).
- Both kernel SQLite databases drop in a hard cutover (nothing server-side is shipped).

Design detail and the guarantee-by-guarantee gap walk:
`.scratch/operation-log-retirement/spec.md`.
