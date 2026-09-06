import { describe, expect, it } from 'vitest';
import type { BundledMigration } from '../api';
import { betterSqlite3Driver } from '../node/better-sqlite3-driver';
import { defineDurableSqliteStore } from '../node/store';
import { assertIncrementalMigrationEquivalence } from './incremental-equivalence';

const migrations: BundledMigration[] = [
  {
    idx: 0,
    tag: '0000_items',
    when: 1,
    hash: 'items',
    sql: 'CREATE TABLE items (id INTEGER PRIMARY KEY);',
  },
  {
    idx: 1,
    tag: '0001_item_values',
    when: 2,
    hash: 'item-values',
    sql: "ALTER TABLE items ADD COLUMN value TEXT NOT NULL DEFAULT '';",
  },
  {
    idx: 2,
    tag: '0002_rebuild_items',
    when: 3,
    hash: 'rebuild-items',
    sql: `
      CREATE TABLE items_new (
        id INTEGER PRIMARY KEY,
        value TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1
      );
      INSERT INTO items_new (id, value) SELECT id, value FROM items;
      DROP TABLE items;
      ALTER TABLE items_new RENAME TO items;
      CREATE INDEX items_value_idx ON items(value);
    `,
  },
];

describe('incremental migration equivalence', () => {
  it('matches one-shot schema creation from every migration boundary', async () => {
    const store = defineDurableSqliteStore({
      name: 'incremental-equivalence-test',
      driver: betterSqlite3Driver,
      migrations,
    });

    await expect(assertIncrementalMigrationEquivalence(store, migrations.length)).resolves.toBe(
      undefined
    );
  });
});
