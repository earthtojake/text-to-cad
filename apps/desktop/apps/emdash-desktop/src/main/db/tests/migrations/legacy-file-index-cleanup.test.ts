import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';
import { initializeDatabase } from '@main/db/initialize';

describe('legacy workspace file index cleanup', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('drops the derived tables and version marker during database initialization', async () => {
    fixture = await openFixture('empty');
    fixture.sqlite.exec(`
      CREATE VIRTUAL TABLE workspace_file_index USING fts5(
        workspace_id UNINDEXED,
        path,
        filename,
        tokenize = 'trigram case_sensitive 0'
      );
      CREATE TABLE workspace_file_index_meta (
        workspace_id TEXT PRIMARY KEY,
        indexed_at INTEGER NOT NULL
      );
      INSERT OR REPLACE INTO kv (key, value, updated_at)
      VALUES ('file_index_version', '3', unixepoch());
    `);

    await initializeDatabase(fixture.sqlite);

    const tables = fixture.sqlite
      .prepare(
        `SELECT name FROM sqlite_master
         WHERE type = 'table' AND name IN ('workspace_file_index', 'workspace_file_index_meta')`
      )
      .all();
    const marker = fixture.sqlite
      .prepare(`SELECT value FROM kv WHERE key = 'file_index_version'`)
      .get();
    expect(tables).toEqual([]);
    expect(marker).toBeUndefined();
  });
});
