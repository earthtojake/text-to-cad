import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

/**
 * 0038 retires the conversations task-id FK cascade (spec §10.5): registry rows only
 * leave through explicit, declinable delete requests (conv.explicit-delete), so deleting
 * a task row unlinks surviving conversation rows instead of destroying them.
 */

const CONV_WITH_SESSION_ID = 'cccc0001-0000-0000-0000-000000000000';

describe('0038 conversation task cascade retirement', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('pre-0035');
  });

  afterEach(() => {
    fixture?.close();
  });

  it('relaxes the task link to ON DELETE SET NULL and keeps the project cascade', () => {
    const foreignKeys = fixture.sqlite
      .prepare(`PRAGMA foreign_key_list('conversations')`)
      .all() as Array<{ table: string; from: string; on_delete: string }>;

    const byColumn = new Map(foreignKeys.map((fk) => [fk.from, fk]));
    expect(byColumn.get('task_id')?.on_delete).toBe('SET NULL');
    expect(byColumn.get('project_id')?.on_delete).toBe('CASCADE');
    expect(byColumn.get('ssh_connection_id')?.on_delete).toBe('SET NULL');
  });

  it('unlinks conversation rows instead of deleting them when the task row goes', () => {
    fixture.sqlite.pragma('foreign_keys = ON');

    const before = fixture.sqlite
      .prepare(`SELECT task_id FROM conversations WHERE id = ?`)
      .get(CONV_WITH_SESSION_ID) as { task_id: string | null };
    expect(before.task_id).not.toBeNull();

    fixture.sqlite.prepare(`DELETE FROM tasks WHERE id = ?`).run(before.task_id);

    const after = fixture.sqlite
      .prepare(`SELECT task_id, title FROM conversations WHERE id = ?`)
      .get(CONV_WITH_SESSION_ID) as { task_id: string | null; title: string } | undefined;
    expect(after).toBeDefined();
    expect(after?.task_id).toBeNull();
  });

  it('carries every row across the table recreate without FK violations', () => {
    const count = fixture.sqlite.prepare(`SELECT COUNT(*) AS n FROM conversations`).get() as {
      n: number;
    };
    expect(count.n).toBe(2);

    const violations = fixture.sqlite.prepare(`PRAGMA foreign_key_check`).all();
    expect(violations).toEqual([]);
  });
});
