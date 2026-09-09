import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';

describe('0027/0028_drop_legacy_operations', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('drops the legacy lifecycle operation tables', async () => {
    fixture = await openFixture('pre-0027');

    const rows = fixture.sqlite
      .prepare(
        `SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('operation_claims', 'lifecycle_operations')`
      )
      .all() as { name: string }[];

    expect(rows).toEqual([]);
  });
});
