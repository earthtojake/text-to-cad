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
