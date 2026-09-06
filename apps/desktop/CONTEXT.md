# Emdash

Emdash runs AI coding agents in parallel across isolated git worktrees on local and remote machines. The desktop app coordinates; workspace hosts execute.

## Language

### The model

**Inventory-and-command model**:
Emdash's state model for host artifacts: the host's inventory is authoritative — for Workspaces indexed by the Host registry — the desktop Registry converges toward it, and there is no standing desired state: emdash never re-converges the world toward a record. Mutations are plain fail-fast wire RPCs (ADR 0005), with one deliberate exception: deletion intent survives unreachability as a Tombstone, swept by the Reconcile sweep (ADR 0006). Creation never converges; only tombstoned deletions do. See ADR 0001 for the authority stance.
_Avoid_: Spec/status, desired state, converging the world toward a record (the one convergence loop removes tombstoned artifacts, nothing else)

### Places and artifacts

**Host**:
A machine emdash can reach and run commands on — the local machine or an SSH-connected remote. Authoritative for everything that physically exists on it.
_Avoid_: Machine (UI label only), server, remote (as a noun)

**Host diagnostics**:
Read-only health facts about a Host: resource metrics and system-dependency detection/install status. Scoped to the Host, not to machine connections — the local host has diagnostics too (the System settings tab). Owned by the `host-diagnostics` slice; the machine details view embeds it.
_Avoid_: Machine metrics (diagnostics are not connection-specific), system (too generic)

**Repository**:
A git clone on a host. A host artifact — not the same thing as a Project.
_Avoid_: Project (that is a desktop grouping), repo root

**Worktree**:
A git worktree of a Repository on a host.

**Git ref**:
The canonical full name of a Git reference (`refs/heads/...`, `refs/remotes/...`, or
`refs/tags/...`). Observed refs store this identity; short names are derived only at display or
selector boundaries and never establish identity or equality.
_Avoid_: Using `refname:short` or a display label as canonical identity

**Checkout upstream**:
The configured relationship from the current local branch to another ref. It is explicitly local
(`branch.<name>.remote = .`) or remote; only the remote form means the branch is published. Tracking
may be resolved (OID and divergence are known) or unresolved while the upstream remains configured.
_Avoid_: Inferring publication from repository ref inventory, treating every upstream as published, collapsing unresolved tracking to no upstream

**Workspace**:
A working directory on a host that emdash tracks — a repository, a worktree, or a plain directory. The place sessions and agents run in.

**Session**:
A running process (terminal or agent process) attached to a Workspace on a host. Host-owned; dies with its workspace.
_Avoid_: Conversation (that is the durable record a session carries forward)

**Session materialization**:
The Host-authoritative fact that an explicit command or recovery intent tried to make a
Conversation's Session live by starting fresh or resuming its last-observed provider pointer. Its
metadata-only outcome says whether continuity was fresh, restored, definitively unavailable, or
ambiguous; it does not imply any Prompt outcome.
_Avoid_: Session (the running process produced by a successful materialization), Prompt attempt

**Session generation**:
The monotonically increasing fence for one Conversation's live Session incarnation. Replacement
or rematerialization advances it so late work from an older incarnation cannot change current
Conversation state.
_Avoid_: Provider connection generation (one provider connection may carry multiple Sessions)

**Provider connection generation**:
The fence for one lifetime of a pooled provider connection, shared by every Session it carries.
Provider evidence is current only when both its Session generation and provider connection
generation match.
_Avoid_: Session generation

**Conversation**:
A durable record of an agent exchange, attached to a Workspace. One Conversation outlives its Sessions — the successive live processes that carry it; resuming starts a new Session of the same Conversation. Identified by its own id for its whole life; any provider session handle it holds is a last-observed pointer, not its identity.
_Avoid_: Session (a conversation is not a process), using the provider's session id as the conversation's identity

**Prompt**:
An immutable logical user request within a Conversation. A deliberate resend creates another Prompt
attempt for the same Prompt; editing accepted queued content supersedes it with a new Prompt.
_Avoid_: Prompt attempt (one accepted opportunity to execute the request), local draft

