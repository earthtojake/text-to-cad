# The Registry is the sole writer of the workspaces table

The `workspaces` table is the Registry from ADR 0001, and its invariants (untrack-never-delete,
tombstone/revert symmetry, observation columns owned by sync, annotation columns owned by features)
were re-implemented by ten independent writers across six slices. We decided a single Registry module
owns every write through a verb vocabulary — `register` (emdash-created, with Provenance), `adopt`
(host-discovered, without), `refresh` (observations only), `untrack`/`revertUntrack`, `resurrect`,
`annotate`, and `purge` (hard delete, valid only on already-untracked rows) — with verbs accepting an
optional transaction handle so callers keep atomicity across tables. Raw drizzle access to the table
outside the module is banned by lint.

## Considered options

- **Full read/write monopoly** — rejected: read needs are join-shaped and consumer-specific
  (search wants branch names per task, sync wants live roots per host), so the interface would
  inflate into one-caller getters. Instead the Registry exports only `getLive`/`findLiveByKey`
  and a named `liveWorkspaces()` predicate that external joins must build on.
- **Writes only, reads raw** — rejected: the liveness rule ("tracked" means `untrackedAt IS NULL`)
  appeared ~26 times; when its meaning changes (e.g. excluding removal-pending rows), that must be
  a one-site edit.

## Consequences

- The positive-assertion invariant is structural, not remembered: the snapshot type consumed by
  convergence is only constructible from a successful scan, and snapshot application returns a report.
- `purge` legitimizes retention deletion of dead rows; it asserts rows are already untracked and
  throws otherwise. Untracking remains the only way a tracked row leaves the Registry.
- The `isAnnotated` predicate (task link or Provenance present) is a Registry rule, not a sync detail.
