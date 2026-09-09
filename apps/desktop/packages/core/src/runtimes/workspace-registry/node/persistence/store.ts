import type Database from 'better-sqlite3';
import type { BetterSQLite3Database } from 'drizzle-orm/better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import type { DurableSqliteStore } from '#primitives/sqlite-store/api';
import { betterSqlite3Driver, defineDurableSqliteStore } from '#primitives/sqlite-store/node';
import { assertSqliteStoreInvariants } from '#primitives/sqlite-store/testing';
import { migrations } from './migrations/migrations.generated';
import * as schema from './schema';

export type WorkspaceRegistryDb = BetterSQLite3Database<typeof schema>;

/**
 * The durable workspace registry storage (ADR 0005): its own SQLite file, owned
 * exclusively by the workspace-registry worker — the sole writer. Deliberately not a
 * table in any shared database.
 */
export const workspaceRegistryStore: DurableSqliteStore<WorkspaceRegistryDb, Database.Database> =
  defineDurableSqliteStore({
    name: 'workspace-registry',
    driver: betterSqlite3Driver,
    migrations,
    createOrm: (connection) => drizzle(connection.native, { schema }),
    backup: { retain: 2 },
    invariants: [assertSqliteStoreInvariants],
  });
