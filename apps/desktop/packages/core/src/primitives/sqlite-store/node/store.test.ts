import { randomUUID } from 'node:crypto';
import { rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import type { BundledMigration, SqliteConnection } from '../api';
import { betterSqlite3Driver } from './better-sqlite3-driver';
import { defineDerivedSqliteStore, defineDurableSqliteStore } from './store';

const migrations: BundledMigration[] = [
  {
    idx: 0,
    tag: '0000_records',
    when: 1,
    hash: 'records',
    sql: 'CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL);',
  },
  {
    idx: 1,
    tag: '0001_records_note',
    when: 2,
    hash: 'records-note',
    sql: 'ALTER TABLE records ADD COLUMN note TEXT;',
  },
];

function tempPath(): string {
  return join(tmpdir(), `sqlite-store-lifecycle-${randomUUID()}.db`);
}

function cleanup(path: string): void {
  for (const suffix of ['', '-wal', '-shm']) rmSync(`${path}${suffix}`, { force: true });
}

describe('SQLite store lifecycle', () => {
  it('awaits asynchronous temporary-database seeds', async () => {
    const store = defineDurableSqliteStore({
      name: 'temp-seed-test',
      driver: betterSqlite3Driver,
      migrations,
    });
    const handle = await store.openTemp(async ({ connection }) => {
      await Promise.resolve();
      connection.run('INSERT INTO records (id, value) VALUES (1, ?)', ['seeded']);
    });

    try {
      expect(
        handle.connection.get<{ value: string }>('SELECT value FROM records WHERE id = 1')?.value
      ).toBe('seeded');
    } finally {
      handle.close();
    }
  });

  it('opens a pre-migration state and migrates it to latest', () => {
    const store = defineDurableSqliteStore({
      name: 'migration-boundary-test',
      driver: betterSqlite3Driver,
      migrations,
    });
    const handle = store.openAtMigration(1);

    try {
      expect(
        handle.connection
          .all<{ name: string }>('PRAGMA table_info(records)')
          .map(({ name }) => name)
      ).toEqual(['id', 'value']);

      handle.connection.run('INSERT INTO records (id, value) VALUES (1, ?)', ['kept']);
      handle.migrateToLatest();

      expect(
        handle.connection
          .all<{ name: string }>('PRAGMA table_info(records)')
          .map(({ name }) => name)
      ).toEqual(['id', 'value', 'note']);
      expect(
        handle.connection.get<{ value: string }>('SELECT value FROM records WHERE id = 1')?.value
      ).toBe('kept');
    } finally {
      handle.close();
    }
  });

  it('cleans up temporary databases when a seed fails', async () => {
    const store = defineDerivedSqliteStore({
      name: 'temp-cleanup-test',
      driver: betterSqlite3Driver,
      version: 1,
      createSchema(connection) {
        connection.exec('CREATE TABLE cache (value TEXT)');
      },
    });

    await expect(
      store.openTemp(async () => {
        throw new Error('seed failed');
      })
    ).rejects.toThrow('seed failed');
  });

  it('rejects invalid migration boundaries', () => {
    const store = defineDurableSqliteStore({
      name: 'invalid-boundary-test',
      driver: betterSqlite3Driver,
      migrations,
    });
    expect(() => store.openAtMigration(3)).toThrow('Migration boundary');
  });

  it('enables foreign keys before hooks and on every returned handle', () => {
    const path = tempPath();
    const observedForeignKeyStates: number[] = [];
    const observeForeignKeys = (connection: SqliteConnection): void => {
      const enabled = connection.get<{ foreign_keys: number }>('PRAGMA foreign_keys')?.foreign_keys;
      observedForeignKeyStates.push(enabled ?? -1);
    };
    const store = defineDurableSqliteStore({
      name: 'foreign-key-state-test',
      driver: betterSqlite3Driver,
      migrations,
      postMigrate: [observeForeignKeys],
      invariants: [observeForeignKeys],
    });

    try {
      const first = store.open(path);
      expect(
        first.connection.get<{ foreign_keys: number }>('PRAGMA foreign_keys')?.foreign_keys
      ).toBe(1);
      first.close();

      const second = store.open(path);
      expect(
        second.connection.get<{ foreign_keys: number }>('PRAGMA foreign_keys')?.foreign_keys
      ).toBe(1);
      second.close();

      const migrationHandle = store.openAtMigration(1);
      migrationHandle.migrateToLatest();
      expect(
        migrationHandle.connection.get<{ foreign_keys: number }>('PRAGMA foreign_keys')
          ?.foreign_keys
      ).toBe(1);
      migrationHandle.close();

      expect(observedForeignKeyStates).toEqual([1, 1, 1, 1, 1]);
    } finally {
      cleanup(path);
    }
  });

  it('opens the zero-migration boundary and migrates it to latest', () => {
    const store = defineDurableSqliteStore({
      name: 'zero-boundary-test',
      driver: betterSqlite3Driver,
      migrations,
    });
    const handle = store.openAtMigration(0);

    try {
      expect(
        handle.connection.get(
          `SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'records'`
        )
      ).toBeUndefined();
      expect(
        handle.connection.get(
          `SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = '__emdash_migrations'`
        )
      ).toBeDefined();

      handle.migrateToLatest();
      expect(
        handle.connection.get(
          `SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'records'`
        )
      ).toBeDefined();
    } finally {
      handle.close();
    }
  });

  it('rejects invalid busy timeouts', () => {
    const path = tempPath();
    const store = defineDurableSqliteStore({
      name: 'invalid-busy-timeout-test',
      driver: betterSqlite3Driver,
      migrations,
      busyTimeoutMs: -1,
    });

    try {
      expect(() => store.open(path)).toThrow(RangeError);
    } finally {
      cleanup(path);
    }
  });

  it('runs invariants only after migrations and for temporary latest-schema handles', async () => {
    const path = tempPath();
    const postMigrate = vi.fn();
    const invariant = vi.fn();
    const store = defineDurableSqliteStore({
      name: 'invariant-gating-test',
      driver: betterSqlite3Driver,
      migrations,
      postMigrate: [postMigrate],
      invariants: [invariant],
    });

    try {
      store.open(path).close();
      expect(postMigrate).toHaveBeenCalledTimes(1);
      expect(invariant).toHaveBeenCalledTimes(1);

      store.open(path).close();
      expect(postMigrate).toHaveBeenCalledTimes(2);
      expect(invariant).toHaveBeenCalledTimes(1);

      const temporary = await store.openTemp();
      temporary.close();
      expect(postMigrate).toHaveBeenCalledTimes(3);
      expect(invariant).toHaveBeenCalledTimes(2);

      const migrationHandle = store.openAtMigration(1);
      migrationHandle.migrateToLatest();
      migrationHandle.close();
      expect(postMigrate).toHaveBeenCalledTimes(4);
      expect(invariant).toHaveBeenCalledTimes(3);
    } finally {
      cleanup(path);
    }
  });
});
