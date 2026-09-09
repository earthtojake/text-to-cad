import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { automationRuns, tasks } from '@core/services/app-db/node/schema';
import { getTasks } from './getTasks';

describe('getTasks', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    fixture.sqlite
      .prepare(
        `INSERT INTO projects (id, name, created_at, updated_at)
         VALUES ('project-1', 'Project', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)`
      )
      .run();
  });

  afterEach(() => {
    fixture.close();
  });

  it('loads tasks from the database', async () => {
    fixture.sqlite
      .prepare(
        `INSERT INTO tasks (
           id,
           project_id,
           name,
           status,
           created_at,
           updated_at,
           status_changed_at
         )
         VALUES (
           'task-1',
           'project-1',
           'My Task',
           'in_progress',
           CURRENT_TIMESTAMP,
           CURRENT_TIMESTAMP,
           CURRENT_TIMESTAMP
         )`
      )
      .run();

    const rows = await getTasks(fixture.db, 'project-1');

    expect(rows).toHaveLength(1);
    expect(rows[0]!.name).toBe('My Task');
    expect(rows[0]!.id).toBe('task-1');
    expect(rows[0]!.automationRunMeta).toBeUndefined();
  });

  it('joins projected automation run metadata onto automation tasks', async () => {
    await fixture.db.insert(automationRuns).values({
      id: 'run-1',
      automationId: 'automation-1',
      automationName: 'Review changes',
      status: 'done',
      scheduledAt: 100,
      startedAt: 110,
      finishedAt: 120,
      seq: 4,
    });
    await fixture.db.insert(tasks).values({
      id: 'task-1',
      projectId: 'project-1',
      name: 'Automation task',
      status: 'in_progress',
      type: 'automation-run',
      automationRunId: 'run-1',
    });

    const rows = await getTasks(fixture.db, 'project-1');

    expect(rows).toHaveLength(1);
    expect(rows[0]?.automationRunMeta).toEqual({
      automationName: 'Review changes',
      status: 'done',
      scheduledAt: 100,
      startedAt: 110,
      finishedAt: 120,
    });
  });
});
