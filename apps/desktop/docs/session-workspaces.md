# Session workspaces and persistence

The session is the ownership boundary. The directory is a way to group
sessions and resolve files, not an independent saved project.

## Directory groups

`sessions.project_id` / `Session.projectId` is the stable absolute path of
the original directory. These names remain in the file-service contracts;
they no longer refer to a project row. A worktree session keeps that directory
identity and separately records its actual `cwd` and `worktreePath`.
New folder choices resolve symlinks, while existing session directory spellings
remain stable. Choosing an alias of an existing directory reuses that group.

`projects.list` and the renderer's `projectsFromSessions` derive directory
descriptors from sessions. `projects.add` (the chooser channel) and
`onboarding.createSample` only validate a folder choice and select a transient
new-session draft. They create no database row: both hand the directory to the
repository's `projects.choose` (`src/main/db/repositories.ts`, not a channel),
which resolves it and remembers it in `chosen`, a map for this run that is
never persisted. Beside it, `projects.get` answers only for a directory a
session records or one in `chosen` — never for a path the renderer merely
names, since an id is renderer input.

The e2e suite chooses folders through a door, not a channel:
`src/main/test-door.ts` (`installE2eDoor`) puts `globalThis.__textToCadE2E`
on main's global only when `NODE_ENV=test` and the build is not packaged. Its
`choose(dir)` calls `projects.choose` and broadcasts `ui.directorySelected`,
as the chooser does; `chooseDirectory` in `tests/e2e/launch.ts` drives it
through `app.evaluate`. `choose` returns a promise that is started in a
`setImmediate` macrotask, so `app.evaluate` must return it (and the caller await
it): `app.evaluate` is an inspector call that V8 runs as an interrupt at the next
function entry, which can land inside a better-sqlite3 `.all()` at its row
factory, where the connection is busy and `prepare` throws. A macrotask starts
on an empty stack.
The descriptor's name is the directory basename. There is no project rename
or delete operation. Sidebar groups contain sessions matching the current
filters; empty groups are omitted. Archiving the last visible session hides
the group. Archived sessions remain available in Settings and can be restored
without recreating a project. Missing or unmounted directories never cause
their session index entries to be deleted. The rows that are removed are the
ones with no `acpSessionId`: `boot()` deletes each that no create in this run
owns (a create cut short by a quit), unpins its marks, and releases the
worktree the row records as cut by that create (`worktreeOwned`; a handed-in
worktree is left alone). `acpSessionId` is stored right after `session/new`,
before the preferences and the marks; a create that fails after that point
while the connection is alive resolves, the row `idle` with the failure as a
note in `session.status.error` (the renderer shows it above the composer, which
stays sendable, with a Retry setup button that re-runs the setup through
`sessions.retrySetup`; a load or a disconnect clears it). When the connection is dead or the row is
gone, `abandonCreate` removes the row, retires the connection and releases the
worktree that create cut, and `create` rejects.

## Explorer and tool ownership

Every explorer tab has both a required `sessionId` and the directory identity
`projectId`. A new session starts with an empty strip. Switching sessions
restores that session's own tabs, selection and pane state. A new-session
draft has no explorer until a session exists.

Persisted tabs are keyed by `session_id`, with a foreign key to sessions.
`explorer.loadTabs` and `saveTabs` name that session; saving checks every tab's
owner and directory before replacing anything. A failed write is atomic.
Drawings stay in memory and are never included in the persisted strip.
`loadTabs` releases a saved terminal `ptyId` that no live pty of the session
answers to (ptys die with the app), so the tab starts a fresh shell; an
`agent: true` tab respawns with the runtime `PATH`.

MCP credentials bind the immutable session id and working directory. Renderer
commands, browser/CDP targets and terminals enforce that same owner. An agent
cannot list, read, close, rename or drive another session's tabs, even if both
sessions use the same directory. Background tool calls update their owner's
retained strip without selecting a different session for the user. Files on
disk may of course be shared by sessions using the same checkout; unsaved
editor buffers and tab UI state are separate.

