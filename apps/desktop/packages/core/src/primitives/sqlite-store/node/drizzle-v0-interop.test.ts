import { randomUUID } from 'node:crypto';
import { rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { BundledMigration } from '../api';
import { betterSqlite3Driver } from './better-sqlite3-driver';
import { drizzleV0Interop } from './drizzle-v0-interop';
import { defineDurableSqliteStore } from './store';

const migration: BundledMigration = {
  idx: 0,
  tag: '0000_users',
  when: 1234,
  hash: 'users-hash',
  sql: 'CREATE TABLE users (id INTEGER PRIMARY KEY);',
};

function tempPath(): string {
  return join(tmpdir(), `sqlite-store-drizzle-v0-${randomUUID()}.db`);
}

function cleanup(path: string): void {
  for (const suffix of ['', '-wal', '-shm']) rmSync(`${path}${suffix}`, { force: true });
}

function createLegacyDatabase(path: string, hash: string, when: number): void {
  const connection = betterSqlite3Driver.open(path);
  connection.exec(`
    CREATE TABLE __drizzle_migrations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      hash TEXT NOT NULL,
      created_at NUMERIC
    );
    CREATE TABLE users (id INTEGER PRIMARY KEY);
  `);
  connection.run('INSERT INTO __drizzle_migrations (hash, created_at) VALUES (?, ?)', [hash, when]);
  connection.close();
}

describe('drizzle v0 migration interop', () => {
  it('backfills by journal timestamp', () => {
    const path = tempPath();
    createLegacyDatabase(path, migration.hash, migration.when);
    const store = defineDurableSqliteStore({
      name: 'legacy-test',
      driver: betterSqlite3Driver,
      migrations: [migration],
      interop: drizzleV0Interop,
    });

    try {
      const handle = store.open(path);
      expect(
        handle.connection.get<{ tag: string }>('SELECT tag FROM __emdash_migrations')?.tag
      ).toBe(migration.tag);
      handle.close();
    } finally {
      cleanup(path);
    }
  });

  it('stores the canonical hash when a timestamp match has a different legacy hash', () => {
    const path = tempPath();
    createLegacyDatabase(path, 'legacy-hash', migration.when);
    const store = defineDurableSqliteStore({
      name: 'legacy-canonical-hash-test',
      driver: betterSqlite3Driver,
      migrations: [migration],
      interop: drizzleV0Interop,
    });

    try {
      const first = store.open(path);
      expect(
        first.connection.get<{ hash: string }>('SELECT hash FROM __emdash_migrations')?.hash
      ).toBe(migration.hash);
      first.close();

      const second = store.open(path);
      expect(
        second.connection.get<{ hash: string }>('SELECT hash FROM __emdash_migrations')?.hash
      ).toBe(migration.hash);
      second.close();
    } finally {
      cleanup(path);
    }
  });

  it('falls back to hash when the journal timestamp does not match', () => {
    const path = tempPath();
    createLegacyDatabase(path, migration.hash, 9999);
    const store = defineDurableSqliteStore({
      name: 'legacy-hash-test',
      driver: betterSqlite3Driver,
      migrations: [migration],
      interop: drizzleV0Interop,
    });

    try {
      const handle = store.open(path);
      expect(
        handle.connection.get<{ tag: string }>('SELECT tag FROM __emdash_migrations')?.tag
      ).toBe(migration.tag);
      handle.close();
    } finally {
      cleanup(path);
    }
  });

  it('throws when hash fallback matches multiple bundled migrations', () => {
    const path = tempPath();
    createLegacyDatabase(path, migration.hash, 9999);
    const duplicateHashMigration: BundledMigration = {
      ...migration,
      idx: 1,
      tag: '0001_users_duplicate',
      when: 5678,
    };
    const store = defineDurableSqliteStore({
      name: 'legacy-ambiguous-hash-test',
      driver: betterSqlite3Driver,
      migrations: [migration, duplicateHashMigration],
      interop: drizzleV0Interop,
    });

    try {
      expect(() => store.open(path)).toThrow('Ambiguous legacy migration hash');
    } finally {
      cleanup(path);
    }
  });

  it('throws when an applied legacy migration cannot be identified', () => {
    const path = tempPath();
    createLegacyDatabase(path, 'unknown-hash', 9999);
    const store = defineDurableSqliteStore({
      name: 'legacy-invalid-test',
      driver: betterSqlite3Driver,
      migrations: [migration],
      interop: drizzleV0Interop,
    });

    try {
      expect(() => store.open(path)).toThrow('Unrecognized legacy migration');
    } finally {
      cleanup(path);
    }
  });

  it('dual-writes new migrations in temporary databases', async () => {
    const store = defineDurableSqliteStore({
      name: 'legacy-dual-write-test',
      driver: betterSqlite3Driver,
      migrations: [migration],
      interop: drizzleV0Interop,
    });
    const handle = await store.openTemp();

    try {
      expect(
        handle.connection.get<{ hash: string; created_at: number }>(
          'SELECT hash, created_at FROM __drizzle_migrations'
        )
      ).toEqual({ hash: migration.hash, created_at: migration.when });
    } finally {
      handle.close();
    }
  });
});
