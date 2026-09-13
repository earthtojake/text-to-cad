import { randomUUID } from 'node:crypto';
import { rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { noopLogger } from '@emdash/shared/logger';
import { describe, expect, it, vi } from 'vitest';
import type { BundledMigration, MigrationInterop } from '../api';
import { betterSqlite3Driver } from './better-sqlite3-driver';
import { migrateDurable } from './durable';
import { defineDurableSqliteStore } from './store';

const migrations: BundledMigration[] = [
  {
    idx: 0,
    tag: '0000_schema',
    when: 1,
    hash: 'hash-0',
    sql: `
      CREATE TABLE parent (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE child (
        id INTEGER PRIMARY KEY,
        parent_id INTEGER NOT NULL REFERENCES parent(id)
      );
      INSERT INTO parent (id, value) VALUES (1, 'before');
      INSERT INTO child (id, parent_id) VALUES (1, 1);
    `,
  },
  {
    idx: 1,
    tag: '0001_rebuild_parent',
    when: 2,
    hash: 'hash-1',
    sql: `
      PRAGMA foreign_keys = OFF;
      CREATE TABLE parent_new (
        id INTEGER PRIMARY KEY,
        value TEXT NOT NULL,
        added INTEGER NOT NULL DEFAULT 1
      );
      INSERT INTO parent_new (id, value) SELECT id, value FROM parent;
      DROP TABLE parent;
      ALTER TABLE parent_new RENAME TO parent;
      PRAGMA foreign_keys = ON;
    `,
  },
];

function tempPath(): string {
  return join(tmpdir(), `sqlite-store-durable-${randomUUID()}.db`);
}

function cleanup(path: string): void {
  for (const suffix of ['', '-wal', '-shm']) rmSync(`${path}${suffix}`, { force: true });
}

describe('durable SQLite migrations', () => {
  it('applies migrations idempotently with FK-safe table rebuilds', () => {
    const path = tempPath();
    const store = defineDurableSqliteStore({
      name: 'durable-test',
      driver: betterSqlite3Driver,
      migrations,
    });

    try {
      const first = store.open(path);
      expect(
        first.connection.get<{ added: number }>('SELECT added FROM parent WHERE id = 1')
      ).toEqual({
        added: 1,
      });
      expect(first.connection.all('PRAGMA foreign_key_check')).toEqual([]);
      first.close();

      const second = store.open(path);
      expect(
        second.connection.get<{ count: number }>(
          'SELECT count(*) AS count FROM __emdash_migrations'
        )?.count
      ).toBe(2);
      second.close();
    } finally {
      cleanup(path);
    }
  });

  it('commits prior migrations but rolls back a failing migration', () => {
    const path = tempPath();
    const connection = betterSqlite3Driver.open(path);
    const failing: BundledMigration[] = [
      {
        idx: 0,
        tag: '0000_stable',
        when: 1,
        hash: 'stable',
        sql: 'CREATE TABLE stable (id INTEGER PRIMARY KEY);',
      },
      {
        idx: 1,
        tag: '0001_fails',
        when: 2,
        hash: 'fails',
        sql: 'CREATE TABLE rolled_back (id INTEGER); THIS IS NOT SQL;',
      },
    ];

    try {
      expect(() =>
        migrateDurable(
          connection,
          { name: 'failure-test', driver: betterSqlite3Driver, migrations: failing },
          noopLogger
        )
      ).toThrow();
      expect(
        connection.get(`SELECT 1 FROM sqlite_schema WHERE type='table' AND name='stable'`)
      ).toBeDefined();
      expect(
        connection.get(`SELECT 1 FROM sqlite_schema WHERE type='table' AND name='rolled_back'`)
      ).toBeUndefined();
      expect(
        connection.all<{ tag: string }>('SELECT tag FROM __emdash_migrations ORDER BY tag')
      ).toEqual([{ tag: '0000_stable' }]);
    } finally {
      connection.close();
      cleanup(path);
    }
  });

  it('invokes migration interop inside bootstrap and apply transactions', async () => {
    const backfill = vi.fn();
    const onApplied = vi.fn();
    const interop: MigrationInterop = { backfill, onApplied };

    const store = defineDurableSqliteStore({
      name: 'interop-test',
      driver: betterSqlite3Driver,
      migrations: [migrations[0]],
      interop,
    });

    const handle = await store.openTemp();
    try {
      expect(backfill).toHaveBeenCalledOnce();
      expect(onApplied).toHaveBeenCalledOnce();
      expect(backfill.mock.invocationCallOrder[0]).toBeLessThan(
        onApplied.mock.invocationCallOrder[0]
      );
    } finally {
      handle.close();
    }
  });

  it('surfaces foreign-key violations created by a migration', async () => {
    const store = defineDurableSqliteStore({
      name: 'fk-violation-test',
      driver: betterSqlite3Driver,
      migrations: [
        {
          idx: 0,
          tag: '0000_invalid_fk',
          when: 1,
          hash: 'invalid',
          sql: `
            CREATE TABLE parent (id INTEGER PRIMARY KEY);
            CREATE TABLE child (parent_id INTEGER REFERENCES parent(id));
            INSERT INTO child (parent_id) VALUES (999);
          `,
        },
      ],
    });

    await expect(store.openTemp()).rejects.toThrow('foreign-key violations');
  });

  it('rejects runner metadata written by a newer implementation', () => {
    const path = tempPath();
    const setup = betterSqlite3Driver.open(path);
    setup.exec('PRAGMA user_version = 2');
    setup.close();
    const store = defineDurableSqliteStore({
      name: 'newer-runner-test',
      driver: betterSqlite3Driver,
      migrations,
    });

    try {
      expect(() => store.open(path)).toThrow('newer than supported version');
    } finally {
      cleanup(path);
    }
  });

  it('tolerates applied migrations unknown to an older manifest', () => {
    const path = tempPath();
    const latestStore = defineDurableSqliteStore({
      name: 'downgrade-latest-test',
      driver: betterSqlite3Driver,
      migrations,
    });
    const olderStore = defineDurableSqliteStore({
      name: 'downgrade-older-test',
      driver: betterSqlite3Driver,
      migrations: [migrations[0]],
    });

    try {
      latestStore.open(path).close();
      const downgraded = olderStore.open(path);
      expect(
        downgraded.connection.get<{ count: number }>(
          'SELECT count(*) AS count FROM __emdash_migrations'
        )?.count
      ).toBe(2);
      downgraded.close();
    } finally {
      cleanup(path);
    }
  });
});
