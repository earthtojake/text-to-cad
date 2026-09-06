import type Database from 'better-sqlite3';
import type { BetterSQLite3Database } from 'drizzle-orm/better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import type { DurableSqliteStore } from '#primitives/sqlite-store/api';
import { betterSqlite3Driver, defineDurableSqliteStore } from '#primitives/sqlite-store/node';
import { assertSqliteStoreInvariants } from '#primitives/sqlite-store/testing';
import { ensureFileSearchFtsSchema } from './fts-schema';
import { migrations } from './migrations/migrations.generated';
import * as schema from './schema';

export type FileSearchDb = BetterSQLite3Database<typeof schema>;

export const fileSearchStore: DurableSqliteStore<FileSearchDb, Database.Database> =
  defineDurableSqliteStore({
    name: 'file-search',
    driver: betterSqlite3Driver,
    migrations,
    createOrm: (connection) => drizzle(connection.native, { schema }),
    postMigrate: [
      (connection) => {
        connection.exec('PRAGMA synchronous = NORMAL');
        ensureFileSearchFtsSchema(connection);
      },
    ],
    backup: { retain: 2 },
    invariants: [assertSqliteStoreInvariants],
  });