**Prompt attempt**:
One immutable, Host-accepted opportunity to execute a Prompt. It has its own identity, acceptance
order, lifecycle, and provider outcome; multiple Attempts for one Prompt never collapse.
_Avoid_: Prompt, retrying or editing an Attempt in place

**Prompt acceptance order**:
The immutable total chronology in which the Host accepted Prompt attempts from every Desktop
writer. It never changes when the pending queue is edited or reordered.
_Avoid_: Prompt queue order

**Prompt queue order**:
The revisioned, mutable dispatch order of accepted Prompt attempts that have not crossed provider
dispatch. It is shared by every Desktop writer and distinct from acceptance chronology.
_Avoid_: Per-Desktop queues, Prompt acceptance order

**Prompt supersession**:
The atomic pre-dispatch replacement of one accepted queued Prompt attempt with a newly identified
Prompt and Attempt in the same queue slot. The old Attempt remains an immutable
`superseded-before-dispatch` fact.
_Avoid_: Editing accepted content in place, cancellation

**ACP Conversation command**:
An immutable, Desktop-minted request for the Host Conversation owner to make one ACP lifecycle
transition. Its command id names delivery of that exact request: an identical duplicate returns the
same durable result, while changed content under that id is a conflict.
_Avoid_: Provider command (an internal effect after the Host transition), treating a retry as new
user intent

**Command receipt**:
The metadata-only, Conversation-lifetime record of one ACP Conversation command's authoritative
result. It binds the command id to its writer, command kind, envelope hash, evaluated or committed
revision, and outcome without retaining Prompt content.
_Avoid_: Provider receipt, transient Wire response

**Plugins**:
One word, three homes — say which one you mean: the capability framework (`@emdash/shared/plugins`), the concrete agent providers (`@emdash/plugins`), and the host services that install and run them (`packages/core/src/services/agent-plugins`).
_Avoid_: Unqualified "plugins" where the home matters

### Desktop concepts

**Project**:
The desktop-side grouping that organizes tasks around a repository. An app concept only.
_Avoid_: Using "project" to mean the git repository on disk

**Project context**:
The desktop-owned live context of a registered Project: the shell and desktop facts that remain
available regardless of Host reachability. Failure to reach or inspect the Host never makes the
Project context unavailable.
_Avoid_: Project mount (conflates desktop availability with Host attachment)

**Project context error**:
A typed failure to construct a Project context from durable desktop data. Limited to an invalid
Project record or failed desktop context hydration; it is the only Project failure class that may
replace the normal shell.
_Avoid_: Classifying Host, attachment, or Repository access failures as Project context errors

**Host attachment**:
The per-Project runtime link to its Host, independent of the Project context. An established
attachment survives an ordinary Host disconnect; Host-dependent capabilities report the temporary
loss and resume when transport reconnects.
_Avoid_: Treating SSH connection state as Project availability

**Task**:
A desktop-owned unit of agent work, linked to the Workspace it runs in.

**Task name**:
The human-readable, single-line label for a Task. It accepts Unicode text, spaces, punctuation, and
capitalization up to 256 user-perceived characters; it is not a Git identifier.
_Avoid_: Slug, branch name, normalizing display text to satisfy Git

**Task branch name**:
The Git-safe branch ref used when a Task creates or uses a branch. It may be derived from the Task
name but remains a separate, independently editable value.
_Avoid_: Task name, treating branch normalization as display-name validation

**Desktop writer**:
The opaque, stable identity of one Desktop profile when it issues Host Conversation commands,
shared by that profile's windows. It supplies attribution, not authorization; the authenticated
Host connection remains the security boundary.
_Avoid_: Wire connection id (transient), user identity, treating writer identity as an ACL

**Command palette**:
The desktop's unified search surface for actions, tasks, projects, conversations, and files. Empty-query suggested actions are a curated idle list, not the catalog.
_Avoid_: CMDK (the library), treating idle as the full command catalog

