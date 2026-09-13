import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

/**
 * 0042 adds the durable deletion tombstone column to the workspaces mirror (ADR 0006):
 * frozen options + target record UUID as versioned JSON. Additive and nullable — no
 * data train; existing rows carry no pending deletion.
 */
describe('0042 workspace deletion tombstone', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('pre-0035');
  });

  afterEach(() => {
    fixture?.close();
  });

  it('adds the deletion_tombstone column with a null default', () => {
    const columns = fixture.sqlite.prepare(`PRAGMA table_info('workspaces')`).all() as {
      name: string;
      notnull: number;
      dflt_value: string | null;
    }[];

    const column = columns.find(({ name }) => name === 'deletion_tombstone');
    expect(column).toBeDefined();
    expect(column?.notnull).toBe(0);
    expect(column?.dflt_value).toBeNull();

    const rows = fixture.sqlite
      .prepare(`SELECT COUNT(*) AS n FROM workspaces WHERE deletion_tombstone IS NOT NULL`)
      .get() as { n: number };
    expect(rows.n).toBe(0);
  });

  it('round-trips a tombstone payload through the raw column', () => {
    const payload = JSON.stringify({
      version: '1',
      targetRecordId: 'ws-1',
      tombstonedAt: 1,
      options: { deleteBranch: true, deleteConversations: false },
    });
    fixture.sqlite
      .prepare(
        `INSERT INTO workspaces (id, type, location, path, deletion_tombstone)
         VALUES ('ws-1', 'local', 'local', '/tmp/tombstoned', ?)`
      )
      .run(payload);

    const row = fixture.sqlite
      .prepare(`SELECT deletion_tombstone FROM workspaces WHERE id = 'ws-1'`)
      .get() as { deletion_tombstone: string };
    expect(JSON.parse(row.deletion_tombstone)).toMatchObject({ targetRecordId: 'ws-1' });
  });
});
