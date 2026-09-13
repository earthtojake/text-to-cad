import assert from 'node:assert/strict';
import type { DurableSqliteStore, SqliteConnection } from '../api';

type SchemaRow = {
  name: string;
  sql: string | null;
  type: string;
};

function readSchema(connection: SqliteConnection): SchemaRow[] {
  return connection
    .all<SchemaRow>(
      `SELECT type, name, sql
       FROM sqlite_schema
       WHERE name NOT LIKE 'sqlite_%'
       ORDER BY type, name`
    )
    .map((row) => ({
      ...row,
      sql: row.sql?.replaceAll(/\s+/g, ' ').trim() ?? null,
    }));
}

/**
 * Verifies that migrating every supported historical boundary reaches the
 * exact schema produced by applying the full manifest to an empty database.
 */
export async function assertIncrementalMigrationEquivalence<TDb, TNative>(
  store: DurableSqliteStore<TDb, TNative>,
  migrationCount: number
): Promise<void> {
  if (!Number.isSafeInteger(migrationCount) || migrationCount < 0) {
    throw new RangeError(`Migration count must be a non-negative integer: ${migrationCount}`);
  }

  const latest = await store.openTemp();
  let expected: SchemaRow[];
  try {
    expected = readSchema(latest.connection);
  } finally {
    latest.close();
  }

  for (let boundary = 0; boundary <= migrationCount; boundary += 1) {
    const incremental = store.openAtMigration(boundary);
    try {
      incremental.migrateToLatest();
      assert.deepEqual(
        readSchema(incremental.connection),
        expected,
        `Migration boundary ${boundary} did not reach the latest schema`
      );
    } finally {
      incremental.close();
    }
  }
}
