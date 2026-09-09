import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

/**
 * 0044 adds the durable deletion tombstone column to the conversations mirror
 * (ADR 0006): target record UUID + write stamp as versioned JSON. Additive and
 * nullable — no data train; existing rows carry no pending deletion.
 */
describe('0044 conversation deletion tombstone', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('pre-0035');
  });

  afterEach(() => {
    fixture?.close();
  });

  it('adds the deletion_tombstone column with a null default', () => {
    const columns = fixture.sqlite.prepare(`PRAGMA table_info('conversations')`).all() as {
      name: string;
      notnull: number;
      dflt_value: string | null;
    }[];

    const column = columns.find(({ name }) => name === 'deletion_tombstone');
    expect(column).toBeDefined();
    expect(column?.notnull).toBe(0);
    expect(column?.dflt_value).toBeNull();

    const rows = fixture.sqlite
      .prepare(`SELECT COUNT(*) AS n FROM conversations WHERE deletion_tombstone IS NOT NULL`)
      .get() as { n: number };
    expect(rows.n).toBe(0);
  });

  it('round-trips a tombstone payload through the raw column', () => {
    const payload = JSON.stringify({
      version: '1',
      targetRecordId: 'conv-1',
      tombstonedAt: 1,
    });
    fixture.sqlite
      .prepare(
        `INSERT INTO conversations (id, title, deletion_tombstone)
         VALUES ('conv-1', 'Tombstoned', ?)`
      )
      .run(payload);

    const row = fixture.sqlite
      .prepare(`SELECT deletion_tombstone FROM conversations WHERE id = 'conv-1'`)
      .get() as { deletion_tombstone: string };
    expect(JSON.parse(row.deletion_tombstone)).toMatchObject({ targetRecordId: 'conv-1' });
  });
});
