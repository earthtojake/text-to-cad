# Prior Art: Registry/Command vs Desired-State Reconciliation Models

Research note supporting the workspace state-management decision: the host filesystem is
authoritative, the desktop keeps a *registry* (tracking index + desktop-only annotations),
sync is level-triggered snapshots converging the record toward the world, and host mutations
are one-shot durable commands in an outbox — deliberately *not* Kubernetes-style
spec/status convergence. All claims below are from primary sources (official docs, specs,
man pages), linked inline. Researched 2026-08-03.

> **Update 2026-08-05:** the durable-command outbox described here was itself retired.
> Host mutations are now plain fail-fast RPC verbs (ADR 0005) and offline deletion is a
> client-side tombstone converged by an entity-generic reconcile sweep (ADR 0006). The
> registry/snapshot half of this note stands; read the outbox references as historical.

## 1. Kubernetes spec/status

Source: [API conventions, "Spec and Status"](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md#spec-and-status)
unless noted.

- `spec` is "a complete description of the desired state", persisted with the object;
  `status` "summarizes the current state of the object in the system" and its fields
  "should be the most recent observations of actual state".
- Ownership is enforced structurally: spec and status "can (and usually should) have
  distinct authorization scopes" — users get write access to spec, controllers get
  read-only spec and full write on status. PUT/POST "MUST ignore the `status` values";
  a `/status` subresource MUST exist for system components to write status.
- Direction of reconciliation: "Over time the system will work to bring the `status` into
  line with the `spec`" — the world is driven toward the record, the inverse of emdash's
  registry.
- Level-based, not edge-based: the system drives toward the most recent spec "regardless
  of previous versions", explicitly "not required to 'touch base'" at intermediate values.
  Restated later: "The system is level-based rather than edge-triggered, and should assume
  an Open World." Emdash's snapshot sync borrows exactly this property (missed
  intermediate states don't matter), just pointed the other way.
- The record is existence-authoritative: "If the specification is deleted, the object will
  be purged from the system." Deleting the record deletes the world — again inverted from
  emdash, where deleting the world updates the record.
- Controllers are control loops that "watch the state of your cluster, then make or request
  changes", each trying "to move the current cluster state closer to the desired state"
  ([Controllers](https://kubernetes.io/docs/concepts/architecture/controller/)). This is
  why out-of-band deletion of a controller-managed object (e.g. a ReplicaSet's Pod) is
  repaired by recreation: the desired state still exists in the record.
- `observedGeneration` in status lets clients check whether the acting component has seen
  the latest spec — a record-side freshness marker emdash doesn't need because it has no
  standing spec.

Deletion and GC ([Finalizers](https://kubernetes.io/docs/concepts/overview/working-with-objects/finalizers/),
[Garbage Collection](https://kubernetes.io/docs/concepts/architecture/garbage-collection/)):

- Deletion is itself declarative: DELETE sets `metadata.deletionTimestamp`, returns HTTP
  202, and the object "remains in a terminating state" until every key in
  `metadata.finalizers` is removed by its owning controller; only then is the object
  actually deleted. Once `deletionTimestamp` is set, finalizers may be removed but not
  added, and "you can not resurrect this object".
- `ownerReferences` drive cascading GC: "Kubernetes checks for and deletes objects that no
  longer have owner references". Foreground deletion blocks the owner on dependents with
  `blockOwnerDeletion=true`; background deletion (the default) deletes the owner
  immediately and GCs dependents later; orphaning is an explicit opt-out.

**Assumptions the model bakes in:** a single writer owns desired state (spec authz scope);
controllers are always-on and colocated with the API server holding truth (deletion
*cannot complete* until a controller processes finalizers — a crashed controller wedges
deletion, per the finalizers doc's "stuck in a deleting state" warning); and the stored
record is authoritative for both existence and intent. None of these hold for emdash:
users mutate host filesystems directly, hosts are intermittently connected, and the host —
not the desktop DB — is truth.

## 2. Terraform state + config

Sources: [State](https://developer.hashicorp.com/terraform/language/state),
[Purpose of State](https://developer.hashicorp.com/terraform/language/state/purpose),
[terraform refresh](https://developer.hashicorp.com/terraform/cli/commands/refresh),
[Import](https://developer.hashicorp.com/terraform/language/import),
[terraform state rm](https://developer.hashicorp.com/terraform/cli/commands/state/rm),
[removed block](https://developer.hashicorp.com/terraform/language/block/removed).

- What state is FOR: "The primary purpose of Terraform state is to store bindings between
  objects in a remote system and resource instances declared in your configuration" — a
  mapping/registry, not the desired state itself. It also stores metadata (e.g. the last
  known dependency order so deleted config can still be destroyed correctly) and "a cache
  of the attribute values for all resources … done only as a performance improvement"
  (Purpose page). Terraform "expects a one-to-one mapping between configured resource
  instances and remote objects" (State page).
- Refresh converges state toward reality: "Prior to any operation, Terraform does a refresh
  to update the state with the real infrastructure" (State page); `terraform refresh`
  "reads the current settings from all managed remote objects and updates the Terraform
  state to match" and "does not modify your real remote objects" (refresh page). This is
  exactly emdash's snapshot-sync direction. The refresh page also documents the failure
  mode emdash must respect: with misconfigured credentials Terraform "may be misled into
  thinking that all of the managed objects have been deleted", dropping every tracked
  object — i.e. distinguish "can't see the host" from "host says gone".
- Adoption: `import` blocks bind "existing infrastructure resources … so that you can begin
  managing the resources as code"; you specify the remote object's identity and a state
  address, plus a matching `resource` block (Import page). Adoption is *manual and
  config-gated* in Terraform; emdash adopts untracked worktrees automatically because
  there is no config to gate on.
- Untrack without destroy: `terraform state rm` "removes the binding to an existing remote
  object without first destroying it. The remote object continues to exist but is no
  longer managed" (state rm page). The declarative form is a `removed` block; by default
  removal destroys the real resource, but `lifecycle { destroy = false }` forgets it
  "without destroying the actual resource" (removed block page). So Terraform has an
  explicit, first-class untrack-vs-destroy distinction — the same distinction emdash draws
  between silent untrack and the remove-worktree command.
- Out-of-band deletion → recreation: because config is standing desired state, forgetting
  (or losing) a binding means "a subsequent terraform plan will include an action to
  create a new object for each of the 'forgotten' instances" (state rm page). Same for
  drift: refresh records the deletion into state, and the next plan against unchanged
  config proposes creation. This is the precise behavior emdash rejects by having *no*
  standing desired state.

**Like emdash:** state as a registry/cache of reality with refresh converging record →
world; import/forget vocabulary; explicit untrack-vs-destroy. **Unlike emdash:** the HCL
config is a durable desired-state document that drives every apply, so deletion out-of-band
is drift to be repaired, not a fact to be recorded.

## 3. Git worktree administrative records

Source: [git-worktree(1)](https://git-scm.com/docs/git-worktree) (DESCRIPTION, COMMANDS,
DETAILS, LIST OUTPUT FORMAT sections); prune expiry from
[git-config(1) `gc.worktreePruneExpire`](https://git-scm.com/docs/git-config#Documentation/git-config.txt-gcworktreePruneExpire).

- Each linked worktree has a private record directory under `$GIT_DIR/worktrees/<name>`
  containing `gitdir` (pointer to the working tree) and per-worktree state (DETAILS). The
  working tree on disk plus this record together constitute "a worktree" — record and
  reality are distinct artifacts, like emdash's registry row vs the directory on the host.
- GC of stale records: "If a working tree is deleted without using `git worktree remove`,
  then its associated administrative files … will eventually be removed automatically (see
  `gc.worktreePruneExpire` in git-config), or you can run `git worktree prune`"
  (DESCRIPTION). `prune` removes "worktree information in `$GIT_DIR/worktrees` for
  worktrees whose working trees are missing" (COMMANDS). Git never recreates the deleted
  directory — out-of-band deletion is absorbed by dropping the record. This is emdash's
  silent-untrack behavior verbatim.
- Grace period: `git gc` runs `git worktree prune --expire 3.months.ago` by default;
  `gc.worktreePruneExpire` can be set to `now` (prune immediately) or `never` (suppress)
  (git-config). `prune --expire <time>` and `list` honor the same threshold. So git's
  default is *delayed* auto-untrack, a hedge against temporarily-unavailable paths —
  analogous to emdash's "missing" state before any untrack decision.
- Protection from GC: `git worktree lock` "prevent[s] its administrative files from being
  pruned automatically", also blocking move/delete, "optionally specifying `--reason` to
  explain why" (DESCRIPTION/COMMANDS). Mechanically, lock writes a file named `locked`
  containing "the reason in plain text" into the record directory (DETAILS). The stated
  use case is worktrees "on a portable device or network share which is not always
  mounted" — i.e. absence-from-disk is expected and must not be read as deletion. This is
  the exact role of emdash's annotations (task links, provenance): an annotated record is
  protected from auto-untrack and surfaces as "missing" instead.
- Observability: `git worktree list` annotates entries `locked` (with reason) and
  `prunable` (with reason, e.g. "gitdir file points to non-existent location"), including
  a stable `--porcelain` format (LIST OUTPUT FORMAT) — a UI contract for exposing
  record-vs-reality divergence rather than hiding it.
- Repair over recreate: `git worktree repair` fixes admin files that are "corrupted or
  outdated due to external factors" — reestablishing links after the main worktree or a
  linked worktree was moved manually (COMMANDS). Divergence is handled by *fixing the
  record's pointers*, never by regenerating the working tree.
- Safety interlocks: `add` "refuses to create a new worktree … if `<path>` is already
  assigned to some worktree but is missing", overridable with `--force`, twice if locked
  (OPTIONS) — stale records actively guard against identity reuse, a reason to keep
  "missing" rows visible rather than deleting them eagerly.

Git worktrees are the closest first-party precedent for emdash's model: filesystem
authoritative, record follows reality, GC with a grace period, explicit lock-with-reason
protecting records from GC, and repair (fix pointers) instead of convergence (recreate).

## 4. Other first-party prior art (brief)

- **systemd device units** ([systemd.device(5)](https://man7.org/linux/man-pages/man5/systemd.device.5.html)):
  "systemd will dynamically create device units for all kernel devices that are marked
  with the 'systemd' udev tag". The unit registry mirrors sysfs/udev reality — systemd
  never creates a device to match a unit, and if `systemd-udevd` isn't running "no device
  units will be available". `SYSTEMD_READY=0` marks a visible device as logically
  unplugged — an annotation overriding raw observation. Pure inventory model; actions on
  devices are separate units triggered by appearance (`SYSTEMD_WANTS=`).
- **mDNS caches** ([RFC 6762 §10](https://datatracker.ietf.org/doc/html/rfc6762#section-10)):
  each host's record set is authoritative for itself; peers keep TTL-bounded caches.
  Clean removal is a "goodbye" packet with TTL 0 causing the cache entry "to be promptly
  deleted" (§10.1); unclean disappearance simply ages out via TTL. Registry-of-reality
  with expiry-based GC and an explicit removal signal — no peer ever tries to make the
  network match its cache.

Both confirm the pattern: when the world is owned by someone else, mature systems keep a
mirror with GC/expiry plus an explicit removal signal, and route *actions* through a
separate channel rather than diffing against a stored desired state.

## 5. Comparison and synthesis

| Dimension | K8s spec/status | Terraform state+config | git worktree records |
| --- | --- | --- | --- |
| Authoritative for existence/intent | API object (spec) in etcd | HCL config (intent); remote system (facts) | Filesystem + `$GIT_DIR/worktrees` records |
| Reconciliation direction | World → record (status reports back) | State → world facts (refresh); world → config (apply) | Record → world (prune/repair) |
| Out-of-band deletion | Recreated by controller (spec persists) | Recreated on next apply (config persists) | Record pruned; never recreated |
| Adoption of unmanaged objects | N/A (API objects born managed) | Manual `import` + matching `resource` block | Not needed (records created only by `add`) |
| Untrack vs destroy | Orphan dependents vs cascading delete | `state rm` / `removed { destroy = false }` vs destroy | `prune` (record only) vs `remove` (record + tree) |
| GC policy | ownerReferences GC, finalizer-gated deletion | None automatic; explicit forget commands | Auto-prune after `gc.worktreePruneExpire` (default 3 months); `lock` exempts |
| Offline / intermittent fit | Poor: deletion blocks on live controllers | Moderate: refresh needs provider access; misread credentials = mass state loss | Good: records inert until next prune/list on the host |

**What emdash borrows from each:**

- From **K8s**: level-triggered snapshot semantics (converge on observed level, tolerate
  missed edges); explicit lifecycle marking on records ("missing" ≈ `deletionTimestamp`
  as a state, not an event); annotation-gated GC (annotated rows ≈ finalizer/
  `blockOwnerDeletion` protection). Rejected: spec-as-truth, recreation on out-of-band
  deletion, deletion blocked on always-on controllers.
- From **Terraform**: state-as-registry ("bindings between objects in a remote system" +
  metadata + cache); refresh direction (record converges to reality before anything else);
  the import/forget vocabulary and the hard untrack-vs-destroy distinction; the
  unreachable-vs-deleted caution from the refresh docs. Rejected: config as standing
  desired state driving apply.
- From **git worktree**: nearly the whole shape — filesystem authoritative, admin records
  as the registry, auto-prune of records for vanished directories with a grace period,
  lock-with-reason protecting records that matter (≈ emdash annotations), repair-not-
  recreate, and stale records guarding path identity. Emdash's outbox commands are the
  one element with no git analogue (git's `remove` is synchronous); Terraform's plan/apply
  of destroy actions and K8s finalizer-gated deletion are the closest precedents for
  durable, idempotent teardown commands.
