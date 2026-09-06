import { randomUUID } from 'node:crypto';
import { mkdirSync, rmSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { BundledMigration } from '../api';
import { listBackups } from './backup';
import { betterSqlite3Driver } from './better-sqlite3-driver';
import { defineDurableSqliteStore } from './store';

const firstMigration: BundledMigration = {
  idx: 0,
  tag: '0000_items',
  when: 1,
  hash: 'items',
  sql: 'CREATE TABLE items (id INTEGER PRIMARY KEY, value TEXT NOT NULL);',
};

const secondMigration: BundledMigration = {
  idx: 1,
  tag: '0001_items_note',
  when: 2,
  hash: 'items-note',
  sql: 'ALTER TABLE items ADD COLUMN note TEXT;',
};

function tempDirectory(prefix = 'sqlite-store-backup-'): string {
  const path = join(tmpdir(), `${prefix}${randomUUID()}`);
  mkdirSync(path, { recursive: true });
  return path;
}

describe('SQLite store backups', () => {
  it('quotes hostile paths and prunes backups to the retention limit', () => {
    const directory = tempDirectory("sqlite store 'backup ");
    const path = join(directory, "data 'file.db");
    const v1 = defineDurableSqliteStore({
      name: 'backup-v1',
      driver: betterSqlite3Driver,
      migrations: [firstMigration],
      backup: { retain: 1 },
    });
    const v2 = defineDurableSqliteStore({
      name: 'backup-v2',
      driver: betterSqlite3Driver,
      migrations: [firstMigration, secondMigration],
      backup: { retain: 1 },
    });
    const thirdMigration: BundledMigration = {
      idx: 2,
      tag: '0002_more_items',
      when: 3,
      hash: 'more-items',
      sql: 'CREATE INDEX items_value_idx ON items(value);',
    };
    const v3 = defineDurableSqliteStore({
      name: 'backup-v3',
      driver: betterSqlite3Driver,
      migrations: [firstMigration, secondMigration, thirdMigration],
      backup: { retain: 1 },
    });

    try {
      v1.open(path).close();
      expect(listBackups(path)).toEqual([]);
      v2.open(path).close();
      v3.open(path).close();
      expect(listBackups(path)).toHaveLength(1);
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });

  it('orders valid backups by their embedded timestamp instead of mtime', () => {
    const directory = tempDirectory();
    const path = join(directory, 'data.db');
    const older = `${path}.backup-100-00000000-0000-0000-0000-000000000001`;
    const newer = `${path}.backup-200-00000000-0000-0000-0000-000000000002`;
    const malformed = `${path}.backup-not-a-timestamp`;

    try {
      writeFileSync(older, '');
      writeFileSync(newer, '');
      writeFileSync(malformed, '');
      utimesSync(older, new Date(300), new Date(300));
      utimesSync(newer, new Date(100), new Date(100));

      expect(listBackups(path)).toEqual([newer, older]);
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });

  it('does not create backups for temporary handles', async () => {
    const store = defineDurableSqliteStore({
      name: 'temporary-backup-test',
      driver: betterSqlite3Driver,
      migrations: [firstMigration],
      backup: { retain: 1 },
    });
    const handle = await store.openTemp();

    try {
      expect(listBackups(handle.path)).toEqual([]);
    } finally {
      handle.close();
    }
  });

  it('restores the latest backup and refuses restore while open', () => {
    const directory = tempDirectory();
    const path = join(directory, 'restore.db');
    const v1 = defineDurableSqliteStore({
      name: 'restore-v1',
      driver: betterSqlite3Driver,
      migrations: [firstMigration],
    });
    const v2 = defineDurableSqliteStore({
      name: 'restore-v2',
      driver: betterSqlite3Driver,
      migrations: [firstMigration, secondMigration],
      backup: { retain: 2 },
    });

    try {
      const initial = v1.open(path);
      initial.connection.run('INSERT INTO items (id, value) VALUES (1, ?)', ['preserved']);
      initial.close();

      const migrated = v2.open(path);
      migrated.connection.run('INSERT INTO items (id, value) VALUES (2, ?)', ['discarded']);
      expect(() => v2.restoreLatestBackup(path)).toThrow('while it is open');
      migrated.close();

      v2.restoreLatestBackup(path);
      const restored = v2.open(path);
      expect(
        restored.connection.all<{ value: string }>('SELECT value FROM items ORDER BY id')
      ).toEqual([{ value: 'preserved' }]);
      restored.close();
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
});
