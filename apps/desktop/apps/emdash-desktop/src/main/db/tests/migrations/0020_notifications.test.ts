import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';
import { notifications } from '@core/services/app-db/node/schema';

describe('0020_notifications', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('creates the notifications table on top of the pre-0020 fixture', async () => {
    fixture = await openFixture('pre-0020');

    const tables = fixture.sqlite
      .prepare(`SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'`)
      .all() as { name: string }[];
    expect(tables).toHaveLength(1);

    const indexes = fixture.sqlite
      .prepare(`SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='notifications'`)
      .all() as { name: string }[];
    expect(indexes.map((row) => row.name)).toEqual(
      expect.arrayContaining([
        'idx_notifications_created_at',
        'idx_notifications_group_key',
        'idx_notifications_read_at',
      ])
    );

    const rows = await fixture.db.select().from(notifications);
    expect(rows).toHaveLength(0);
  });
});
