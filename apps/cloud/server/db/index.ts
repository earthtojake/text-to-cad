// One query interface over two drivers: Postgres (Neon, `DATABASE_URL`) in production and
// PGlite (in memory, or `CLOUD_PGLITE_DIR`) for development and tests. Both speak $1
// placeholders. Callers cast aggregates (`::int`, `::float8`) so both return numbers.
import { readFile } from 'node:fs/promises';
import type Postgres from 'postgres';

export type Row = Record<string, any>;

export interface QueryResult<T = Row> {
  rows: T[];
  rowCount: number;
}

export interface Queryable {
  query<T = Row>(text: string, params?: unknown[]): Promise<QueryResult<T>>;
}

export interface Db extends Queryable {
  kind: 'pglite' | 'postgres';
  exec(script: string): Promise<void>;
  transaction<T>(fn: (tx: Queryable) => Promise<T>): Promise<T>;
  close(): Promise<void>;
}

export async function createPgliteDb(dir?: string): Promise<Db> {
  const { PGlite } = await import('@electric-sql/pglite');
  const pg = dir ? new PGlite(dir) : new PGlite();
  await pg.waitReady;
  const wrap = (target: { query: typeof pg.query }): Queryable => ({
    async query<T>(text: string, params: unknown[] = []) {
      const result = await target.query<T>(text, params as any[]);
      return { rows: result.rows, rowCount: result.affectedRows ?? result.rows.length };
    },
  });
  return {
    kind: 'pglite',
    ...wrap(pg),
    async exec(script) {
      await pg.exec(script);
    },
    transaction: (fn) => pg.transaction((tx) => fn(wrap(tx))),
    async close() {
      await pg.close();
    },
  };
}

export async function createPostgresDb(url: string): Promise<Db> {
  const { default: postgres } = await import('postgres');
  // prepare: false keeps it working behind a transaction-mode pooler (Neon's pooled URL).
  const sql = postgres(url, { prepare: false, max: 5, idle_timeout: 20, connect_timeout: 10, onnotice: () => {} });
  const wrap = (target: Postgres.Sql | Postgres.TransactionSql): Queryable => ({
    async query<T>(text: string, params: unknown[] = []) {
      const rows = await target.unsafe(text, params as any[]);
      return { rows: [...rows] as T[], rowCount: rows.count ?? rows.length };
    },
  });
  return {
    kind: 'postgres',
    ...wrap(sql),
    async exec(script) {
      await sql.unsafe(script).simple();
    },
    transaction: async (fn) => (await sql.begin((tx) => fn(wrap(tx)))) as any,
    async close() {
      await sql.end({ timeout: 5 });
    },
  };
}

export async function openDb(config: { url?: string; pgliteDir?: string }): Promise<Db> {
  const db = config.url ? await createPostgresDb(config.url) : await createPgliteDb(config.pgliteDir);
  await migrate(db);
  return db;
}

let schema: string | undefined;

export async function migrate(db: Db): Promise<void> {
  schema ??= await readFile(new URL('./schema.sql', import.meta.url), 'utf8');
  await db.exec(schema);
}

/** A unique-constraint violation (Postgres SQLSTATE 23505), from either driver. */
export function isUniqueViolation(error: unknown, constraint?: string): boolean {
  const e = error as { code?: string; constraint?: string; constraint_name?: string; message?: string } | null;
  if (!e || e.code !== '23505') return false;
  if (!constraint) return true;
  const name = e.constraint ?? e.constraint_name ?? '';
  return name === constraint || (e.message ?? '').includes(constraint);
}
