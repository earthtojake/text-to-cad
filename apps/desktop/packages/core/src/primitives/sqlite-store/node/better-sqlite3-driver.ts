import Database from 'better-sqlite3';
import type { SqliteConnection, SqliteDriver } from '../api';

function normalizeInteger(value: unknown): unknown {
  if (
    typeof value === 'bigint' &&
    value >= BigInt(Number.MIN_SAFE_INTEGER) &&
    value <= BigInt(Number.MAX_SAFE_INTEGER)
  ) {
    return Number(value);
  }

  return value;
}

function normalizeRow<T>(row: unknown): T {
  return Object.fromEntries(
    Object.entries(row as Record<string, unknown>).map(([key, value]) => [
      key,
      normalizeInteger(value),
    ])
  ) as T;
}

export const betterSqlite3Driver: SqliteDriver<Database.Database> = {
  open(path) {
    const native = new Database(path);
    const connection: SqliteConnection<Database.Database> = {
      native,
      exec: (sql) => {
        native.exec(sql);
      },
      get: <T>(sql: string, params: readonly unknown[] = []) => {
        const row = native
          .prepare(sql)
          .safeIntegers(true)
          .get(...params);
        return row === undefined ? undefined : normalizeRow<T>(row);
      },
      all: <T>(sql: string, params: readonly unknown[] = []) =>
        native
          .prepare(sql)
          .safeIntegers(true)
          .all(...params)
          .map((row) => normalizeRow<T>(row)),
      run: (sql, params = []) =>
        native
          .prepare(sql)
          .safeIntegers(true)
          .run(...params),
      close: () => {
        native.close();
      },
    };

    return connection;
  },
};
