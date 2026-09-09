import type { BundledMigration, MigrationInterop, SqliteConnection } from '../api';
import { STORE_TABLE } from './constants';

const LEGACY_TABLE = '__drizzle_migrations';

function tableExists(connection: SqliteConnection, table: string): boolean {
  return (
    connection.get(
      `SELECT 1 AS present
       FROM sqlite_schema
       WHERE type = 'table' AND name = ?
       LIMIT 1`,
      [table]
    ) !== undefined
  );
}

function backfill(connection: SqliteConnection, migrations: readonly BundledMigration[]): void {
  if (!tableExists(connection, LEGACY_TABLE)) return;

  const legacyRows = connection.all<{ created_at: number | null; hash: string }>(
    `SELECT hash, created_at FROM ${LEGACY_TABLE} ORDER BY id`
  );

  for (const row of legacyRows) {
    const timestampMatch = migrations.find(({ when }) => when === row.created_at);
    const hashMatches = timestampMatch ? [] : migrations.filter(({ hash }) => hash === row.hash);
    if (hashMatches.length > 1) {
      throw new Error(
        `Ambiguous legacy migration hash ${row.hash}: matched ${hashMatches.length} migrations`
      );
    }
    const migration = timestampMatch ?? hashMatches[0];
    if (!migration) {
      throw new Error(
        `Unrecognized legacy migration (created_at=${String(row.created_at)}, hash=${row.hash})`
      );
    }
    connection.run(
      `INSERT OR IGNORE INTO ${STORE_TABLE} (tag, hash, applied_at)
       VALUES (?, ?, ?)`,
      [migration.tag, migration.hash, row.created_at ?? migration.when]
    );
  }
}

function onApplied(connection: SqliteConnection, migration: BundledMigration): void {
  connection.exec(`
    CREATE TABLE IF NOT EXISTS ${LEGACY_TABLE} (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      hash TEXT NOT NULL,
      created_at NUMERIC
    )
  `);
  connection.run(`INSERT INTO ${LEGACY_TABLE} (hash, created_at) VALUES (?, ?)`, [
    migration.hash,
    migration.when,
  ]);
}

export const drizzleV0Interop: MigrationInterop = {
  backfill,
  onApplied,
};
