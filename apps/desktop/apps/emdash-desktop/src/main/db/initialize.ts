import { createHash } from 'node:crypto';
import type BetterSqlite3 from 'better-sqlite3';
import journal from '@root/drizzle/meta/_journal.json';

// Vite bundles all migration SQL files at build time — no runtime path resolution needed.
// Each value is the raw SQL string content of the file.
const sqlFiles = import.meta.glob('@root/drizzle/*.sql', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

type JournalEntry = { idx: number; when: number; tag: string; breakpoints: boolean };

function runBundledMigrations(connection: BetterSqlite3.Database): void {
  connection.exec(`
    CREATE TABLE IF NOT EXISTS __drizzle_migrations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      hash TEXT NOT NULL,
      created_at NUMERIC
    )
  `);

  const lastRow = connection
    .prepare('SELECT created_at FROM __drizzle_migrations ORDER BY created_at DESC LIMIT 1')
    .get() as { created_at: number } | undefined;
  const lastTimestamp = lastRow?.created_at ?? 0;

  const pending = (journal as { entries: JournalEntry[] }).entries.filter(
    (entry) => entry.when > lastTimestamp
  );
  if (pending.length === 0) return;

  // Migrations that recreate a table (CREATE __new_x → DROP x → RENAME) must not
  // run with foreign keys enforced: DROP TABLE under enforcement performs an
  // implicit DELETE that cascades into child tables. `PRAGMA foreign_keys` is a
  // no-op inside a transaction, so the toggle has to happen out here.
  connection.pragma('foreign_keys = OFF');
  try {
    connection.transaction(() => {
      for (const entry of pending) {
        const sqlKey = Object.keys(sqlFiles).find((k) => k.includes(entry.tag));
        if (!sqlKey) throw new Error(`Missing bundled SQL for migration: ${entry.tag}`);

        const sql = sqlFiles[sqlKey];
        const hash = createHash('sha256').update(sql).digest('hex');

        for (const stmt of sql.split('--> statement-breakpoint')) {
          const trimmed = stmt.trim();
          if (trimmed) connection.exec(trimmed);
        }

        connection
          .prepare('INSERT INTO __drizzle_migrations (hash, created_at) VALUES (?, ?)')
          .run(hash, entry.when);
      }
    })();
  } finally {
    connection.pragma('foreign_keys = ON');
  }
}

/**
 * Creates the FTS5 full-text search virtual table used by the command palette.
 * This is managed outside the Drizzle migration system because Drizzle cannot
 * generate FTS5 virtual table DDL. The table is version-gated via the `kv`
 * table so it can be safely dropped and recreated when the schema changes.
 */
function ensureSearchIndex(connection: BetterSqlite3.Database): void {
  // Bump this version string whenever the FTS schema changes — the table is
  // dropped and recreated, and SearchService backfills dynamic entities.
  const SEARCH_INDEX_VERSION = '4';

  const row = connection.prepare(`SELECT value FROM kv WHERE key = 'fts_version'`).get() as
    | { value: string }
    | undefined;

  if (row?.value !== SEARCH_INDEX_VERSION) {
    connection.exec(`DROP TABLE IF EXISTS search_index`);
    connection.exec(`
      CREATE VIRTUAL TABLE search_index USING fts5(
        item_type,
        item_id    UNINDEXED,
        project_id UNINDEXED,
        task_id    UNINDEXED,
        title,
        keywords,
        tokenize = 'trigram case_sensitive 0'
      )
    `);
    connection
      .prepare(
        `INSERT OR REPLACE INTO kv (key, value, updated_at) VALUES ('fts_version', ?, unixepoch())`
      )
      .run(SEARCH_INDEX_VERSION);
  }
}

/** Removes the desktop-owned index now provided by the dedicated Core file-search runtime. */
function removeLegacyFileIndex(connection: BetterSqlite3.Database): void {
  connection.transaction(() => {
    connection.exec(`DROP TABLE IF EXISTS workspace_file_index`);
    connection.exec(`DROP TABLE IF EXISTS workspace_file_index_meta`);
    // Removing the marker lets an older desktop version recreate its derived index after a
    // downgrade instead of assuming the dropped tables still exist.
    connection.prepare(`DELETE FROM kv WHERE key = 'file_index_version'`).run();
  })();
}

/**
 * Runs all pending migrations against the provided SQLite connection. Call this
 * once during boot before publishing the shared app database.
 *
 * Accepts an explicit connection so migration tests and fixture generators can
 * pass an in-memory database.
 *
 * Returns the connection that was used.
 */
export async function initializeDatabase(
  connection: BetterSqlite3.Database
): Promise<BetterSqlite3.Database> {
  connection.pragma('foreign_keys = ON');
  runBundledMigrations(connection);
  ensureSearchIndex(connection);
  removeLegacyFileIndex(connection);
  return connection;
}