The renderer window shares bounded CAD geometry caches by directory/root while
any retained file tab owns that root. Switching sessions or collapsing the pane
unmounts the viewport without discarding those caches. Closing the last owner or
discarding its session releases the client; camera and selection remain per tab.

Archive writes the session row first, then closes live session resources; it
retains the session row and its persisted tabs. Delete removes that session and its children only. A
session's worktree goes only when Settings' auto-delete is on: deleting the
session then removes it (never forced), and after each new worktree's row is
written a keep-limit sweep removes the oldest past the limit — never one the
`cwd`, `projectId` or `worktreePath` of a session that is not archived names, a
locked one, a create still in flight, or one with unsaved work (README, "Git
modes and worktrees"). An archived session holds no worktree: `sessionsUsing`
(`src/main/projects/git.ts`) is the one answer to "in use" for Settings' count,
Delete's refusal, the sweep and a session's release. A worktree whose folder
was deleted by hand reads as clean in Settings and can be deleted there. A create that fails is the exception:
the worktree it made, and its branch while still at its base, go with its row
whatever the setting.

## Session names

The first prompt supplies a fallback title until the agent sends an ACP
`session_info_update`. Main validates the update against the parent ACP
session, saves the title, and broadcasts the session index. Notifications
during creation and replay are handled too. Sidebar and header read the same
saved title.

A `session/load` replay sends no `session_info_update`, so main starts the
reloaded state from the title it already knew — the last snapshot's, or the
row's when the agent named it — and a replayed agent turn is settled as
`end_turn`, as it was live; replayed user turns keep no stop reason.

`titleSource` records `prompt`, `agent`, or `user`. An explicit user rename
has priority over later agent notifications, including after restart. Empty
titles and updates for other ACP sessions are ignored. Older databases did
not record title provenance; migrated titles initially use `prompt`.

## Upgrades, restart and profiles

The database is `text-to-cad.db` inside Electron's `userData` directory. Normal
launches use the stable `text-to-cad` app-data directory. An explicit
`--user-data-dir` selects a separate profile; it does not move, merge or delete
the normal profile. Use the same profile when relaunching a user's preview.
The startup `[db]` log identifies the actual database.

Before upgrading an existing schema, the app writes a consistent SQLite
backup beside it: `text-to-cad.db.before-v<newest migration>-<timestamp>.bak`, named
by the version the upgrade goes to, not the one it leaves. `VACUUM INTO`
includes committed WAL contents; copying only the main database file would
not. A backup or migration error aborts the open, never resets the database.
After an upgrade succeeds only the newest three backups are kept and older
ones are deleted (`UPGRADE_BACKUPS_KEPT` and `pruneUpgradeBackups` in
`src/main/db/index.ts`). A database from a newer app schema is rejected rather
than modified.

Migration 11 removes the projects table and carries every session id, agent
session id, snapshot, archive/pin flag, working directory and review mark
forward. Each legacy shared tab is assigned once to the most recent session
for its root, preferring an unarchived session. Tabs from old directories
without any session remain recoverable from the pre-upgrade backup while it is
among the three kept. No tabs
are copied into sessions subsequently created in the same directory.

Migration 12 adds `sessions.worktree_owned`: whether the create that wrote a row
cut its worktree or was handed it (`New session in this worktree`). `boot`
releases only the first kind when it purges a create the app quit in. Existing
rows read as given, so a worktree nobody can vouch for is left alone.

Schema migrations are append-only. Validate changes against an existing
database fixture as well as an empty database. The native regression suite
`tests/e2e/session-storage.spec.ts` covers upgrade, restart, backup contents,
ownership rejection and deletion isolation (it finds the backup by the newest
migration's version, `MIGRATIONS.at(-1)`, so a new migration does not break it); `persistence.spec.ts` covers
agent naming and persisted user overrides.
