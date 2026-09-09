import type Database from 'better-sqlite3';
import type { BetterSQLite3Database } from 'drizzle-orm/better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import type { DurableSqliteStore } from '#primitives/sqlite-store/api';
import { betterSqlite3Driver, defineDurableSqliteStore } from '#primitives/sqlite-store/node';
import { assertSqliteStoreInvariants } from '#primitives/sqlite-store/testing';
import { migrations } from './migrations/migrations.generated';
import * as schema from './schema';

export type ConversationsDb = BetterSQLite3Database<typeof schema>;

/**
 * The durable conversation index storage (spec §3.4): its own SQLite file, owned exclusively
 * by the conversations worker. Deliberately not a table in the kernel operations DB —
 * conversation records are user content and must never be swept by operational retention
 * (conv.explicit-delete).
 */
export const conversationsStore: DurableSqliteStore<ConversationsDb, Database.Database> =
  defineDurableSqliteStore({
    name: 'conversations',
    driver: betterSqlite3Driver,
    migrations,
    createOrm: (connection) => drizzle(connection.native, { schema }),
    backup: { retain: 2 },
    invariants: [assertSqliteStoreInvariants],
  });
