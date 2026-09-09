/**
 * The migration runner.
 *
 * Deliberately tiny and deliberately not tied to better-sqlite3: it takes a
 * structural `MigrationDb`, so the ordering and failure behaviour can be
 * tested in plain Node (`tests/unit/migrations.test.ts`) without a native
 * module built against Electron's ABI.
 *
 * Schema version lives in sqlite's own `user_version` pragma. Migrations are
 * append-only and never renumbered: an installed app has already run the ones
 * below it.
 */

/** The slice of a sqlite handle the runner needs. */
export interface MigrationDb {
  pragma(source: string, options?: { simple?: boolean }): unknown;
  exec(source: string): unknown;
}

export interface Migration {
  /** 1-based, contiguous, append-only. */
  readonly version: number;
  /** Human-readable; shows up in failure messages. */
  readonly name: string;
  readonly up: string;
}

export const MIGRATIONS: readonly Migration[] = [
  {
    version: 1,
    name: "initial",
    up: `
      CREATE TABLE projects (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        path        TEXT NOT NULL UNIQUE,
        created_at  INTEGER NOT NULL
      );

      CREATE TABLE sessions (
        id          TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        agent_id    TEXT NOT NULL,
        cwd         TEXT NOT NULL,
        git_mode    TEXT NOT NULL,
        branch      TEXT,
        title       TEXT NOT NULL,
        created_at  INTEGER NOT NULL,
        updated_at  INTEGER NOT NULL,
        status      TEXT NOT NULL
      );
      CREATE INDEX sessions_by_project ON sessions(project_id, updated_at DESC);

      -- One row per setting key, JSON-encoded. A blob would make a settings
      -- write a read-modify-write of the whole object; per-key rows also let
      -- an unknown key from a newer build survive a downgrade untouched.
      CREATE TABLE settings (
        key    TEXT PRIMARY KEY,
        value  TEXT NOT NULL
      );

      -- The explorer strip. Kind-specific fields live in the JSON payload;
      -- the columns are only what the app queries or orders by.
      CREATE TABLE explorer_tabs (
        id          TEXT PRIMARY KEY,
        session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        kind        TEXT NOT NULL,
        position    INTEGER NOT NULL,
        payload     TEXT NOT NULL
      );
      CREATE INDEX explorer_tabs_by_session ON explorer_tabs(session_id, position);
    `,
  },
  {
    version: 2,
    name: "acp-sessions",
    // P1: the agent's own session id (what `session/load` resumes) and the
    // files-changed counters the sidebar pill shows.
    up: `
      ALTER TABLE sessions ADD COLUMN acp_session_id TEXT;
      ALTER TABLE sessions ADD COLUMN changed_files INTEGER NOT NULL DEFAULT 0;
      ALTER TABLE sessions ADD COLUMN insertions INTEGER NOT NULL DEFAULT 0;
      ALTER TABLE sessions ADD COLUMN deletions INTEGER NOT NULL DEFAULT 0;
    `,
  },
  {
    version: 3,
    name: "explorer-tabs-per-project",
    // The strip belongs to the project, not to a thread (see the comment on
    // ExplorerTabBase in src/shared/types.ts). Migration 1 keyed it by session
    // with a cascading foreign key, which would take a person's open files
    // away when they closed a thread.
    //
    // Rebuilt rather than altered: sqlite cannot drop a foreign key with
    // ALTER TABLE, and there is nothing to carry over — no build has shipped
    // with a session strip in it.
    up: `
      DROP TABLE explorer_tabs;

      CREATE TABLE explorer_tabs (
        id          TEXT PRIMARY KEY,
        project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        kind        TEXT NOT NULL,
        position    INTEGER NOT NULL,
        payload     TEXT NOT NULL
      );
      CREATE INDEX explorer_tabs_by_project ON explorer_tabs(project_id, position);
    `,
  },
  {
    version: 4,
    name: "archived-sessions",
    // P2: the sidebar's archive action. The row stays so the agent's own
    // transcript can still be loaded back.
    up: `
      ALTER TABLE sessions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;
    `,
  },
  {
    version: 5,
    name: "worktrees-and-review-marks",
    // P7: the worktree a session owns (and may take with it when it is
    // deleted), and the two revisions the review's `Last turn` and `This
    // session` scopes are measured from. All nullable: a session in `none` or
    // `checkout` mode has no worktree, and a directory that is not a
    // repository has no revisions.
    up: `
      ALTER TABLE sessions ADD COLUMN worktree_path TEXT;
      ALTER TABLE sessions ADD COLUMN session_head TEXT;
      ALTER TABLE sessions ADD COLUMN turn_head TEXT;
      ALTER TABLE sessions ADD COLUMN turn_started_at INTEGER;
    `,
  },
  {
    version: 6,
    name: "agent-options",
    // What each agent last said its session could be configured with, and
    // what the person picked. The new-session screen draws a model and an
    // effort chip before any agent is running, and only a snapshot taken
    // from a real `session/new` can tell it which models that agent has.
    //
    // `options` is the ConfigOption[] as JSON: the wire shape changes with
    // the adapters, and a cache is exactly the place not to freeze it into
    // columns. It is a cache — a row that no longer parses is dropped and
    // re-probed, never migrated.
    up: `
      CREATE TABLE agent_options (
        agent_id        TEXT PRIMARY KEY,
        options         TEXT,
        options_at      INTEGER,
        default_model   TEXT,
        default_effort  TEXT
      );
    `,
  },
  {
    version: 7,
    name: "pinned-sessions",
    // The sidebar's `Pinned` section. A column on the session rather than a
    // list of ids in the settings blob: the row already goes away when the
    // thread is deleted, and a list would be a second place to forget it
    // from.
    up: `
      ALTER TABLE sessions ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;
    `,
  },
  {
    version: 8,
    name: "agent-modes",
    // The mode is the app's one permission control, drawn on the new-session
    // screen as well as in a live thread, so the cache has to keep the other
    // half of what `session/new` answers: Claude sends its modes in `modes`
    // rather than as a config option, and a screen with no session would
    // have nothing to draw them from. `default_mode` is the mode the next
    // session starts in, beside the model and the effort it starts with;
    // null means the agent's own auto-approval preset.
    //
    // `modes` is JSON for the same reason `options` is (migration 6): it is
    // a cache of a wire shape, and a row that no longer parses is re-probed
    // rather than migrated.
    up: `
      ALTER TABLE agent_options ADD COLUMN modes TEXT;
      ALTER TABLE agent_options ADD COLUMN default_mode TEXT;
    `,
  },
  {
    version: 9,
    name: "agent-effort-per-model",
    // The effort belongs to the model, not to the agent. Claude's `effort`
    // option is reported for whichever model the session is on and its
    // levels change with it — `Xhigh` exists for one model and not the next
    // — so one `default_effort` per agent carried the outgoing model's level
    // onto the incoming one and forgot the earlier pick. It becomes a map:
    //
    //   default_efforts  {"<model value>": "<effort value>"}
    //   effort_options   {"<model value>": <the effort ConfigOption>}
    //
    // `default_efforts` is what the person picked, per model; `effort_options`
    // is the levels each model offers, filled in whenever a live session
    // reports its options — the only place a model's list is ever said. Both
    // are JSON for the reason `options` is (migration 6): a cache of a wire
    // shape, re-probed rather than migrated when it stops parsing.
    //
    // The old column goes, with nothing left behind to read it: a level
    // stored against no model is not an answer to "which effort for this
    // model", and a shim that guessed one would be a wrong answer.
    up: `
      ALTER TABLE agent_options ADD COLUMN default_efforts TEXT;
      ALTER TABLE agent_options ADD COLUMN effort_options TEXT;
      ALTER TABLE agent_options DROP COLUMN default_effort;
    `,
  },
  {
    version: 10,
    name: "session-state-snapshots",
    // The last reduced `SessionState` of each session, so clicking a row
    // paints its transcript at once instead of showing a spinner for the two
    // seconds a spawn, an `initialize` and a `session/load` take
    // (src/main/acp/snapshots.ts, README "Opening a session").
    //
    // A table of its own rather than a column on `sessions`: every read of
    // that row goes through the sidebar's list, and a half-megabyte JSON
    // blob per session is not something to carry into a list of titles.
    //
    // `state` is the SessionState as JSON, capped by the writer. It is a
    // cache — a row that no longer parses is dropped and the session falls
    // back to the spinner, never migrated — and it goes with its session
    // (ON DELETE CASCADE).
    up: `
      CREATE TABLE session_state (
        session_id  TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
        state       TEXT NOT NULL,
        updated_at  INTEGER NOT NULL
      );
    `,
  },
];

