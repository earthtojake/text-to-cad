import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';
import { automationRuns } from '@core/services/app-db/node/schema';

describe('0022_automation_run_projection', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('backfills legacy runs into the projection shape', async () => {
    fixture = await openFixture('pre-0022');

    const rows = await fixture.db.select().from(automationRuns).orderBy(automationRuns.id);
    expect(rows).toEqual([
      {
        id: 'run-active',
        automationId: 'automation-active',
        automationName: 'Nightly Review',
        status: 'done',
        scheduledAt: 1000,
        startedAt: 1100,
        finishedAt: 1200,
        seq: 0,
      },
      {
        id: 'run-orphaned',
        automationId: 'automation-missing',
        automationName: 'Automation run',
        status: 'scheduled',
        scheduledAt: 3000,
        startedAt: null,
        finishedAt: null,
        seq: 0,
      },
      {
        id: 'run-soft-deleted',
        automationId: 'automation-soft-deleted',
        automationName: 'Retired Automation',
        status: 'failed',
        scheduledAt: 2000,
        startedAt: 2100,
        finishedAt: 2200,
        seq: 0,
      },
    ]);

    const columns = fixture.sqlite.prepare(`PRAGMA table_info('automation_runs')`).all() as {
      name: string;
    }[];
    expect(columns.map(({ name }) => name)).toEqual([
      'id',
      'automation_id',
      'automation_name',
      'status',
      'scheduled_at',
      'started_at',
      'finished_at',
      'seq',
    ]);

    const foreignKeys = fixture.sqlite.prepare(`PRAGMA foreign_key_list('automation_runs')`).all();
    expect(foreignKeys).toEqual([]);

    const indexes = fixture.sqlite.prepare(`PRAGMA index_list('automation_runs')`).all() as {
      name: string;
    }[];
    expect(indexes.map(({ name }) => name)).toContain('idx_automation_runs_automation_id');
  });

  it('defaults existing and new automation revisions to one', async () => {
    fixture = await openFixture('pre-0022');

    const existing = fixture.sqlite
      .prepare(`SELECT id, revision FROM automations ORDER BY id`)
      .all() as { id: string; revision: number }[];
    expect(existing).toEqual([
      { id: 'automation-active', revision: 1 },
      { id: 'automation-soft-deleted', revision: 1 },
    ]);

    fixture.sqlite
      .prepare(
        `INSERT INTO automations (id, name, enabled, created_at, updated_at)
         VALUES ('automation-new', 'New Automation', 1, 300, 300)`
      )
      .run();
    const inserted = fixture.sqlite
      .prepare(`SELECT revision FROM automations WHERE id = 'automation-new'`)
      .get() as { revision: number };
    expect(inserted.revision).toBe(1);
  });

  it('enforces one active task per run while allowing re-adoption after soft deletion', async () => {
    fixture = await openFixture('pre-0022');

    const indexes = fixture.sqlite.prepare(`PRAGMA index_list('tasks')`).all() as {
      name: string;
    }[];
    expect(indexes.map(({ name }) => name)).toContain('idx_tasks_active_automation_run_id');

    const insertTask = fixture.sqlite.prepare(
      `INSERT INTO tasks (id, project_id, name, status, type, automation_run_id)
       VALUES (?, '11111111-1111-1111-1111-111111111111', ?, 'in_progress', 'automation-run', ?)`
    );
    insertTask.run('adopted-task-1', 'First adoption', 'run-active');
    expect(() => insertTask.run('adopted-task-2', 'Duplicate adoption', 'run-active')).toThrow(
      /UNIQUE constraint failed/
    );

    fixture.sqlite
      .prepare(`UPDATE tasks SET deleted_at = CURRENT_TIMESTAMP WHERE id = 'adopted-task-1'`)
      .run();
    expect(() =>
      insertTask.run('adopted-task-2', 'Replacement adoption', 'run-active')
    ).not.toThrow();
  });

  it('preserves projected runs when an automation is deleted', async () => {
    fixture = await openFixture('pre-0022');

    fixture.sqlite.prepare(`DELETE FROM automations WHERE id = 'automation-active'`).run();
    const projected = fixture.sqlite
      .prepare(`SELECT automation_name FROM automation_runs WHERE id = 'run-active'`)
      .get() as { automation_name: string } | undefined;
    expect(projected).toEqual({ automation_name: 'Nightly Review' });
  });
});
