import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';

describe('0016 acp conversation type migration', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('adds a nullable type column to conversations', async () => {
    fixture = await openFixture('pre-0016');

    const columns = fixture.sqlite.prepare(`PRAGMA table_info(conversations)`).all() as {
      name: string;
      notnull: number;
      dflt_value: string | null;
    }[];

    const typeCol = columns.find((c) => c.name === 'type');
    expect(typeCol).toBeDefined();
    expect(typeCol!.notnull).toBe(0);
    expect(typeCol!.dflt_value).toBeNull();
  });

  it('leaves existing conversation rows with null type', async () => {
    fixture = await openFixture('pre-0016');

    const rows = fixture.sqlite.prepare(`SELECT type FROM conversations LIMIT 1`).all() as {
      type: string | null;
    }[];

    if (rows.length > 0) {
      expect(rows[0].type).toBeNull();
    }
  });
});
