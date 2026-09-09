import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import type { AppDb } from '@core/services/app-db/node/db';
import * as schema from '@core/services/app-db/node/schema';
import { getAppConfig } from '@main/bootstrap/core/config';
import { resolveDatabasePath } from './path';

export interface DrizzleClient {
  db: AppDb;
  sqlite: Database.Database;
  close: () => void;
}

export interface CreateDrizzleClientOptions {
  database?: Database.Database;
  filePath?: string;
  busyTimeoutMs?: number;
}

const DEFAULT_BUSY_TIMEOUT_MS = 5000;

function openDatabase(filePath: string, busyTimeoutMs: number): Database.Database {
  const db = new Database(filePath);
  db.pragma('journal_mode = WAL');
  db.pragma(`busy_timeout = ${busyTimeoutMs}`);
  return db;
}

export function createDrizzleClient(options: CreateDrizzleClientOptions = {}): DrizzleClient {
  if (getAppConfig().disableNativeDb) {
    throw new Error('Native SQLite database is disabled via EMDASH_DISABLE_NATIVE_DB=1');
  }

  const busyTimeout = options.busyTimeoutMs ?? DEFAULT_BUSY_TIMEOUT_MS;
  const sqlite =
    options.database ?? openDatabase(options.filePath ?? resolveDatabasePath(), busyTimeout);
  const db = drizzle(sqlite, { schema });

  const client: DrizzleClient = {
    db,
    sqlite,
    close: () => sqlite.close(),
  };

  return client;
}
