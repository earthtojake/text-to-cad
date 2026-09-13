import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

/**
 * 0043 adds the durable outcome columns to the workspaces mirror (spec §6): the
 * host-written last removal attempt and the per-script last outcomes, both as
 * versioned JSON. Additive and nullable — no data train; existing rows carry no
 * recorded attempt or script outcome.
 */
describe('0043 workspace removal attempt and script outcomes', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('pre-0035');
  });

  afterEach(() => {
    fixture?.close();
  });

  it('adds both columns with a null default', () => {
    const columns = fixture.sqlite.prepare(`PRAGMA table_info('workspaces')`).all() as {
      name: string;
      notnull: number;
      dflt_value: string | null;
    }[];

    for (const name of ['last_removal_attempt', 'script_outcomes']) {
      const column = columns.find((candidate) => candidate.name === name);
      expect(column, name).toBeDefined();
      expect(column?.notnull, name).toBe(0);
      expect(column?.dflt_value, name).toBeNull();
    }

    const rows = fixture.sqlite
      .prepare(
        `SELECT COUNT(*) AS n FROM workspaces
         WHERE last_removal_attempt IS NOT NULL OR script_outcomes IS NOT NULL`
      )
      .get() as { n: number };
    expect(rows.n).toBe(0);
  });

  it('round-trips both payloads through the raw columns', () => {
    const attempt = JSON.stringify({
      version: '1',
      stage: 'remove',
      class: 'terminal',
      message: 'worktree is locked',
      at: 1,
    });
    const outcomes = JSON.stringify({
      version: '1',
      prepare: null,
      setup: { outcome: 'failed', at: 1, message: 'pnpm install failed' },
      run: null,
    });
    fixture.sqlite
      .prepare(
        `INSERT INTO workspaces (id, type, location, path, last_removal_attempt, script_outcomes)
         VALUES ('ws-1', 'local', 'local', '/tmp/outcomes', ?, ?)`
      )
      .run(attempt, outcomes);

    const row = fixture.sqlite
      .prepare(`SELECT last_removal_attempt, script_outcomes FROM workspaces WHERE id = 'ws-1'`)
      .get() as { last_removal_attempt: string; script_outcomes: string };
    expect(JSON.parse(row.last_removal_attempt)).toMatchObject({ class: 'terminal' });
    expect(JSON.parse(row.script_outcomes)).toMatchObject({
      setup: { outcome: 'failed' },
    });
  });
});
