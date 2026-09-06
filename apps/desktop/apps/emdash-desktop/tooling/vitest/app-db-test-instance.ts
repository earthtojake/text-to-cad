import type Database from 'better-sqlite3';
import { afterEach, beforeEach, vi } from 'vitest';
import type { AppDb } from '@core/services/app-db/node/db';
import { resetAppDbForTests, setAppDb } from '@main/db/instance';

export function installAppDbTestInstance(
  createDatabase: () => AppDb,
  createSqlite: () => Database.Database = () => ({}) as Database.Database
): void {
  beforeEach(() => {
    resetAppDbForTests();
    setAppDb({
      db: createDatabase(),
      sqlite: createSqlite(),
      close: vi.fn(),
    });
  });
  afterEach(() => resetAppDbForTests());
}
