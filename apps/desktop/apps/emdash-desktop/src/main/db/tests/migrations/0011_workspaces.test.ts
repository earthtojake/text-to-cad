import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';

describe('0011 workspaces migration', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('creates the workspaces table', async () => {
    fixture = await openFixture('pre-0011');

    const tables = fixture.sqlite
      .prepare(`SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`)
      .all() as { name: string }[];

    expect(tables.map((t) => t.name)).toContain('workspaces');
  });

  it('workspaces table has all expected columns at head', async () => {
    fixture = await openFixture('pre-0011');

    const columns = fixture.sqlite.prepare(`PRAGMA table_info(workspaces)`).all() as {
      name: string;
      type: string;
      notnull: number;
      dflt_value: string | null;
    }[];

    const colNames = columns.map((c) => c.name);
    expect(colNames).toContain('id');
    expect(colNames).toContain('type');
    expect(colNames).toContain('path');
    expect(colNames).toContain('created_at');
    expect(colNames).toContain('updated_at');
    // Pull-scan git stat columns were retired at head in favor of observed_git.
    expect(colNames).not.toContain('lines_added');
    expect(colNames).not.toContain('lines_deleted');

    const typeCol = columns.find((c) => c.name === 'type')!;
    expect(typeCol.notnull).toBe(1);
  });

  it('workspace key column and index are retired at head', async () => {
    fixture = await openFixture('pre-0011');

    const indexes = fixture.sqlite
      .prepare(`SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='workspaces'`)
      .all() as { name: string }[];
    expect(indexes.map((i) => i.name)).not.toContain('idx_workspaces_key');

    const columns = fixture.sqlite.prepare(`PRAGMA table_info(workspaces)`).all() as {
      name: string;
    }[];
    expect(columns.map((c) => c.name)).not.toContain('key');
  });

  it('existing data is preserved after migration', async () => {
    fixture = await openFixture('pre-0011');

    const projects = fixture.sqlite.prepare(`SELECT COUNT(*) as count FROM projects`).get() as {
      count: number;
    };

    expect(projects.count).toBeGreaterThan(0);
  });
});
