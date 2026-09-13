export type SqliteRunResult = {
  changes: number | bigint;
  lastInsertRowid: number | bigint;
};

/**
 * Minimal SQL-shaped connection contract used by SQLite stores.
 *
 * Store lifecycle, transactions, and pragmas intentionally live above this
 * interface so drivers cannot introduce different migration semantics.
 *
 * INTEGER values within JavaScript's safe range are returned as numbers.
 * Values outside that range must be returned exactly as bigints; drivers must
 * never silently round an INTEGER.
 */
export interface SqliteConnection<TNative = unknown> {
  readonly native: TNative;
  exec(sql: string): void;
  get<T>(sql: string, params?: readonly unknown[]): T | undefined;
  all<T>(sql: string, params?: readonly unknown[]): T[];
  run(sql: string, params?: readonly unknown[]): SqliteRunResult;
  close(): void;
}

export interface SqliteDriver<TNative = unknown> {
  open(path: string): SqliteConnection<TNative>;
}
