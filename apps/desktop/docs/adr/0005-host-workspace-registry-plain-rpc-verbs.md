# Host-side workspace registry with plain-RPC lifecycle verbs

Each host runs a workspace registry: a sole-writer runtime over its own durable store, holding
registered paths plus host-computed observations (branch, dirty, ahead/behind, changed lines
including untracked files), published to desktops through a single `records` live model that
merges the durable rows with an in-memory runtime overlay (creation progress, activation state,
notices). The filesystem remains the source of truth — the registry observes it and auto-adopts
worktrees of registered repositories; it never converges the world toward a record (ADR 0001's
host-authoritative stance is unchanged). The desktop keeps its mirror + annotations and applies
each delivery as a full snapshot through the registry sole writer (ADR 0002's verbs stay).

Workspace lifecycle is six task-independent verbs — `createWorkspace`, `createWorktree`,
`activateWorkspace`, `deactivateWorkspace`, `deleteWorkspace`, `deleteWorktree` — modeled as
**plain wire RPCs**. This supersedes ADR 0001's transport clause ("mutating host state happens
only through one-shot durable commands in an outbox") for workspace mutations: no inbox/outbox,
no durable operation log, no liveJob endpoints. Handlers serialize exclusively per-repository
for worktree create/delete and per-workspace for activate/deactivate/delete (waits, not
errors). *(ADR 0006 fixed the implementation: a `KeyedMutex` with fixed repo-before-workspace
acquisition order — the kernel claim machinery retires entirely.)*

## Canonical registration and production cutover

`createWorkspace` registers an existing path and returns the Host's canonical record. The desktop
may propose an id, but a path already owned by another id is a successful canonical resolution, not
an error: every caller persists the returned record. Replaying the same id and path is idempotent;
reusing an id for another path remains an immutable-identity error. `createWorktree` stays strict
because it creates an artifact rather than registering one that already exists.

The desktop Registry Claims only Host-acknowledged records. Claim inserts or refreshes the canonical
id on the same Host, accepts the Host's canonical path spelling, may explicitly retrack an untracked
id, and refuses a pending deletion Tombstone or another live id at the path. Claim never changes a
row's Host attachment. Project relink is a separate explicit Retrack: the destination Host must
return the same UUID for every linked path before one desktop transaction changes the attachment.
Normal snapshot Observe matches by id only. It preflights path ownership before any writes and stops
the Host attachment on an identity collision instead of path-relinking or repeatedly hitting
SQLite's unique index.

The shipped desktop-owned Workspace shape requires one production cutover before Observe attaches.
That backfill classifies legacy rows, preserves dependency closure, registers existing paths
parent-first, accepts Host-returned canonical ids, and atomically translates Project, Task,
child-parent, and config bindings. The first released Host registry starts empty, so the ordinary
single-desktop cutover preserves every legacy id; translation exists for a Host that already learned
the path during that cutover, including another desktop or scanner adoption. A legacy row whose path
is absent or already missing stays
desktop-side; normal Observe missing/untrack rules apply after cutover. The cutover never manufactures
a Host record without an artifact to inspect. A versioned per-Host completion marker is written only
at a stable fixed point; failures gate snapshot and reconcile attachment. One internal path-based
UUID translation seam serves exactly two explicit workflows: the production backfill and repository
initialization when the Host resolves the Project path to another canonical record. It moves every
desktop binding transactionally and remains outside the general Registry API; Claim and Observe
never call it.

## Why plain RPCs

The outbox existed to survive two gaps: desktop-to-host disconnection at enqueue time, and
daemon interruption mid-execution. Both are now handled without durable commands:

- **Unreachable host → fail fast.** Every verb returns a typed `host-unreachable` error and this
  design queues nothing. A workspace-specific pending-intents queue ("mini-outbox") was
  considered and rejected: it reintroduces the exact machinery this design removes. "Removal
  pending" leaves the workspace vocabulary. The system-wide offline-delete answer — durable
  client-side tombstones swept by an entity-generic reconcile loop (operation-log-retirement
  effort) that calls these delete verbs when the host is reachable — composes with this contract
  rather than changing it; idempotent deletes are what make that sweep safe to repeat.
- **Interruption → durable fact records, client-driven retry.** `createWorktree` registers its
  record at the start (`lastCreateOutcome: 'started'`) and records `succeeded` or
  `failed(stage, error)` durably. An interrupted creation is visible in the registry after
  restart; recovery is a client replay (same UUID + identical immutable spec re-executes;
  a succeeded one no-ops; a divergent spec errors). The host never re-converges on its own —
  outcomes are facts, not desired state.

Progress needs no job objects: callers watch the `records` live model, whose runtime overlay
carries creation stage and activation script states. After a daemon restart the overlay is
simply absent — activation is ephemeral by design (`lastActivatedAt` is an observation, never
a durable "active" flag).

## Consequences

- `deactivateWorkspace` is the sole owner of kill-sessions + time-boxed non-fatal teardown;
  the delete verbs compose it server-side. This retires ADR 0003 (teardown inside the
  removeWorktree verb): 0003's rationale was the queued-offline removal, which no longer exists.
- Deletes are idempotent (absent id succeeds) and never refuse for dirty/unpushed state;
  informed confirmation is the client's job, powered by mirror observations — no preflight RPC.
- `deleteWorkspace` never touches disk; `deleteWorktree` is the only artifact-destroying verb.
- Project creation and Pick are Host-first: Host registration precedes one local transaction that
  Claims the canonical Workspace and inserts the Project binding.
- Automation adoption resolves the workspace through the Host and Claims the returned canonical
  record; it never creates a desktop-only Workspace identity when snapshot sync has not arrived.
- Activation and config reads never create an unknown Workspace as a compatibility fallback.
- Desktop-side scan tiers, the workspace snapshot pull sync, and the workspace outbox
  definitions retire; freshness (fs-events primary, activity-gated escalation, polling floor,
  explicit refresh verb) is a host concern.
- Retiring the outbox for anything else (conversations delete) is a separate effort; until then
  the two transports coexist, scoped by domain.
