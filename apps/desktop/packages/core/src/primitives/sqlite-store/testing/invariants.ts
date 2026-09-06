import type { SqliteConnection } from '../api';

export function assertSqliteIntegrity(connection: SqliteConnection): void {
  const rows = connection.all<Record<string, unknown>>('PRAGMA integrity_check');
  const messages = rows.flatMap((row) => Object.values(row).map(String));
  if (messages.length !== 1 || messages[0] !== 'ok') {
    throw new Error(`SQLite integrity check failed: ${messages.join('; ')}`);
  }
}

export function assertForeignKeyIntegrity(connection: SqliteConnection): void {
  const violations = connection.all<Record<string, unknown>>('PRAGMA foreign_key_check');
  if (violations.length > 0) {
    throw new Error(`SQLite foreign-key check failed: ${JSON.stringify(violations.slice(0, 5))}`);
  }
}

export function assertSqliteStoreInvariants(connection: SqliteConnection): void {
  assertSqliteIntegrity(connection);
  assertForeignKeyIntegrity(connection);
}