**Keyword mode**:
A command-palette query restricted to one kind by an `@kind` prefix (`@files`, `@commands`, `@tasks`, `@conversations`, `@projects`).
_Avoid_: Scoped search (Scope is the ownership primitive), treating `@` as a sixth provider

**Host (services/hosts)**:
`src/core/services/hosts` owns machine lifecycle and workspace-server provisioning under the Host vocabulary (`HostService`, the `hosts` wire domain) — the merged home of the former `remote-machine` and `workspace-server` services. "Machine" remains a UI label only. Host (wire) remains the separately-scoped wire term.
_Avoid_: Machine (outside UI labels), "remote" as a noun

**Host availability**:
The Hosts-domain fact describing whether a Host runtime can currently serve desktops. SSH connected
only begins preparation; availability becomes ready after the runtime handshake. The Hosts domain
owns bounded recovery and an explicit session-scoped suspension after user Disconnect.
_Avoid_: Treating SSH connection state as runtime readiness, copying availability into each Project

**Desktop Secret Authority**:
The desktop-owned authority over user Secret references, storage backends, Host grants,
rotation and revocation, and the aggregate audit history. Desktop-only consumers resolve
through it directly; Host-executed consumers reach it through the Host Secret Runtime.
_Avoid_: Treating the desktop store as the process-injection layer, separate local and
remote secret authorities

**Host Secret Runtime**:
The Host-owned capability that authorizes and delivers granted Secrets to Git, agents,
scripts, and configuration materialization on that Host. The same capability serves the
local Host and SSH-connected Hosts; locality changes transport and offline availability,
not ownership or the consumer path.
_Avoid_: Remote secrets service, calling desktop secret storage directly from Host-executed
consumers

**Host registry**:
A host's durable, sole-writer index of its Workspaces: registered paths plus host-computed Observations, pushed to desktops as one live model that merges the durable records with the Runtime overlay. The filesystem stays authoritative — the registry observes it (adopting and un-adopting worktrees), never converges it toward a record. See ADR 0005.
_Avoid_: Source of truth (the filesystem is), desired state

**Registry**:
The desktop's mirror of each Host registry plus desktop annotations (task links, Provenance, client config) — never the authority on what exists on a host.
_Avoid_: Spec, expected state, source of truth (for host state)

**Mirror kernel**:
The lean shared machinery behind the per-kind Registries: the per-host sync attachment service, the `sweepUnseen` helper (grace window + the missing/untrack split), guard fragments, and the contract test suite every kind's registry must pass. Claim/Observe upserts and snapshot-apply functions stay hand-written per kind — the suite, not shared code, is what keeps the two stacks from drifting. It converges the mirror toward host Observations and is never an authority.
_Avoid_: Sync kernel (that is the client↔client CRDT plane), Registry kernel (invites confusion with the Host registry, which is the authority the kernel is not), verb-building framework (deliberately rejected for exactly two kinds)

