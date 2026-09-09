# Host-authoritative workspaces: the inventory-and-command model

> **Partially superseded by ADR 0005 and ADR 0006.** The host-authoritative stance, the
> rejection of spec/status convergence, and the registry consequences below all stand. The
> transport clause — "mutating host state happens only through one-shot durable commands in an
> outbox" — no longer holds at all: mutations are plain fail-fast RPCs (0005 for workspace
> verbs, 0006 generally), and deletion intent survives unreachability as a durable client
> tombstone swept by a deletion-only reconcile loop (0006). The durable index also now lives
> host-side (the workspace registry), with the desktop keeping a mirror + annotations.

Workspaces (repos, worktrees, directories) live on hosts that emdash shares with humans and other tools. We decided the host is authoritative for what exists: the desktop keeps a *registry* — a tracking index of discovered reality plus desktop-only annotations — and sync converges the *record* toward the *world* (adopt untracked worktrees, mark tracked-but-gone rows missing). Mutating host state happens only through one-shot durable commands in an outbox (idempotent by deterministic id, executed when the host is reachable, cancelled when the host is forgotten). Desktop-owned records (tasks, automations, projects) delete immediately and never block on a host.

## Considered options

The Kubernetes-style spec/status model (record is desired state; controllers converge the world toward it) was explicitly rejected, for three reasons:

1. **Emdash is a guest on the host, not the owner.** A convergence controller would fight the user — recreating worktrees they deleted, removing worktrees they made by hand. What the user does to the host is fact, not drift.
2. **Convergence assumes an always-on controller colocated with the truth.** The desktop is intermittently connected and sometimes permanently gone. The only standing loop we keep (orphaned-session GC) runs host-side for exactly this reason.
3. **Multi-writer desired state is incoherent.** Both emdash and users create worktrees; a spec model would need desired state backfilled for artifacts emdash never asked for. In our model creation provenance is optional (`config` is NULL for adopted workspaces).

Prior art and detailed comparison (K8s API conventions, Terraform state, git's own worktree admin records): `agents/research/reconciliation-models.md`. Git's worktree tracking is the closest precedent — filesystem-authoritative records, auto-prune of stale entries, lock-with-reason protecting annotated ones.

## Consequences

- **Positive-assertion invariant**: a snapshot is a positive assertion about what exists; a failed, partial, or errored scan writes nothing to the registry. "Host reachable but the scan errored" must be indistinguishable from "host unreachable" — never from "the repo has no worktrees". This is the guard against the mass-drop hazard Terraform documents for misconfigured refresh.
- **Immediate pure-mirror untrack**: never-annotated adopted rows are untracked on the first confirming snapshot (no git-style grace period) — they are reconstructible by the next scan, and the positive-assertion invariant already blocks the failure mode a grace period would hedge.
- Registered rows with desktop annotations are never auto-deleted; they surface as missing until the user untracks them.
- Out-of-band deletions are recorded, never repaired; out-of-band creations are adopted, never reverted.
