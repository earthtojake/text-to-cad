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
descriptors from sessions. `projects.add` / `addPath` only validate a folder
choice and select a transient new-session draft. They create no database row.
The descriptor's name is the directory basename. There is no project rename
or delete operation. Sidebar groups contain sessions matching the current
filters; empty groups are omitted. Archiving the last visible session hides
the group. Archived sessions remain available in Settings and can be restored
without recreating a project. Missing or unmounted directories never cause
their session index entries to be deleted.

## Explorer and tool ownership

Every explorer tab has both a required `sessionId` and the directory identity
`projectId`. A new session starts with an empty strip. Switching sessions
restores that session's own tabs, selection and pane state. A new-session
draft has no explorer until a session exists.

Persisted tabs are keyed by `session_id`, with a foreign key to sessions.
`explorer.loadTabs` and `saveTabs` name that session; saving checks every tab's
owner and directory before replacing anything. A failed write is atomic.
Drawings stay in memory and are never included in the persisted strip.

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

Archive closes live session resources but retains the session row and its
persisted tabs. Delete removes that session and its children only. The
existing explicit worktree cleanup preference still controls worktree removal.

## Session names

The first prompt supplies a fallback title until the agent sends an ACP
`session_info_update`. Main validates the update against the parent ACP
session, saves the title, and broadcasts the session index. Notifications
during creation and replay are handled too. Sidebar and header read the same
saved title.

`titleSource` records `prompt`, `agent`, or `user`. An explicit user rename
has priority over later agent notifications, including after restart. Empty
titles and updates for other ACP sessions are ignored. Older databases did
not record title provenance; migrated titles initially use `prompt`.

## Upgrades, restart and profiles

The database is `hardcore.db` inside Electron's `userData` directory. Normal
launches use the stable `Hardcore` app-data directory. An explicit
`--user-data-dir` selects a separate profile; it does not move, merge or delete
the normal profile. Use the same profile when relaunching a user's preview.
The startup `[db]` log identifies the actual database.

Before upgrading an existing schema, the app writes a consistent SQLite
backup beside it: `hardcore.db.before-v<version>-<timestamp>.bak`. `VACUUM INTO`
includes committed WAL contents; copying only the main database file would
not. A backup or migration error aborts the open, never resets the database.
A database from a newer app schema is rejected rather than modified.

Migration 11 removes the projects table and carries every session id, agent
session id, snapshot, archive/pin flag, working directory and review mark
forward. Each legacy shared tab is assigned once to the most recent session
for its root, preferring an unarchived session. Tabs from old directories
without any session remain recoverable from the pre-upgrade backup. No tabs
are copied into sessions subsequently created in the same directory.

Schema migrations are append-only. Validate changes against an existing
database fixture as well as an empty database. The native regression suite
`tests/e2e/session-storage.spec.ts` covers upgrade, restart, backup contents,
ownership rejection and deletion isolation; `session-titles.spec.ts` covers
agent naming and persisted user overrides.