**Host records kit**:
The lean helper set in `packages/core` that sole-writer host runtimes compose in — the records publication helper (cell + expose + publish, guaranteeing the snapshot-on-subscribe `records` semantics the Mirror kernel's sync attachment assumes) and the idempotent-delete helper. Deliberately not a framework: runtimes stay hand-written, and the idempotent-create replay rule is a stated contract with per-kind implementations.
_Avoid_: Host kernel (there is no host-side counterpart to the Mirror kernel), runtime scaffold/base class

**Session lifecycle chassis**:
The one deep module behind the session-shaped runtimes' lifecycle glue — activity tracking, idle sweeping, intent persistence, reporter fan-out, and eviction — replacing the per-runtime copies. Keyed by Session, so it serves terminals as well as agents; Conversation concerns (intents, reporter, reconcile) are one optional block that a subset consumer omits. Eviction runs a named per-key resource list and always reports the session's end, so teardown and reporting cannot drift.
_Avoid_: Conversation lifecycle (terminals carry no Conversation), framework/base-class framing (runtimes stay hand-written and drive it)

### State vocabulary

**Host fact**:
State a host is authoritative for: existence of artifacts, git state, sessions. The desktop only caches it.

**Observation**:
A Host fact computed on the host, held in its Host registry, and mirrored into the Registry — stamped with when it was last observed. Never authoritative; staleness is expected and displayed, not hidden. Changed-line stats count untracked files' lines as additions.

**Runtime overlay**:
The in-memory, per-Workspace host state merged into the Host registry's live model: creation progress, Activation phase and script states, Workspace notices. Ephemeral by design — absent after a daemon restart. The only progress surface for workspace verbs; there are no job objects.
_Avoid_: Persisting "active" as a durable flag (lastActivatedAt is an Observation)

**Provenance**:
The immutable record of what emdash asked for when it created a Workspace (stored as its config). Absent for adopted workspaces.
_Avoid_: Intent (nothing on the desktop expresses ongoing intent about host state)

**Adoption**:
The Host registry recording a Workspace that exists on disk but was not registered through a verb. Automatic and unconfirmed for worktrees of a registered Repository, performed by the host's own scan; adopted records follow the disk (deleted when the artifact vanishes). Repositories and plain directories are only ever tracked by explicit action.

**Register**:
Creating or resolving a Host registry record for a path through a create verb. The desktop proposes an id, but the Host returns the canonical record for the path and the desktop persists only that id. Registered records survive a vanished path as Missing. Provenance stays a desktop annotation on the mirror row; the Host record keeps only the minimal immutable creation fields replay is enforced against.

**Purge**:
Hard-deleting already-untracked Registry rows as retention cleanup. Never valid on tracked rows — untracking is the only way a tracked row leaves the Registry.

**Missing**:
A registered Workspace whose path a reachable host reports as gone. The Host registry keeps the record (observedStatus missing) until a delete verb removes it; adopted records are instead deleted outright — pure mirror entries follow the disk.

**Tracked / Untracked**:
Whether a host artifact has a Registry entry. Untracking is a desktop decision about the Registry; deleting is a host verb against the artifact.

**Identity lost**:
A Registry row whose Host can no longer be decoded — a remote row whose SSH connection was deleted, or a row with no location. Never reinterpreted as local: host-mutating flows refuse, a Project whose Repository row is identity-lost is skipped like a missing one, reads surface the loss rather than guess.
_Avoid_: Falling back to local, empty connection ids

### Operations

**Workspace verb**:
One of the six lifecycle RPCs on the Host registry contract: createWorkspace, createWorktree, activateWorkspace, deactivateWorkspace, deleteWorkspace, deleteWorktree. Fail fast when the host is unreachable — nothing is queued. Handlers serialize with a keyed mutex (per-repo exclusive for worktree create/delete, per-workspace for activate/deactivate/delete; waits, not errors); killing dependent sessions is part of deactivate, which the delete verbs compose server-side. Deletes are idempotent and identity-keyed (a different record id at the path no-ops); deleteWorktree is the only artifact-destroying verb.
_Avoid_: Host operation, enqueue/queue language, claims, preflight RPCs (informed confirmation reads the mirror)

**Desktop operation**:
A mutation of desktop-owned records (tasks, projects, links). Completes against desktop records immediately and never blocks on host availability — the host-artifact halves of a cascade become Tombstones for the Reconcile sweep.

**Tombstone**:
A durable mark on a mirror row recording that the user deleted the entity: the deletion intent itself, carrying the frozen deletion options and the target record's id. Visible as the pending state until the Reconcile sweep converges it (or the user chooses Untrack anyway); purged when the mirror confirms the host record gone, and by forget-host. Tombstones have no expiry — boundedness comes from visibility and the terminal-failure stop.
_Avoid_: Queue/outbox language, "removal pending" as a separate state (the visible tombstoned row is the pending state), expiring intent

**Reconcile sweep**:
The client-side loop that converges tombstoned entities: whenever a host is reachable (boot, reconnect, tombstoned-while-online, 10-minute backstop), it calls each kind's idempotent removal verb for that host's tombstones and purges on mirror-confirmed absence. Entity-generic — one sweep, per-kind removal functions; failure classes are host-written on the record (transient retries silently, terminal stops with Retry / Untrack anyway). Deletion-only: it removes what tombstones name and converges nothing else.
_Avoid_: Reconciling the host toward records generally (ADR 0001 still rejects that), cross-kind ordering guarantees, treating RPC returns as truth (the record's outcome metadata is)

**Scan**:
The host-side pass that computes Observations and performs Adoption for registered paths — it reads the filesystem and git, records what it finds in the Host registry, and never mutates the world or converges it toward a record (ADR 0001). A failed or partial scan writes nothing (the positive-assertion invariant). Owned by the Registry scanner inside the workspace-registry runtime.
_Avoid_: Reconcile (the Reconcile sweep is the client-side, deletion-only tombstone loop), sync (that is the mirror plane)

**Placement**:
The desktop policy that picks the intended path for a new Workspace — computed from settings and Registry knowledge only, never by probing the host. The host is the final arbiter of what actually happens at that path.
_Avoid_: Probing, path reservation (nothing holds a path on the host)

**Claim**:
The desktop Registry atomically attaching annotations and bindings to a Host-acknowledged canonical Workspace record. An unknown id is inserted, a live id on the same Host is refreshed from Host structure (including canonical path spelling), and an explicitly claimed untracked id is retracked; a pending deletion Tombstone refuses. Claim never changes a row's Host attachment. Another live id at the same Host path is an identity invariant violation outside the one-time production cutover. A Claim is never optimistic for existing-path registration; task worktree creation has a separately named creation-intent row because `createWorktree` is strict about its caller-supplied id.
_Avoid_: Upsert (the mechanism, not the meaning), creation reviving tombstones, mirror-first creation (the Registry mirrors acked records; it never front-runs the Host registry)

**Retrack**:
The explicit desktop operation that moves an existing Workspace mirror to another Host attachment after that destination Host confirms the same canonical UUID. Used by Project relink; never inferred by Claim, Observe, or a path collision. A destination path owned by another UUID is a conflict rather than an implicit Project merge.
_Avoid_: Changing `sshConnectionId` as an annotation, path-based identity repair, treating a new Host's same path as automatically the same Project

**Observe**:
Applying a Host registry snapshot to the desktop Registry by canonical Workspace id. Observe refreshes Host facts, adopts unknown Host ids, and applies missing/untrack rules; it never relinks by path, rewrites desktop annotations, or resurrects an untracked row. A same-path/different-id collision is reported before writes and stops that Host attachment. Cross-id translation is limited to explicit workflows that already own the previous identity: the production backfill and repository initialization after the Host resolves a Project path to another canonical id.
_Avoid_: Path-based repair during normal sync, deliveries resurrecting untracked rows

**Activation**:
The moment a Workspace accepts Sessions. Session start waits for the prepare script to finish, but activation is never blocked by a script failure — failures surface as Workspace notices. Setup runs after activation, concurrent with live sessions; run scripts wait on setup success. Activation is ephemeral host-runtime state living in the Runtime overlay: after a daemon restart every workspace is inactive, and only lastActivatedAt persists as an Observation. Deactivation (kill all sessions + time-boxed, non-fatal teardown) is owned by deactivateWorkspace alone.
_Avoid_: Provisioning (that creates the artifact; activation starts using it), durable "active" flags

**Workspace notice**:
A surfaced, non-fatal event about a Workspace's session plane (a failed prepare or setup script). Informational with a re-run affordance, carried on the workspace's Runtime overlay — ephemeral like the activation it belongs to. The durable trace is the per-script last-outcome on the workspace record, which survives daemon restarts and syncs to the mirror.
_Avoid_: Operation, error state (the workspace keeps working)

### File identity vocabulary

Roles in `@emdash/core/primitives/path/api` (see `agents/architecture/path-system.md`), adopted as
the file identity for the unified content stack.

**HostFileRef**:
The canonical identity of a file: a Host (`HostRef`) plus an absolute path on that host. Independent
of any Workspace — workspace membership is a view/scoping concern, never part of file identity.
_Avoid_: HostPathRef (retired working name), (workspaceId, relative path) as identity

**ResourceUri**:
The serialized form of a HostFileRef (`emdash-file://v2/...`), used on the wire and in durable
state.
_Avoid_: Raw absolute path strings as serialized identity

**ResourceKey**:
The normalized comparison key derived from a HostFileRef for in-memory maps and dedupe — accounts
for case sensitivity and unicode normalization without changing display spelling.
_Avoid_: Using formatted paths or ResourceUris as map keys where normalized equality matters

**ScopedPath**:
A root HostFileRef plus a portable relative path — the shape for root-relative operations (tree
entries, watcher events, git paths, bulk calls). Not a file identity: the same file reached via
different roots yields different ScopedPaths.
_Avoid_: Keying content or open-file state by ScopedPath

**Facet**:
One of the up-to-three Monaco models of a single open file: the writable buffer, the read-only disk
mirror, and a read-only git snapshot at a ref. Facet URIs derive deterministically from the file's
ResourceUri and decode back to its HostFileRef.
_Avoid_: Treating facets as independent files with unrelated URIs

### Wire vocabulary

Roles in `packages/wire`, settled by the wire-architecture map's naming pass.

**Source**:
The server-side owner of one endpoint instance's data — the thing followers sync from. Named with a `Source` suffix (`LiveLogSource`, `LiveJobSource`, `EventStreamSource`); these implement the protocol `LiveSource` seam.
_Avoid_: Server (a file-name word, not a role), host (that is the keyed registry)

**Host (wire)**:
A keyed server-side registry of Sources serving one endpoint (the event-stream host), or the worker process registry (`WireWorkerHost`). Never a single instance's owner.
_Avoid_: Using host for a single Source

**Follower**:
The client-side sync state machine (`LiveFollower`): generation/sequence tracking, gap detection, resync. Internal machinery under every replica.

**Replica**:
One client-side, follower-backed copy of a Source's data: `ReplicaState`, `ReplicaLog`, `ReplicaJob`.
_Avoid_: Client (that is the RPC-side word)

**Replica cache**:
The keyed, refcounted, lingering cache of Replicas (`*ReplicaCache`), built on the kernel's keyed-retention primitive. Acquire/release leases; linger starts at last release.
_Avoid_: Word-order distinctions (the old `LiveJobReplica`-vs-`ReplicaJob` convention)

**State kernel**:
Wire's reactive state primitives (`cell`, `derived`, `family`, `query`, `optimistic`) — the only public surface for state-shaped data. Retention is observation-driven: observed ⇒ retained; `retain()` is the keep-warm exception.
_Avoid_: Authoring state models with hand-written providers (use `cell` + `expose`), consuming them with anything but `remote()`

**Bridge**:
The adapter pair carrying kernel state over the live-model wire protocol: `expose` (server) and `remote` (client). An adapter over the live layer, not a parallel transport.

**Wire seam**:
The seeded-connection seam in `primitives/wire/browser` — the single point where a host process hands core its wire connection. The host bootstrap calls `seedWireConnection` once; everything else reaches the wire through `domainClient`.
_Avoid_: Acquiring a connection anywhere else in core, reaching the wire through renderer-owned clients (the aggregate desktop wire client is renderer-internal)

### Core vocabulary

Roles in `packages/core`, sharpened during the exec-and-layering effort.

**Runtime (core)**:
Host-specific code under `packages/core/src/runtimes/` — a wire component worker that runs on the host plane, both locally and in the workspace-server, serving desktops through the host runtimes contract. Being a subprocess over wire is not sufficient: a worker that serves other workers rather than desktops (fs-watch) is a service, not a runtime.
_Avoid_: Calling every wire component worker a runtime

### Styling vocabulary

**Theme**:
The complete visual configuration for a rendered scope, composed from one Color scheme, one Density profile, and one Typography profile.
_Avoid_: Color theme, the token vocabulary, ThemeProvider

**Color scheme**:
The independently selectable Theme profile that assigns color, surface, and shadow values.
_Avoid_: Theme

**Density profile**:
The independently selectable Theme profile that assigns spatial density values.
_Avoid_: Theme

**Typography profile**:
The independently selectable Theme profile that assigns font and type-scale values.
_Avoid_: Theme

**Profile Definition**:
The source input that declares one Color scheme, Density profile, or Typography profile before build-time resolution.
_Avoid_: Theme Definition, Token Source

**Theme Compiler**:
The build-time Module that validates and resolves Profile Definitions into Token Values and host-loadable artifacts.
_Avoid_: Theme Generator, Token Generator

**Token**:
A stable, typed, author-facing value slot whose resolved value may vary by Theme or its owning visual context. CSS custom properties are implementation details, not Tokens.
_Avoid_: Any CSS custom property

**Primitive Token**:
A role-free Token representing a reusable design value such as a palette step, spacing step, radius size, or type-scale size.
_Avoid_: Scale Token, Foundation Token, React primitive

**Palette Token**:
A Primitive Token exposing one step or contrast value from a named neutral, accent, or hue palette. Color scheme Profile Definitions assign its Token Value.
_Avoid_: Raw color value, Semantic Token

**Semantic Token**:
A Token named for visual intent or use, such as muted foreground, elevated surface, or destructive border, independent of a specific UI component.
_Avoid_: Component-specific Token, any Token alias

**Contextual Token**:
A Semantic Token whose value is rebound by the nearest owning visual context, such as the current Surface background, foreground, hover, or border.
_Avoid_: Surface Reference, recipe-local variable

**Token Reference**:
The typed author-facing expression used in styles to refer to a Token. Its CSS custom-property representation is an implementation detail.
_Avoid_: Token, Token Value, raw CSS variable

**Token Value**:
The resolved CSS value assigned to a Token under a Theme and any owning visual context.
_Avoid_: Token, Token Reference

**Surface**:
A rendered region that establishes inherited visual context—background, foreground, border, and interaction-state roles—for itself and its descendants.
_Avoid_: Surface Token family, surface class, surface recipe

**Surface Level**:
A Surface's position in the ordered elevation relationship.
_Avoid_: Surface Role, Surface Tone

**Surface Role**:
A Surface's semantic purpose independent of its elevation.
_Avoid_: Surface Level, Surface Tone

**Surface Tone**:
A Surface's neutral or status intent, applied within its Level and Role.
_Avoid_: Surface Level, Surface Role, status room

**Style Recipe**:
A reusable style Module whose small typed variant interface returns the class name for a complete visual variant.
_Avoid_: Styling primitive, any shared style fragment, any Vanilla Extract `style()` result

**Style Utility**:
A constrained author-facing interface for local atomic layout or intentional Token-backed overrides. It does not encode a reusable visual pattern or component state.
_Avoid_: Styling primitive, any shared style helper, Style Recipe

**Component Styling Interface**:
The styling-relevant part of a React Module's public Interface: its intentional visual variants, state hooks, and slots.
_Avoid_: Appearance API, internal classes or selectors

**Global Rule**:
A CSS rule reached through a document, stable, or foreign selector rather than a generated class returned by a typed styling interface.
_Avoid_: Any Vanilla Extract `globalStyle()` call

**Host Styling Adapter**:
The host-owned Module at the styling seam with `@emdash/ui`, responsible for satisfying the shared styling interface and mapping host-only visual roles when necessary.
_Avoid_: Host Token Bridge, Theme Bridge

### Shared vocabulary

Roles in `packages/shared`, settled by the shared-architecture naming pass.

**Prelude**:
The root entrypoint (`@emdash/shared`) — the single home for the blessed cross-cutting core: the result module, `Unsubscribe`, `Emitter`, the lifecycle leases, `isDeepEqual`, the serialization/error family, and `Secret`. One home per symbol package-wide: domain modules stay subpath-only, and nothing is importable from both the root and a subpath.
_Avoid_: Re-exporting a prelude symbol from a subpath, aliasing a shared type under a domain name

**Scope**:
The ownership primitive: cancellation, cleanup ordering, child ownership, and tracked async work that must not outlive its feature. Registries, caches, and runs hang off a Scope rather than inventing their own teardown.
_Avoid_: Hand-rolled dispose lists, work that outlives its owner

**Clock**:
The time seam. No raw `Date.now`/`setTimeout` outside `scheduling/clock.ts`; anything time-dependent (`async-cache`, `resource-cache`, retry, timeouts) takes a `Clock` so tests drive time with `createManualClock`.
_Avoid_: Direct timer calls in primitives, fake-timer test hacks where a `Clock` parameter exists

**RetrySchedule**:
The one retry/backoff word. The `retrySchedule(options)` constructor lives beside the `retrySchedules` combinator namespace in `@emdash/shared/scheduling`; a schedule maps a retry index to a delay or `undefined` (stop).
_Avoid_: Backoff/BackoffSchedule (dissolved), per-package retry vocabularies

**Secret**:
The wrapper for actual secret material: tokens, passwords, private keys, passphrases, bearer capabilities, and decrypted backend values. It stays wrapped through internal and Wire plumbing; `Secret.expose()` is the one plaintext disclosure spelling and is lint-allowlisted only at true sinks.
_Avoid_: Revealing early, `reveal()` aliases, using Secret for public ciphertext/signatures, logging exposed values

**Sensitive**:
The wrapper for non-secret security artifacts that generic egress must redact, such as public enrollment keys, signatures, ciphertext, signed manifests, raw audit payloads, and encrypted locators. It is an egress classification, not a Secret authorization boundary.
_Avoid_: Using Sensitive to bypass Secret disclosure controls, treating all redacted artifacts as secret material

**Secret Wire envelope**:
The strict versioned structural carrier declared by `wireSecret` or `wireSensitive` to preserve a protected wrapper across a process boundary. It marks sensitivity for schema validation and redaction but does not encrypt; Host grant confidentiality uses a separate HPKE envelope.
_Avoid_: Host grant envelope, logging placeholder, generic recursive Secret discovery

**Emdash Git credential helper**:
The packaged, stateless Host-local adapter implementing Git's credential-helper protocol. It asks the Host Secret Runtime through a scoped Git credential channel and writes a granted credential only to Git's response stream; it never chooses an account or stores a credential.
_Avoid_: ASKPASS broker, provider-native helper, Secret resolver, global credential store

**First-party Git credential mode**:
The per-Project choice for Git operations owned by Emdash itself: `effective-account` uses the selected managed account, while `system` delegates to the Host's native Git authentication. It is separate from Session policy so agent containment does not disable background source control.
_Avoid_: Agent Git credentials, GitHub API account, silent native fallback after a selected identity breaks

**Session Git credential mode**:
The per-Project policy for terminal, TUI, and ACP Git: `effective-account`, `system`, or `none`. It governs credential helpers and ASKPASS; `none` is not a sandbox for netrc, integrated HTTP authentication, native SSH, or other same-user ambient mechanisms.
_Avoid_: First-party Git credential mode, no-network mode, OS-user credential sandbox

**Git credential target policy**:
The HTTPS boundary attached to one Git credential channel capability. A first-party operation target is one exact repository; a Session target is one canonical authority (host and effective port) and permits repository paths on that authority.
_Avoid_: Git remote URL string matching, helper-selected binding, Host-wide Secret grant

**Git credential channel capability**:
The ephemeral bearer right minted by the Host Secret Runtime for one Git operation or Session. It binds an exact Workspace, consumer, Secret binding, HTTPS target, purpose, Runtime boot, expiry, and optional use budget; it confers no grant enumeration or caller-selected binding.
_Avoid_: Secret binding, provider token, reusable Host credential, desktop nonce

**Package conventions**:
Ownership-drop: a primitive that takes ownership of a value fires `onDrop` exactly once for every taken-then-discarded value, and rejecting a value never fires it (the caller kept ownership). Never-silent: optional failure hooks default to logger-backed reporting rather than swallowing.
_Avoid_: Silent drops, failure hooks whose omission loses the error
