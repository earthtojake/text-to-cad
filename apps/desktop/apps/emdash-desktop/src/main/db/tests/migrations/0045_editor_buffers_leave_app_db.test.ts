import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

/**
 * 0045 drops the legacy (projectId, workspaceId, filePath)-keyed editor_buffers
 * table: crash-recovery buffers move to their own SQLite store beside the app
 * database, keyed by ResourceUri (file-content-stack spec §8). Existing rows
 * are transient crash-recovery artifacts and are dropped wholesale by explicit
 * decision — no data migration.
 *
 * The pre-0045 fixture carries two seeded legacy buffer rows to prove the
 * wholesale drop.
 */
describe('0045 editor buffers leave the app db', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('pre-0045');
  });

  afterEach(() => {
    fixture?.close();
  });

  it('drops the editor_buffers table and its seeded legacy rows', () => {
    const tables = fixture.sqlite
      .prepare(`SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'editor_buffers'`)
      .all();
    expect(tables).toEqual([]);

    const indexes = fixture.sqlite
      .prepare(
        `SELECT name FROM sqlite_master
         WHERE type = 'index' AND name = 'idx_editor_buffers_workspace_file'`
      )
      .all();
    expect(indexes).toEqual([]);
  });
});
