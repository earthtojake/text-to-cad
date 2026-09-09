import { randomUUID } from 'node:crypto';
import { rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { betterSqlite3Driver } from './better-sqlite3-driver';
import { defineDerivedSqliteStore } from './store';

function tempPath(): string {
  return join(tmpdir(), `sqlite-store-derived-${randomUUID()}.db`);
}

function cleanup(path: string): void {
  for (const suffix of ['', '-wal', '-shm']) rmSync(`${path}${suffix}`, { force: true });
}

describe('derived SQLite stores', () => {
  it('creates the schema once when its version matches', () => {
    const path = tempPath();
    const createSchema = vi.fn((connection) => {
      connection.exec('CREATE TABLE cache_entries (key TEXT PRIMARY KEY, value TEXT)');
    });
    const store = defineDerivedSqliteStore({
      name: 'derived-test',
      driver: betterSqlite3Driver,
      version: 2,
      createSchema,
    });

    try {
      const first = store.open(path);
      first.close();
      const second = store.open(path);
      second.close();
      expect(createSchema).toHaveBeenCalledOnce();
    } finally {
      cleanup(path);
    }
  });

  it.each([
    { label: 'older', version: 1 },
    { label: 'newer', version: 3 },
  ])('rebuilds $label schema versions', ({ version }) => {
    const path = tempPath();
    const setup = betterSqlite3Driver.open(path);
    setup.exec(`
      CREATE TABLE stale_cache (value TEXT);
      INSERT INTO stale_cache (value) VALUES ('discard me');
      PRAGMA user_version = ${version};
    `);
    setup.close();

    const store = defineDerivedSqliteStore({
      name: 'derived-rebuild-test',
      driver: betterSqlite3Driver,
      version: 2,
      createSchema(connection) {
        connection.exec('CREATE TABLE current_cache (value TEXT)');
      },
    });

    try {
      const handle = store.open(path);
      expect(
        handle.connection.get(
          `SELECT 1 FROM sqlite_schema WHERE type='table' AND name='stale_cache'`
        )
      ).toBeUndefined();
      expect(
        handle.connection.get(
          `SELECT 1 FROM sqlite_schema WHERE type='table' AND name='current_cache'`
        )
      ).toBeDefined();
      expect(
        handle.connection.get<{ user_version: number }>('PRAGMA user_version')?.user_version
      ).toBe(2);
      handle.close();
    } finally {
      cleanup(path);
    }
  });
});