/**
 * Bring `db` up to the newest migration, applying each pending one in its own
 * transaction. Returns the version it ended on.
 *
 * A failure rolls that migration back and throws, leaving `user_version` at
 * the last one that succeeded — so a fixed build resumes from there instead of
 * re-running work it already did.
 */
export function runMigrations(db: MigrationDb, migrations: readonly Migration[] = MIGRATIONS) {
  assertContiguous(migrations);

  const current = Number(db.pragma("user_version", { simple: true }) ?? 0);
  const pending = migrations.filter((migration) => migration.version > current);

  for (const migration of pending) {
    db.exec("BEGIN");
    try {
      db.exec(migration.up);
      // `user_version` takes no bound parameter; the value is checked to be an
      // integer by assertContiguous, so this cannot smuggle SQL.
      db.exec(`PRAGMA user_version = ${migration.version}`);
      db.exec("COMMIT");
    } catch (error) {
      db.exec("ROLLBACK");
      throw new Error(
        `migration ${migration.version} (${migration.name}) failed: ${String(error)}`,
        { cause: error },
      );
    }
  }

  return migrations.at(-1)?.version ?? current;
}

function assertContiguous(migrations: readonly Migration[]) {
  migrations.forEach((migration, index) => {
    if (!Number.isSafeInteger(migration.version) || migration.version !== index + 1) {
      throw new Error(
        `migrations must be numbered 1..n in order; found ${migration.version} at index ${index}`,
      );
    }
  });
}
