import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';

describe('0012 terminal shell id migration', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('adds a non-null shell_id column with the system value', async () => {
    fixture = await openFixture('pre-0012');

    const columns = fixture.sqlite.prepare(`PRAGMA table_info(terminals)`).all() as {
      name: string;
      notnull: number;
      dflt_value: string | null;
    }[];

    const shellId = columns.find((c) => c.name === 'shell_id');
    expect(shellId).toBeDefined();
    expect(shellId!.notnull).toBe(1);
    expect(shellId!.dflt_value).toBe("'system'");
  });

  it('backfills existing terminal rows to system', async () => {
    fixture = await openFixture('pre-0012');

    const row = fixture.sqlite
      .prepare(`SELECT shell_id FROM terminals WHERE id = 'pre-0012-terminal-1'`)
      .get() as { shell_id: string } | undefined;

    expect(row?.shell_id).toBe('system');
  });
});
